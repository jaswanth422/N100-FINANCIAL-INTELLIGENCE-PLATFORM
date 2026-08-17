"""Company endpoint integration tests."""

from fastapi.testclient import TestClient

from api.main import app

CLIENT = TestClient(app)


def test_company_directory_returns_all_companies() -> None:
    """The directory endpoint returns the complete 92-company universe."""
    response = CLIENT.get("/api/v1/companies")
    assert response.status_code == 200
    assert len(response.json()) == 92


def test_tcs_profile_and_unknown_ticker_status() -> None:
    """Known companies return data while unknown tickers return 404."""
    response = CLIENT.get("/api/v1/companies/TCS")
    assert response.status_code == 200
    assert response.json()["id"] == "TCS"
    assert CLIENT.get("/api/v1/companies/INVALID").status_code == 404
