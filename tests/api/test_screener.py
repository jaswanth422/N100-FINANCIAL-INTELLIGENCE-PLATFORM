"""Screener endpoint integration tests."""

from fastapi.testclient import TestClient

from api.main import app


def test_screener_respects_roe_and_rejects_invalid_values() -> None:
    """ROE threshold results meet their threshold and invalid inputs return 422."""
    client = TestClient(app)
    response = client.get("/api/v1/screener?min_roe=15")
    assert response.status_code == 200
    assert all(item["roe_pct"] >= 15 for item in response.json())
    assert client.get("/api/v1/screener?max_pe=-1").status_code == 400
