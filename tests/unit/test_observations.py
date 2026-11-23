from bughunter.core.config import MAX_OBSERVATION_TEXT, TRUNCATION_MARKER
from bughunter.core.observations import (
    EpisodeStatus,
    build_observation_space,
    make_observation,
    sanitize_text,
)


def test_sanitize_replaces_non_printable_and_normalises_newlines() -> None:
    assert sanitize_text("café\r\nok\x00") == "caf?\nok?"


def test_sanitize_truncates_with_marker() -> None:
    text = sanitize_text("x" * (MAX_OBSERVATION_TEXT + 50))
    assert len(text) == MAX_OBSERVATION_TEXT
    assert text.endswith(TRUNCATION_MARKER)


def test_observation_with_arbitrary_text_is_in_space() -> None:
    space = build_observation_space(max_steps=10)
    obs = make_observation(
        task="Fix {it}!\n\ttabs & symbols ~`|",
        last_result="ünïcødé " * 3000,
        steps_remaining=10,
        status=EpisodeStatus.RUNNING,
    )
    assert space.contains(obs)


def test_empty_text_is_in_space() -> None:
    space = build_observation_space(max_steps=3)
    assert space.contains(make_observation("", "", 0, EpisodeStatus.SUBMITTED))
