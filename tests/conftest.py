from collections.abc import Iterator

import pytest

from bughunter.challenges.base import Challenge
from bughunter.challenges.registry import default_registry
from bughunter.core.environment import BugHunterEnv
from bughunter.sandbox.workspace import Workspace


@pytest.fixture(scope="session")
def api001() -> Challenge:
    return default_registry().get("API-001")


@pytest.fixture
def workspace(api001: Challenge) -> Iterator[Workspace]:
    ws = Workspace.create(api001)
    yield ws
    ws.cleanup()


@pytest.fixture
def env() -> Iterator[BugHunterEnv]:
    environment = BugHunterEnv("API-001")
    yield environment
    environment.close()
