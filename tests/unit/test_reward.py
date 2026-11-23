import pytest

from bughunter.challenges.base import ScoringWeights, TestCategory
from bughunter.evaluation.report import (
    FailureCategory,
    IntegrityReport,
    IntegrityViolation,
    TestCaseResult,
    TestOutcome,
)
from bughunter.evaluation.reward import compute_score

WEIGHTS = ScoringWeights(hidden=50, public=15, regression=20, edge_cases=10, valid_submission=5)
CHANGED = IntegrityReport(changed_files=("app/repository.py",))


def results(**pass_fail: tuple[int, int]) -> list[TestCaseResult]:
    out: list[TestCaseResult] = []
    for name, (passed, failed) in pass_fail.items():
        category = TestCategory(name)
        out += [TestCaseResult(category=category, name="t", outcome=TestOutcome.PASSED)] * passed
        out += [TestCaseResult(category=category, name="t", outcome=TestOutcome.FAILED)] * failed
    return out


ALL_PASS = results(hidden=(4, 0), public=(2, 0), regression=(3, 0), edge_cases=(2, 0))


def test_perfect_submission_scores_100() -> None:
    breakdown = compute_score(WEIGHTS, ALL_PASS, CHANGED, None)
    assert breakdown.score == 100
    assert breakdown.resolved
    assert breakdown.failure_category is FailureCategory.NONE


def test_supporting_credit_is_gated_by_hidden_pass_rate() -> None:
    unfixed = results(hidden=(0, 4), public=(2, 0), regression=(3, 0), edge_cases=(2, 0))
    assert compute_score(WEIGHTS, unfixed, CHANGED, None).score == 0

    half = results(hidden=(2, 2), public=(2, 0), regression=(3, 0), edge_cases=(2, 0))
    breakdown = compute_score(WEIGHTS, half, CHANGED, None)
    # 50*0.5 + (15 + 20 + 10 + 5) * 0.5
    assert breakdown.score == pytest.approx(50)
    assert breakdown.failure_category is FailureCategory.BUG_NOT_RESOLVED
    assert not breakdown.resolved


@pytest.mark.parametrize(
    ("integrity", "error", "failure"),
    [
        (
            IntegrityReport(
                violations=(IntegrityViolation(kind="protected", path="tests/x", detail="d"),),
                changed_files=("app/a.py",),
            ),
            None,
            FailureCategory.TAMPERING,
        ),
        (IntegrityReport(), None, FailureCategory.NO_CHANGES),
        (CHANGED, "verifier timed out", FailureCategory.EVALUATION_ERROR),
    ],
)
def test_disqualified_submissions_score_zero(
    integrity: IntegrityReport, error: str | None, failure: FailureCategory
) -> None:
    breakdown = compute_score(WEIGHTS, ALL_PASS, integrity, error)
    assert breakdown.score == 0
    assert not breakdown.resolved
    assert breakdown.failure_category is failure


def test_empty_category_earns_nothing() -> None:
    no_hidden = results(public=(2, 0), regression=(3, 0), edge_cases=(2, 0))
    breakdown = compute_score(WEIGHTS, no_hidden, CHANGED, None)
    assert breakdown.score == 0
    assert not breakdown.resolved


def test_failure_category_precedence() -> None:
    regressed = results(hidden=(4, 0), public=(2, 0), regression=(2, 1), edge_cases=(2, 0))
    assert compute_score(WEIGHTS, regressed, CHANGED, None).failure_category is (
        FailureCategory.REGRESSION
    )
    edges = results(hidden=(4, 0), public=(2, 0), regression=(3, 0), edge_cases=(1, 1))
    breakdown = compute_score(WEIGHTS, edges, CHANGED, None)
    assert breakdown.failure_category is FailureCategory.EDGE_CASES_FAILING
    assert breakdown.resolved  # The reported bug is fixed; edge-case gaps cost points only.
    assert breakdown.score == pytest.approx(95)


def test_skipped_and_errored_tests_count_as_failures() -> None:
    mixed = [
        TestCaseResult(category=TestCategory.HIDDEN, name="a", outcome=TestOutcome.PASSED),
        TestCaseResult(category=TestCategory.HIDDEN, name="b", outcome=TestOutcome.SKIPPED),
        TestCaseResult(category=TestCategory.HIDDEN, name="c", outcome=TestOutcome.ERROR),
    ]
    hidden = compute_score(WEIGHTS, mixed, CHANGED, None).categories[0]
    assert (hidden.passed, hidden.total) == (1, 3)
