"""Calibrates the API-001 verifier against known submissions, and runs full episodes."""

import pytest

from bughunter.challenges.base import Challenge, TestCategory
from bughunter.core.actions import make_action
from bughunter.core.environment import BugHunterEnv
from bughunter.core.observations import EpisodeStatus
from bughunter.evaluation.evaluator import Evaluator
from bughunter.evaluation.report import EvaluationReport, FailureCategory
from bughunter.sandbox.workspace import Workspace

from helpers import apply_reference, reference_source, write

pytestmark = pytest.mark.integration

STARTER_LOOKUP = "        return self._users[user_id]\n"


def evaluate(challenge: Challenge, workspace: Workspace) -> EvaluationReport:
    return Evaluator().evaluate(challenge, workspace)


def category(report: EvaluationReport, name: TestCategory) -> tuple[int, int]:
    score = next(c for c in report.categories if c.category is name)
    return score.passed, score.total


def replace_lookup(workspace: Workspace, body: str) -> None:
    path = workspace.root / "app" / "repository.py"
    source = path.read_text(encoding="utf-8")
    assert STARTER_LOOKUP in source
    path.write_text(source.replace(STARTER_LOOKUP, body), encoding="utf-8")


def test_reference_solution_scores_100(api001: Challenge, workspace: Workspace) -> None:
    apply_reference(api001, workspace)
    report = evaluate(api001, workspace)
    assert report.evaluation_error is None
    assert report.score == 100
    assert report.resolved
    assert report.failure_category is FailureCategory.NONE
    assert report.sandbox_isolated is False


def test_starter_reproduces_the_bug(api001: Challenge, workspace: Workspace) -> None:
    write(workspace, "app/main.py", (workspace.root / "app/main.py").read_text() + "\n# noop\n")
    report = evaluate(api001, workspace)
    assert category(report, TestCategory.HIDDEN) == (0, 12)
    assert category(report, TestCategory.PUBLIC) == (2, 4)
    assert category(report, TestCategory.REGRESSION) == (6, 6)
    # A comment-only edit earns nothing: supporting credit is gated on hidden tests.
    assert report.score == 0
    assert report.failure_category is FailureCategory.BUG_NOT_RESOLVED


def test_unchanged_submission_scores_zero(api001: Challenge, workspace: Workspace) -> None:
    report = evaluate(api001, workspace)
    assert report.score == 0
    assert report.failure_category is FailureCategory.NO_CHANGES


def test_off_by_one_fix_earns_partial_credit(api001: Challenge, workspace: Workspace) -> None:
    # A plausible but wrong fix: treats IDs as 1-based positions instead of identifiers.
    replace_lookup(
        workspace,
        "        if 1 <= user_id <= len(self._users):\n"
        "            return self._users[user_id - 1]\n"
        "        return None\n",
    )
    report = evaluate(api001, workspace)
    hidden_passed, hidden_total = category(report, TestCategory.HIDDEN)
    assert 0 < hidden_passed < hidden_total
    assert 0 < report.score < 60
    assert not report.resolved
    assert report.failure_category is FailureCategory.BUG_NOT_RESOLVED


def test_fix_that_changes_validation_contract_loses_edge_points(
    api001: Challenge, workspace: Workspace
) -> None:
    apply_reference(api001, workspace)
    main = workspace.root / "app" / "main.py"
    source = main.read_text(encoding="utf-8")
    source = source.replace("from fastapi import FastAPI", "from fastapi import FastAPI, Path")
    source = source.replace("user_id: int)", "user_id: int = Path(gt=0))")
    main.write_text(source, encoding="utf-8")
    report = evaluate(api001, workspace)
    assert report.resolved
    assert (
        category(report, TestCategory.EDGE_CASES)[0] < category(report, TestCategory.EDGE_CASES)[1]
    )
    assert report.failure_category is FailureCategory.EDGE_CASES_FAILING
    assert 90 <= report.score < 100


def test_fix_that_breaks_listing_is_a_regression(api001: Challenge, workspace: Workspace) -> None:
    apply_reference(api001, workspace)
    path = workspace.root / "app" / "repository.py"
    source = path.read_text(encoding="utf-8").replace(
        "return list(self._users)", "return sorted(self._users, key=lambda u: u.name)"
    )
    path.write_text(source, encoding="utf-8")
    report = evaluate(api001, workspace)
    assert category(report, TestCategory.HIDDEN) == (12, 12)
    assert not report.resolved
    assert report.failure_category is FailureCategory.REGRESSION
    assert report.score < 100


def test_import_crash_fails_every_test(api001: Challenge, workspace: Workspace) -> None:
    write(workspace, "app/repository.py", "raise RuntimeError('boom')\n")
    report = evaluate(api001, workspace)
    assert report.evaluation_error is None
    assert report.score == 0
    # Every suite still ran (no aborted run, no vanished tests) and nothing passed.
    for name in TestCategory:
        passed, total = category(report, name)
        assert total > 0, name
        assert passed == 0, name


def test_process_exit_during_import_is_an_evaluation_error(
    api001: Challenge, workspace: Workspace
) -> None:
    write(workspace, "app/repository.py", "import os\nos._exit(0)\n")
    report = evaluate(api001, workspace)
    assert report.score == 0
    assert report.evaluation_error is not None
    assert report.failure_category is FailureCategory.EVALUATION_ERROR


def test_agent_summary_hides_hidden_test_names(api001: Challenge, workspace: Workspace) -> None:
    apply_reference(api001, workspace)
    report = evaluate(api001, workspace)
    summary = report.agent_summary()
    assert "100.0/100" in summary
    assert all(test.name not in summary for test in report.tests)
    assert "test_" not in summary


def test_full_episode_through_tools_scores_100(api001: Challenge) -> None:
    """The Sprint 1 milestone: explore, edit, test and submit via the environment."""
    env = BugHunterEnv("API-001")
    try:
        obs, _ = env.reset(seed=7)
        assert "API-001" in obs["task"]

        def act(tool: str, **args: object) -> tuple[dict[str, object], float, bool, bool, dict]:
            obs, reward, terminated, truncated, info = env.step(make_action(tool, **args))
            assert env.observation_space.contains(obs)
            return obs, float(reward), terminated, truncated, info

        act("list_files")
        act("search_code", pattern="get_user")
        act("read_file", path="app/repository.py")
        obs, *_ = act("run_command", command="pytest -q")
        assert "2 failed" in str(obs["last_result"])

        fixed = reference_source(api001, "app/repository.py")
        _, _, _, _, info = act("edit_file", path="app/repository.py", content=fixed)
        assert info["ok"]
        obs, *_ = act("run_command", command="python -m pytest -q")
        assert "4 passed" in str(obs["last_result"])

        obs, reward, terminated, truncated, info = act("submit_solution")
        assert (reward, terminated, truncated) == (100.0, True, False)
        assert obs["status"] == EpisodeStatus.SUBMITTED
        assert "score 100.0/100" in str(obs["last_result"])
        assert info["evaluation"]["resolved"] is True
        assert info["episode"]["steps_taken"] == 7
        assert info["episode"]["tool_counts"]["run_command"] == 2
    finally:
        env.close()
