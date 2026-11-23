from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bughunter.challenges.base import Challenge, ChallengeSpec, ScoringWeights
from bughunter.challenges.registry import ChallengeNotFoundError, ChallengeRegistry


def test_registry_discovers_api001(api001: Challenge) -> None:
    assert ChallengeRegistry().ids() == ["API-001"]
    assert api001.spec.name == "User Lookup Failure"
    assert api001.spec.workspace.editable_paths == ("app",)


def test_unknown_challenge_lists_available_ids() -> None:
    with pytest.raises(ChallengeNotFoundError, match="API-001"):
        ChallengeRegistry().get("NOPE-999")


def test_weights_must_sum_to_100() -> None:
    with pytest.raises(ValidationError, match="sum to 100"):
        ScoringWeights(hidden=50, public=15, regression=20, edge_cases=10, valid_submission=0)


def test_spec_rejects_unknown_fields_and_missing_submit(api001: Challenge) -> None:
    raw = yaml.safe_load((api001.root / "challenge.yaml").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        ChallengeSpec.model_validate({**raw, "surprise": True})
    with pytest.raises(ValidationError, match="submit_solution"):
        ChallengeSpec.model_validate({**raw, "allowed_tools": ["list_files"]})


def test_challenge_layout_is_validated(api001: Challenge, tmp_path: Path) -> None:
    (tmp_path / "challenge.yaml").write_bytes((api001.root / "challenge.yaml").read_bytes())
    with pytest.raises(FileNotFoundError, match="missing directories"):
        Challenge.load(tmp_path)


def test_task_text_states_every_verified_behaviour(api001: Challenge) -> None:
    # Hidden tests may only check behaviour the agent was told about.
    task = api001.spec.task
    for requirement in ("404", '{"detail": "User not found"}', "422", "zero and negative"):
        assert requirement in task
