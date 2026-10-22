import pytest

from tests.conftest import ADMIN, ANALYST


def test_missing_key_is_401(client, legit):
    assert client.get("/flags").status_code == 401
    r = client.post("/transactions", json={"idempotency_key": "no-key-0001", "features": legit})
    assert r.status_code == 401


def test_bad_key_is_401(client):
    assert client.get("/flags", headers={"X-API-Key": "wrong"}).status_code == 401


def test_analyst_cannot_post_transactions(client, legit):
    r = client.post("/transactions", headers=ANALYST,
                    json={"idempotency_key": "analyst-0001", "features": legit})
    assert r.status_code == 403


@pytest.mark.parametrize("headers", [ANALYST, ADMIN], ids=["analyst", "admin"])
def test_both_roles_can_read_flags_and_stats(client, headers):
    assert client.get("/flags", headers=headers).status_code == 200
    assert client.get("/stats", headers=headers).status_code == 200


def test_health_needs_no_key(client):
    assert client.get("/health").status_code == 200
