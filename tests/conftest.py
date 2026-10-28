"""Shared test setup. Runs offline: no LLM key, no dataset, no real database.

The env vars below MUST be set before `app` is imported, because app/db.py reads
DATABASE_URL at import time and app/auth.py reads the API keys on each request.
"""
import json
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="sentinel-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["GROQ_API_KEY"] = "unused-in-tests"  # set so a developer's real key is never loaded

import pytest
from fastapi.testclient import TestClient

from app import llm, scoring
from app.db import Base, engine
from app.main import app

ADMIN = {"X-API-Key": "test-admin-key"}

# Two real rows from the held-out test split (public Kaggle data), so CI needs no dataset.
SAMPLES = json.loads((Path(__file__).parent / "sample_rows.json").read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any test that forgets to mock the LLM fails loudly instead of calling the network."""
    def boom():
        raise AssertionError("test tried to create a real LLM client")
    monkeypatch.setattr(llm, "_get_client", boom)


@pytest.fixture
def client():
    """Fresh empty database per test; the context manager runs the app lifespan (loads the model)."""
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def legit():
    return dict(SAMPLES["legit"])


@pytest.fixture
def fraud():
    return dict(SAMPLES["fraud"])


@pytest.fixture
def post_tx(client):
    """post_tx(features, key='k1234567') -> response, sent as admin."""
    def _post(features, key="key-00000001", headers=ADMIN):
        return client.post("/transactions", headers=headers,
                           json={"idempotency_key": key, "features": features})
    return _post


@pytest.fixture
def flagged_tx(client, monkeypatch, legit):
    """Creates one flagged transaction by forcing scoring.score to return a flagged result.

    Using a stub keeps the review tests independent of the model's exact output.
    """
    stub = {"score": 0.97, "source": "model", "flagged": True,
            "explanation": [{"feature": "V14", "contribution": 2.1, "value": -8.0}]}
    monkeypatch.setattr(scoring, "score", lambda features: stub)
    r = client.post("/transactions", headers=ADMIN,
                    json={"idempotency_key": "flagged-0001", "features": legit})
    assert r.status_code == 201
    return r.json()
