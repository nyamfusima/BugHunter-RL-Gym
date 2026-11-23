"""Hidden tests: is the reported lookup bug actually resolved?"""

import pytest
from fastapi.testclient import TestClient

from conftest import EXPECTED_USERS, NOT_FOUND_BODY


@pytest.mark.parametrize("expected", EXPECTED_USERS, ids=lambda u: f"user-{u['id']}")
def test_each_existing_user_is_returned_by_its_id(
    client: TestClient, expected: dict[str, object]
) -> None:
    response = client.get(f"/users/{expected['id']}")
    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize("missing_id", [3, 5, 6, 8])
def test_ids_in_gaps_between_users_are_not_found(client: TestClient, missing_id: int) -> None:
    response = client.get(f"/users/{missing_id}")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


@pytest.mark.parametrize("missing_id", [10, 50, 1000])
def test_ids_beyond_the_last_user_are_not_found(client: TestClient, missing_id: int) -> None:
    response = client.get(f"/users/{missing_id}")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
