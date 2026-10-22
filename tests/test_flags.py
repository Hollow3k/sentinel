from tests.conftest import ADMIN, ANALYST


def test_review_flow(client, flagged_tx):
    tx_id = flagged_tx["id"]

    queue = client.get("/flags?reviewed=false", headers=ANALYST).json()
    assert [t["id"] for t in queue] == [tx_id]

    r = client.post(f"/flags/{tx_id}/review", headers=ANALYST,
                    json={"decision": "confirm_fraud", "note": "card stolen"})
    assert r.status_code == 200
    assert r.json() == {"transaction_id": tx_id, "decision": "confirm_fraud"}

    assert client.get("/flags?reviewed=false", headers=ANALYST).json() == []
    done = client.get("/flags?reviewed=true", headers=ANALYST).json()
    assert [t["id"] for t in done] == [tx_id]
    assert done[0]["reviewed"] is True

    reviews = client.get("/stats", headers=ANALYST).json()["reviews"]
    assert reviews == [{"decision": "confirm_fraud", "n": 1, "pct": 100.0}]


def test_flags_are_sorted_by_score_descending(client, post_tx, legit, fraud):
    post_tx(legit, key="sorted-legit-1")  # not flagged, must not appear
    post_tx(fraud, key="sorted-fraud-1")
    flags = client.get("/flags", headers=ANALYST).json()
    assert len(flags) == 1
    assert flags[0]["flagged"] is True


def test_review_unknown_id_is_404(client):
    r = client.post("/flags/9999/review", headers=ANALYST, json={"decision": "dismiss"})
    assert r.status_code == 404


def test_cannot_review_a_non_flagged_transaction(client, post_tx, legit):
    tx = post_tx(legit).json()
    assert tx["flagged"] is False
    r = client.post(f"/flags/{tx['id']}/review", headers=ANALYST, json={"decision": "dismiss"})
    assert r.status_code == 404


def test_invalid_review_decision_is_422(client, flagged_tx):
    r = client.post(f"/flags/{flagged_tx['id']}/review", headers=ANALYST,
                    json={"decision": "maybe"})
    assert r.status_code == 422


def test_review_requires_a_key(client, flagged_tx):
    r = client.post(f"/flags/{flagged_tx['id']}/review", json={"decision": "dismiss"})
    assert r.status_code == 401


def test_flags_limit_is_validated(client, flagged_tx):
    # A negative LIMIT is accepted by SQLite but is a 500 on Postgres, so reject it up front.
    assert client.get("/flags?limit=-1", headers=ADMIN).status_code == 422
    assert client.get("/flags?limit=0", headers=ADMIN).status_code == 422
    assert len(client.get("/flags?limit=1", headers=ADMIN).json()) == 1
