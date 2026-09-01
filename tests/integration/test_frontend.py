from fastapi.testclient import TestClient

from app.main import create_app


def test_root_serves_dashboard() -> None:
    response = TestClient(create_app()).get("/")
    assert response.status_code == 200
    assert "AI Sales Lead Qualifier" in response.text
    assert 'id="lead-form"' in response.text
    assert 'id="history-list"' in response.text
