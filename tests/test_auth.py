import pytest

from tests.conftest import ADMIN


def test_missing_key_is_401_for_ingestion(client, legit):
    r = client.post("/transactions", json={"idempotency_key": "no-key-0001", "features": legit})
    assert r.status_code == 401


def test_analyst_cannot_post_transactions(client, legit):
    r = client.post("/transactions", headers={"X-API-Key": "not-admin"},
                    json={"idempotency_key": "analyst-0001", "features": legit})
    assert r.status_code == 401


@pytest.mark.parametrize("headers", [{}, ADMIN], ids=["public", "admin"])
def test_public_and_admin_can_read_flags_and_stats(client, headers):
    assert client.get("/flags", headers=headers).status_code == 200
    assert client.get("/stats", headers=headers).status_code == 200


def test_dashboard_endpoints_are_public(client):
    assert client.get("/flags").status_code == 200
    assert client.get("/stats").status_code == 200


def test_health_needs_no_key(client):
    assert client.get("/health").status_code == 200
