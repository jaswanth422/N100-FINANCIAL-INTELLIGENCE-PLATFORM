"""Sector endpoint integration tests."""

from fastapi.testclient import TestClient

from api.main import app


def test_sector_summary_and_it_alias() -> None:
    """Sector summary is populated and IT alias returns only IT companies."""
    client = TestClient(app)
    response = client.get("/api/v1/sectors")
    assert response.status_code == 200
    assert len(response.json()) == 10
    members = client.get("/api/v1/sectors/IT/companies")
    assert members.status_code == 200
    assert all(item["broad_sector"] == "Information Technology" for item in members.json())
