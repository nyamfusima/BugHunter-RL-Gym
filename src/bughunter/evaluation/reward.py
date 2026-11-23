"""Turns test results into a score out of 100.

Scoring rules:

1. Each category earns ``weight x pass_rate``. A category with no recorded tests earns 0.
2. **Hidden-test gating.** Public, regression, edge-case and valid-submission credit is
   multiplied by the hidden-test pass rate. Otherwise a trivial edit to the broken code
   would collect the regression points (the broken code already "preserves" behaviour it
   never touched) plus partial public and edge-case credit: 37.5/100 on API-001 for a
   comment-only change.
   Gating makes the score measure progress on the actual defect.
3. Tampering, an empty submission, or an evaluation that cannot complete scores 0.
4. Tool usage, time and step counts never affect the score; they are reported separately.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from bughunter.challenges.base import ScoringWeights, TestCategory
from bughunter.evaluation.report import (
    CategoryScore,
    FailureCategory,
    IntegrityReport,
    TestCaseResult,
    TestOutcome,
)

CATEGORY_ORDER = (
    TestCategory.HIDDEN,
    TestCategory.PUBLIC,
    TestCategory.REGRESSION,
    TestCategory.EDGE_CASES,
)


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    categories: tuple[CategoryScore, ...]
    valid_submission_points: float
    resolved: bool
    failure_category: FailureCategory


def _pass_rates(results: Sequence[TestCaseResult]) -> dict[TestCategory, tuple[int, int]]:
    counts = {category: (0, 0) for category in CATEGORY_ORDER}
    for result in results:
        passed, total = counts[result.category]
        counts[result.category] = (passed + (result.outcome is TestOutcome.PASSED), total + 1)
    return counts


def compute_score(
    weights: ScoringWeights,
    results: Sequence[TestCaseResult],
    integrity: IntegrityReport,
    evaluation_error: str | None,
) -> ScoreBreakdown:
    counts = _pass_rates(results)
    rates = {c: (p / t if t else 0.0) for c, (p, t) in counts.items()}
    disqualified = integrity.tampered or integrity.no_changes or evaluation_error is not None
    gate = 0.0 if disqualified else rates[TestCategory.HIDDEN]

    categories: list[CategoryScore] = []
    for category in CATEGORY_ORDER:
        passed, total = counts[category]
        weight = weights.for_category(category)
        if disqualified:
            points = 0.0
        elif category is TestCategory.HIDDEN:
            points = weight * rates[category]
        else:
            points = weight * rates[category] * gate
        categories.append(
            CategoryScore(
                category=category,
                passed=passed,
                total=total,
                pass_rate=rates[category],
                max_points=weight,
                points=round(points, 4),
            )
        )
    valid_points = 0.0 if disqualified else weights.valid_submission * gate
    score = round(sum(c.points for c in categories) + valid_points, 2)

    all_pass = all(counts[c][1] > 0 and rates[c] == 1.0 for c in CATEGORY_ORDER)
    resolved = not disqualified and all(
        counts[c][1] > 0 and rates[c] == 1.0
        for c in (TestCategory.HIDDEN, TestCategory.PUBLIC, TestCategory.REGRESSION)
    )

    if integrity.tampered:
        failure = FailureCategory.TAMPERING
    elif integrity.no_changes:
        failure = FailureCategory.NO_CHANGES
    elif evaluation_error is not None:
        failure = FailureCategory.EVALUATION_ERROR
    elif rates[TestCategory.HIDDEN] < 1.0:
        failure = FailureCategory.BUG_NOT_RESOLVED
    elif rates[TestCategory.REGRESSION] < 1.0:
        failure = FailureCategory.REGRESSION
    elif rates[TestCategory.PUBLIC] < 1.0:
        failure = FailureCategory.PUBLIC_TESTS_FAILING
    elif not all_pass:
        failure = FailureCategory.EDGE_CASES_FAILING
    else:
        failure = FailureCategory.NONE

    return ScoreBreakdown(
        score=score,
        categories=tuple(categories),
        valid_submission_points=round(valid_points, 4),
        resolved=resolved,
        failure_category=failure,
    )
