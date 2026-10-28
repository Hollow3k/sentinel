import json
import math

import pytest

from app import scoring
from app.db import Transaction
from tests.conftest import ADMIN


def test_health_reports_model_loaded(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_loaded": True}


def test_transaction_is_scored_by_real_model(post_tx, legit):
    # source == "model" matters: if SHAP breaks, scoring silently falls back to rules.
    r = post_tx(legit)
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "model"
    assert 0.0 <= body["score"] <= 1.0
    assert body["flagged"] is False
    assert len(body["explanation"]) == 3
    assert {"feature", "contribution", "value"} <= set(body["explanation"][0])


def test_known_fraud_row_is_flagged(post_tx, fraud):
    body = post_tx(fraud).json()
    assert body["source"] == "model"
    assert body["flagged"] is True
    assert body["score"] >= scoring.THRESHOLD


def test_idempotent_replay_returns_same_transaction(post_tx, legit):
    first = post_tx(legit, key="replay-key-1")
    second = post_tx(legit, key="replay-key-1")
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_same_key_with_different_payload_is_409(post_tx, legit):
    assert post_tx(legit, key="conflict-key-1").status_code == 201
    changed = {**legit, "Amount": legit["Amount"] + 1}
    assert post_tx(changed, key="conflict-key-1").status_code == 409


def test_concurrent_different_payload_is_409(client, legit, monkeypatch):
    from app import main
    from sqlalchemy.exc import IntegrityError

    session_factory = main.SessionLocal
    db = session_factory()
    winner = Transaction(
        idempotency_key="race-key-1", features=legit, time_seconds=0, amount=1,
        hour_of_day=0, bucket=0, score=0, source="fallback_rules", flagged=False,
    )
    db.add(winner)
    db.commit()
    db.close()
    monkeypatch.setattr(scoring, "score", lambda features: {
        "score": 0.1, "source": "model", "flagged": False, "explanation": [],
    })

    class RaceSession:
        def __init__(self):
            self.db = session_factory()
        def __getattr__(self, name):
            return getattr(self.db, name)
        def commit(self):
            raise IntegrityError("duplicate", {}, None)
        def close(self):
            self.db.close()

    monkeypatch.setattr(main, "SessionLocal", RaceSession)
    changed = {**legit, "Amount": legit["Amount"] + 1}
    response = client.post("/transactions", headers=ADMIN, json={
        "idempotency_key": "race-key-1", "features": changed,
    })
    assert response.status_code == 409


def _without(features, name):
    return {k: v for k, v in features.items() if k != name}


@pytest.mark.parametrize("make_features", [
    pytest.param(lambda f: _without(f, "V1"), id="missing-feature"),
    pytest.param(lambda f: {**f, "Extra": 1.0}, id="extra-feature"),
    pytest.param(lambda f: {**f, "Amount": -5.0}, id="negative-amount"),
    pytest.param(lambda f: {**f, "Amount": 2_000_000.0}, id="amount-too-large"),
    pytest.param(lambda f: {**f, "Time": -1.0}, id="negative-time"),
])
def test_invalid_features_are_422(post_tx, legit, make_features):
    assert post_tx(make_features(legit)).status_code == 422


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"])
def test_non_finite_numbers_are_422(client, legit, bad):
    # httpx refuses to serialise NaN/inf, so send the raw JSON text (Python's json emits NaN/Infinity).
    body = json.dumps({"idempotency_key": "nan-key-0001", "features": {**legit, "V1": bad}})
    r = client.post("/transactions", headers={**ADMIN, "Content-Type": "application/json"},
                    content=body)
    assert r.status_code == 422


@pytest.mark.parametrize("key", ["short", "has space 123", "bad!chars-123", "x" * 65])
def test_invalid_idempotency_key_is_422(post_tx, legit, key):
    assert post_tx(legit, key=key).status_code == 422


def test_fallback_when_model_unavailable(client, post_tx, legit, monkeypatch):
    monkeypatch.setattr(scoring, "_model", None)
    assert client.get("/health").json()["model_loaded"] is False

    ok = post_tx({**legit, "Amount": 50.0}, key="fallback-low-1").json()
    assert ok["source"] == "fallback_rules"
    assert ok["flagged"] is False

    high = post_tx({**legit, "Amount": 5000.0}, key="fallback-high-1").json()
    assert high["source"] == "fallback_rules"
    assert high["flagged"] is True
    assert high["explanation"] == []


def test_fallback_when_shap_fails(post_tx, legit, monkeypatch):
    class BrokenExplainer:
        def shap_values(self, df):
            raise RuntimeError("shap exploded")
    monkeypatch.setattr(scoring, "_explainer", BrokenExplainer())
    body = post_tx(legit).json()
    assert body["source"] == "fallback_rules"


def test_service_starts_without_a_model_when_loading_fails(monkeypatch, legit):
    from fastapi.testclient import TestClient

    from app.main import app

    class BrokenModel:
        def load_model(self, path):
            raise OSError("model file missing")
    monkeypatch.setattr(scoring, "XGBClassifier", BrokenModel)
    with TestClient(app) as c:  # lifespan calls scoring.load_model()
        assert c.get("/health").json()["model_loaded"] is False
        r = c.post("/transactions", headers=ADMIN,
                   json={"idempotency_key": "no-model-0001", "features": legit})
        assert r.status_code == 201
        assert r.json()["source"] == "fallback_rules"


def test_demo_seed_is_public_and_creates_transactions(client):
    r = client.post("/demo/seed")
    assert r.status_code == 200
    assert r.json() == {"created": 10}
    assert len(client.get("/flags").json()) >= 1
