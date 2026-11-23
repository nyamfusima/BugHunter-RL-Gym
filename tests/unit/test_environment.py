import gymnasium as gym
import pytest
from gymnasium.utils.env_checker import check_env

import bughunter  # noqa: F401 - registers BugHunter-v0
from bughunter.challenges.base import Challenge
from bughunter.core.actions import ToolName, make_action
from bughunter.core.environment import BugHunterEnv
from bughunter.core.observations import EpisodeStatus


def test_gymnasium_env_checker_passes() -> None:
    env = BugHunterEnv("API-001")
    try:
        check_env(env, skip_render_check=True)
    finally:
        env.close()


def test_registered_with_gymnasium() -> None:
    env = gym.make("BugHunter-v0")
    try:
        obs, info = env.reset(seed=0)
        assert info["challenge_id"] == "API-001"
        assert info["sandbox_isolated"] is False
        assert env.observation_space.contains(obs)
    finally:
        env.close()


def test_reset_returns_task_and_full_budget(env: BugHunterEnv) -> None:
    obs, info = env.reset(seed=123)
    assert obs["task"].startswith("Challenge: API-001")
    assert obs["steps_remaining"] == env.challenge.spec.limits.max_steps
    assert obs["status"] == EpisodeStatus.RUNNING
    assert env.observation_space.contains(obs)
    assert set(info["allowed_tools"]) == {t.slug for t in ToolName}


def test_reset_creates_a_fresh_workspace(env: BugHunterEnv) -> None:
    env.reset()
    first = env.workspace.root
    env.step(make_action("edit_file", path="app/main.py", content="broken = True\n"))
    env.reset()
    assert not first.exists()
    assert "FastAPI" in (env.workspace.root / "app" / "main.py").read_text(encoding="utf-8")


def test_list_and_read_files(env: BugHunterEnv) -> None:
    env.reset()
    obs, reward, terminated, truncated, info = env.step(make_action("list_files"))
    assert "app/repository.py" in obs["last_result"]
    assert "tests/test_users.py" in obs["last_result"]
    assert (reward, terminated, truncated, info["ok"]) == (0.0, False, False, True)

    obs, *_ = env.step(make_action("read_file", path="app/repository.py", start_line=17))
    assert "return self._users[user_id]" in obs["last_result"]
    assert obs["steps_remaining"] == env.challenge.spec.limits.max_steps - 2


def test_search_code(env: BugHunterEnv) -> None:
    env.reset()
    obs, *_ = env.step(make_action("search_code", pattern="def get_user"))
    assert "app/repository.py:" in obs["last_result"]
    assert "app/main.py:" in obs["last_result"]
    obs, *_ = env.step(make_action("search_code", pattern=r"_users\[\w+\]", regex=True))
    assert obs["last_result"] == "app/repository.py:17: return self._users[user_id]"


def test_edit_file_replace_and_errors(env: BugHunterEnv) -> None:
    env.reset()
    obs, *_, info = env.step(
        make_action(
            "edit_file",
            path="app/repository.py",
            old_str="return self._users[user_id]",
            new_str="return next((u for u in self._users if u.id == user_id), None)",
        )
    )
    assert info["ok"], obs["last_result"]
    source = (env.workspace.root / "app" / "repository.py").read_text(encoding="utf-8")
    assert "u.id == user_id" in source

    obs, *_, info = env.step(
        make_action("edit_file", path="app/repository.py", old_str="no such text", new_str="x")
    )
    assert not info["ok"]
    assert "found 0 matches" in obs["last_result"]


def test_run_command_runs_public_tests_and_reproduces_the_bug(env: BugHunterEnv) -> None:
    env.reset()
    obs, *_, info = env.step(make_action("run_command", command="pytest -q"))
    assert info["ok"]
    assert "[exit code 1]" in obs["last_result"]
    assert "2 failed, 2 passed" in obs["last_result"]


def test_invalid_actions_consume_a_step_without_crashing(env: BugHunterEnv) -> None:
    env.reset()
    budget = env.challenge.spec.limits.max_steps
    for action in (
        {"tool": 1, "args": "{not json"},
        {"tool": 1, "args": "{}"},
        make_action("read_file", path="does/not/exist.py"),
    ):
        obs, reward, terminated, truncated, info = env.step(action)
        assert obs["last_result"].startswith("ERROR:")
        assert not info["ok"]
        assert (reward, terminated, truncated) == (0.0, False, False)
    assert obs["steps_remaining"] == budget - 3
    assert env.episode.summary()["invalid_actions"] == 3


def test_step_budget_truncates_without_reward(env: BugHunterEnv) -> None:
    env.reset()
    budget = env.challenge.spec.limits.max_steps
    for _ in range(budget - 1):
        *_, terminated, truncated, _info = env.step(make_action("list_files"))
        assert not (terminated or truncated)
    obs, reward, terminated, truncated, info = env.step(make_action("list_files"))
    assert (reward, terminated, truncated) == (0.0, False, True)
    assert obs["status"] == EpisodeStatus.TRUNCATED_STEPS
    assert obs["steps_remaining"] == 0
    assert info["episode"]["status"] == "truncated_steps"
    assert "evaluation" not in info
    with pytest.raises(RuntimeError, match="reset"):
        env.step(make_action("list_files"))


def test_time_limit_truncates_before_executing_the_action(env: BugHunterEnv) -> None:
    env.reset()
    env.episode.time_limit_seconds = 0.0
    obs, reward, terminated, truncated, _info = env.step(make_action("submit_solution"))
    assert (reward, terminated, truncated) == (0.0, False, True)
    assert obs["status"] == EpisodeStatus.TRUNCATED_TIME
    assert env.episode.report is None  # The late submission was never evaluated.


def test_step_before_reset_raises() -> None:
    env = BugHunterEnv("API-001")
    with pytest.raises(RuntimeError, match="reset"):
        env.step(make_action("list_files"))


def test_disallowed_tool_is_refused(env: BugHunterEnv) -> None:
    restricted = env.challenge.spec.model_copy(
        update={"allowed_tools": ("list_files", "submit_solution")}
    )
    env.challenge = Challenge(env.challenge.root, restricted)
    env.reset()
    obs, *_, info = env.step(make_action("read_file", path="app/main.py"))
    assert not info["ok"]
    assert "not allowed" in obs["last_result"]


def test_close_removes_workspace(env: BugHunterEnv) -> None:
    env.reset()
    root = env.workspace.root
    env.close()
    assert not root.exists()
