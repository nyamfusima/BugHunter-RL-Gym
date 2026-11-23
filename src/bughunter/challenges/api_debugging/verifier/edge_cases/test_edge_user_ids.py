"""Edge cases: boundary and malformed user IDs."""

import pytest
from fastapi.testclient import TestClient

from conftest import NOT_FOUND_BODY


@pytest.mark.parametrize("user_id", ["0", "-1", "-5"])
def test_non_positive_ids_are_not_found(client: TestClient, user_id: str) -> None:
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


def test_huge_id_is_not_found_rather_than_a_server_error(client: TestClient) -> None:
    response = client.get(f"/users/{10**20}")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


@pytest.mark.parametrize("user_id", ["abc", "1.5", "2abc"])
def test_non_integer_ids_are_rejected_as_validation_errors(
    client: TestClient, user_id: str
) -> None:
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 422


def test_not_found_response_is_json(client: TestClient) -> None:
    response = client.get("/users/3")
    assert response.headers["content-type"].startswith("application/json")
