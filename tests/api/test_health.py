"""Health endpoint integration tests."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_reports_status_and_database_counts() -> None:
    """Health responds with service status and populated table-count details."""
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert {"companies", "financial_ratios", "financial_statements", "sectors"}.issubset(
        payload["db_row_counts"]
    )
