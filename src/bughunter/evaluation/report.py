"""Structured evaluation results.

The full :class:`EvaluationReport` (including individual hidden test names) is for the
benchmark operator. Agents only ever see :meth:`EvaluationReport.agent_summary`, so hidden
test identities do not leak into later episodes through an agent's memory.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bughunter.challenges.base import TestCategory


class TestOutcome(StrEnum):
    __test__ = False

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class FailureCategory(StrEnum):
    NONE = "none"
    TAMPERING = "tampering"
    NO_CHANGES = "no_changes"
    EVALUATION_ERROR = "evaluation_error"
    BUG_NOT_RESOLVED = "bug_not_resolved"
    REGRESSION = "regression"
    PUBLIC_TESTS_FAILING = "public_tests_failing"
    EDGE_CASES_FAILING = "edge_cases_failing"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class TestCaseResult(_Model):
    __test__ = False

    category: TestCategory
    name: str
    outcome: TestOutcome


class CategoryScore(_Model):
    category: TestCategory
    passed: int
    total: int
    pass_rate: float
    max_points: float
    points: float


class IntegrityViolation(_Model):
    kind: str
    path: str
    detail: str


class IntegrityReport(_Model):
    violations: tuple[IntegrityViolation, ...] = ()
    changed_files: tuple[str, ...] = ()

    @property
    def tampered(self) -> bool:
        return bool(self.violations)

    @property
    def no_changes(self) -> bool:
        return not self.changed_files


class EvaluationReport(_Model):
    challenge_id: str
    challenge_version: str
    score: float = Field(ge=0, le=100)
    max_score: float = 100.0
    resolved: bool
    failure_category: FailureCategory
    categories: tuple[CategoryScore, ...]
    valid_submission_points: float
    integrity: IntegrityReport
    tests: tuple[TestCaseResult, ...]
    evaluation_error: str | None = None
    sandbox_isolated: bool
    duration_seconds: float

    def agent_summary(self) -> str:
        lines = [
            f"Submission evaluated: score {self.score:.1f}/{self.max_score:.0f}",
            f"Resolved: {'yes' if self.resolved else 'no'}",
            f"Outcome: {self.failure_category.value}",
        ]
        for cat in self.categories:
            lines.append(f"  {cat.category.value}: {cat.passed}/{cat.total} tests passed")
        if self.integrity.tampered:
            lines.append("Integrity violations were detected; the submission scores zero.")
        if self.evaluation_error:
            lines.append("The evaluation could not complete; the submission scores zero.")
        return "\n".join(lines)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
