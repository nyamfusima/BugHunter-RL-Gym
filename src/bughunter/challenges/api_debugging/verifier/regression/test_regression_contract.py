"""Regression tests: behaviour that worked before the fix must keep working."""

from fastapi.testclient import TestClient

from conftest import EXPECTED_USERS


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_users_returns_all_users_in_signup_order(client: TestClient) -> None:
    response = client.get("/users")
    assert response.status_code == 200
    assert response.json() == EXPECTED_USERS


def test_list_users_active_filter(client: TestClient) -> None:
    active = client.get("/users", params={"active": "true"}).json()
    inactive = client.get("/users", params={"active": "false"}).json()
    assert active == [u for u in EXPECTED_USERS if u["active"]]
    assert inactive == [u for u in EXPECTED_USERS if not u["active"]]


def test_user_response_contract_fields(client: TestClient) -> None:
    body = client.get("/users/1").json()
    assert set(body) == {"id", "name", "email", "active"}


def test_lookups_do_not_mutate_the_directory(client: TestClient) -> None:
    for user_id in (1, 3, 9, 1000, -1, 0):
        client.get(f"/users/{user_id}")
    assert client.get("/users").json() == EXPECTED_USERS


def test_user_id_path_parameter_remains_an_integer(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/users/{user_id}"]["get"]["parameters"]
    user_id = next(p for p in parameters if p["name"] == "user_id")
    assert user_id["in"] == "path"
    assert user_id["schema"]["type"] == "integer"
