"""Trusted fixtures for the API-001 verifier.

The agent's application is imported lazily inside the fixture rather than at module import
time. That keeps test *collection* independent of the agent's code: if the agent's code fails
to import, every test errors (and is scored as failed) instead of silently disappearing.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

EXPECTED_USERS = [
    {"id": 1, "name": "Ada Lovelace", "email": "ada@example.com", "active": True},
    {"id": 2, "name": "Alan Turing", "email": "alan@example.com", "active": True},
    {"id": 4, "name": "Grace Hopper", "email": "grace@example.com", "active": False},
    {"id": 7, "name": "Edsger Dijkstra", "email": "edsger@example.com", "active": True},
    {"id": 9, "name": "Barbara Liskov", "email": "barbara@example.com", "active": True},
]

NOT_FOUND_BODY = {"detail": "User not found"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
