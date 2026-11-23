"""BugHunter: an evaluation gym for AI coding agents that debug and repair software."""

from gymnasium.envs.registration import register

__version__ = "0.1.0"

register(
    id="BugHunter-v0",
    entry_point="bughunter.core.environment:BugHunterEnv",
    kwargs={"challenge_id": "API-001"},
)

__all__ = ["__version__"]
