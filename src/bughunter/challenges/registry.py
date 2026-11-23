"""Discovers and loads challenges from the package's challenge directories."""

from functools import cache
from pathlib import Path

from bughunter.challenges.base import Challenge

CHALLENGES_ROOT = Path(__file__).resolve().parent


class ChallengeNotFoundError(KeyError):
    pass


class ChallengeRegistry:
    def __init__(self, root: Path = CHALLENGES_ROOT) -> None:
        self._challenges: dict[str, Challenge] = {}
        for spec_file in sorted(root.glob(f"*/{Challenge.SPEC_FILE}")):
            challenge = Challenge.load(spec_file.parent)
            if challenge.id in self._challenges:
                raise ValueError(f"duplicate challenge id {challenge.id}")
            self._challenges[challenge.id] = challenge

    def get(self, challenge_id: str) -> Challenge:
        try:
            return self._challenges[challenge_id]
        except KeyError:
            known = ", ".join(sorted(self._challenges)) or "none"
            raise ChallengeNotFoundError(
                f"unknown challenge {challenge_id!r} (available: {known})"
            ) from None

    def ids(self) -> list[str]:
        return sorted(self._challenges)

    def __len__(self) -> int:
        return len(self._challenges)


@cache
def default_registry() -> ChallengeRegistry:
    return ChallengeRegistry()
