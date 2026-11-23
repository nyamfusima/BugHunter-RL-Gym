"""Challenge specification (``challenge.yaml``) and the on-disk challenge layout.

A challenge directory contains::

    challenge.yaml    # this specification
    starter/          # the broken project; copied into the agent's workspace
    public_tests/     # tests the agent can see; copied into <workspace>/tests
    verifier/         # TRUSTED: hidden test suites, one sub-directory per category
    reference/        # TRUSTED: a known-good solution, used only to validate the verifier

Only ``starter/`` and ``public_tests/`` ever reach the agent.
"""

from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bughunter.core.actions import ToolName
from bughunter.core.config import MAX_STEPS_CEILING


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class TestCategory(StrEnum):
    """Scored test categories. Verifier suites live in ``verifier/<category>/``."""

    __test__ = False  # not a pytest test class

    HIDDEN = "hidden"
    PUBLIC = "public"
    REGRESSION = "regression"
    EDGE_CASES = "edge_cases"

    @property
    def is_verifier_suite(self) -> bool:
        return self is not TestCategory.PUBLIC


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(_Spec):
    max_steps: int = Field(ge=1, le=MAX_STEPS_CEILING)
    time_limit_seconds: float = Field(gt=0)
    command_timeout_seconds: float = Field(gt=0)


class WorkspaceSpec(_Spec):
    #: Workspace-relative directories the agent is allowed to modify. Everything else is
    #: protected: modifying it is treated as tampering.
    editable_paths: tuple[str, ...] = Field(min_length=1)
    public_tests_dir: str = "tests"


class ScoringWeights(_Spec):
    hidden: float = Field(ge=0)
    public: float = Field(ge=0)
    regression: float = Field(ge=0)
    edge_cases: float = Field(ge=0)
    valid_submission: float = Field(ge=0)

    @model_validator(mode="after")
    def _sum_to_100(self) -> Self:
        total = self.hidden + self.public + self.regression + self.edge_cases
        total += self.valid_submission
        if abs(total - 100.0) > 1e-9:
            raise ValueError(f"scoring weights must sum to 100, got {total}")
        return self

    def for_category(self, category: TestCategory) -> float:
        return float(getattr(self, category.value))


class EvaluationSpec(_Spec):
    timeout_seconds: float = Field(gt=0)
    weights: ScoringWeights


class ChallengeSpec(_Spec):
    id: str = Field(pattern=r"^[A-Z]+-\d{3}$")
    name: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    category: str
    difficulty: Difficulty
    task: str = Field(min_length=1)
    limits: Limits
    workspace: WorkspaceSpec
    allowed_tools: tuple[str, ...]
    #: Command prefixes the agent may run, e.g. ``[["pytest"], ["python", "-m", "pytest"]]``.
    allowed_commands: tuple[tuple[str, ...], ...] = ()
    evaluation: EvaluationSpec

    @model_validator(mode="after")
    def _check_tools(self) -> Self:
        tools = {ToolName.from_slug(slug) for slug in self.allowed_tools}
        if ToolName.SUBMIT_SOLUTION not in tools:
            raise ValueError("allowed_tools must include submit_solution")
        return self

    @property
    def allowed_tool_names(self) -> frozenset[ToolName]:
        return frozenset(ToolName.from_slug(slug) for slug in self.allowed_tools)


class Challenge:
    """A challenge specification bound to its asset directory."""

    SPEC_FILE = "challenge.yaml"

    def __init__(self, root: Path, spec: ChallengeSpec) -> None:
        self.root = root
        self.spec = spec

    @classmethod
    def load(cls, root: Path) -> "Challenge":
        raw = yaml.safe_load((root / cls.SPEC_FILE).read_text(encoding="utf-8"))
        challenge = cls(root, ChallengeSpec.model_validate(raw))
        challenge.validate_layout()
        return challenge

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def starter_dir(self) -> Path:
        return self.root / "starter"

    @property
    def public_tests_dir(self) -> Path:
        return self.root / "public_tests"

    @property
    def verifier_dir(self) -> Path:
        return self.root / "verifier"

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"

    @cached_property
    def verifier_categories(self) -> tuple[TestCategory, ...]:
        return tuple(c for c in TestCategory if c.is_verifier_suite)

    def validate_layout(self) -> None:
        required = [self.starter_dir, self.public_tests_dir, self.verifier_dir]
        required += [self.verifier_dir / c.value for c in self.verifier_categories]
        missing = [str(p.relative_to(self.root)) for p in required if not p.is_dir()]
        if missing:
            raise FileNotFoundError(f"challenge {self.id} is missing directories: {missing}")
        for editable in self.spec.workspace.editable_paths:
            if not (self.starter_dir / editable).exists():
                raise FileNotFoundError(f"editable path {editable!r} not found in starter/")

    def __repr__(self) -> str:
        return f"Challenge({self.id!r}, {self.spec.name!r})"
