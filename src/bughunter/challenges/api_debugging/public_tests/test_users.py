from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_users_returns_all_users() -> None:
    response = client.get("/users")
    assert response.status_code == 200
    assert len(response.json()) == 5


def test_get_user_returns_requested_user() -> None:
    response = client.get("/users/2")
    assert response.status_code == 200
    assert response.json()["id"] == 2
    assert response.json()["name"] == "Alan Turing"


def test_get_unknown_user_returns_404() -> None:
    response = client.get("/users/1000")
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}
