from tests.conftest import ANALYST


def test_stats_on_empty_database(client):
    r = client.get("/stats", headers=ANALYST)
    assert r.status_code == 200
    assert r.json() == {"hourly": [], "score_buckets": [], "reviews": []}


def test_stats_shape_and_values(client, post_tx, legit, fraud):
    # legit row: Time -> hour_of_day computed from the row; fraud row is flagged.
    post_tx(legit, key="stats-legit-01")
    post_tx(fraud, key="stats-fraud-01")
    body = client.get("/stats", headers=ANALYST).json()

    assert set(body) == {"hourly", "score_buckets", "reviews"}
    for row in body["hourly"]:
        assert set(row) == {"hour_of_day", "n", "flagged_n", "flag_rate", "cumulative_flagged"}
        assert 0 <= row["hour_of_day"] <= 23
        assert 0.0 <= row["flag_rate"] <= 1.0
    assert sum(r["n"] for r in body["hourly"]) == 2
    assert sum(r["flagged_n"] for r in body["hourly"]) == 1
    # cumulative window sum ends at the total number of flags
    assert body["hourly"][-1]["cumulative_flagged"] == 1

    assert sum(r["n"] for r in body["score_buckets"]) == 2
    assert all(0 <= r["bucket"] <= 9 for r in body["score_buckets"])
    assert body["reviews"] == []


def test_stats_review_percentages(client, post_tx, fraud, legit, monkeypatch):
    from app import scoring
    stub = {"score": 0.99, "source": "model", "flagged": True, "explanation": []}
    monkeypatch.setattr(scoring, "score", lambda f: stub)
    ids = [post_tx(fraud, key=f"pct-key-000{i}").json()["id"] for i in range(3)]
    decisions = ["confirm_fraud", "confirm_fraud", "dismiss"]
    for tx_id, d in zip(ids, decisions):
        assert client.post(f"/flags/{tx_id}/review", headers=ANALYST,
                           json={"decision": d}).status_code == 200
    reviews = {r["decision"]: r for r in client.get("/stats", headers=ANALYST).json()["reviews"]}
    assert reviews["confirm_fraud"]["n"] == 2
    assert reviews["dismiss"]["n"] == 1
    assert round(reviews["confirm_fraud"]["pct"] + reviews["dismiss"]["pct"], 1) == 100.0
