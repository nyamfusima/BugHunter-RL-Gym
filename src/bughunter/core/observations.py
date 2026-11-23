"""Observation contract: the Gymnasium observation space and observation construction."""

from enum import IntEnum
from typing import Any

import numpy as np
from gymnasium import spaces

from bughunter.core.config import MAX_OBSERVATION_TEXT, TEXT_CHARSET, TRUNCATION_MARKER

_ALLOWED_CHARS = frozenset(TEXT_CHARSET)


class EpisodeStatus(IntEnum):
    RUNNING = 0
    SUBMITTED = 1
    TRUNCATED_STEPS = 2
    TRUNCATED_TIME = 3


def text_space(max_length: int = MAX_OBSERVATION_TEXT) -> spaces.Text:
    return spaces.Text(max_length=max_length, min_length=0, charset=TEXT_CHARSET)


def build_observation_space(max_steps: int) -> spaces.Dict:
    return spaces.Dict(
        {
            "task": text_space(),
            "last_result": text_space(),
            "steps_remaining": spaces.Discrete(max_steps + 1),
            "status": spaces.Discrete(len(EpisodeStatus)),
        }
    )


def sanitize_text(text: str, max_length: int = MAX_OBSERVATION_TEXT) -> str:
    """Make arbitrary tool output fit a ``Text`` space: printable ASCII, bounded length.

    Characters outside the charset are replaced with ``?`` (so non-ASCII source is lossy in
    observations; the files on disk are untouched). Over-long text is truncated with a marker.
    """
    text = text.replace("\r\n", "\n")
    cleaned = "".join(ch if ch in _ALLOWED_CHARS else "?" for ch in text)
    if len(cleaned) > max_length:
        keep = max_length - len(TRUNCATION_MARKER)
        cleaned = cleaned[:keep] + TRUNCATION_MARKER
    return cleaned


def make_observation(
    task: str, last_result: str, steps_remaining: int, status: EpisodeStatus
) -> dict[str, Any]:
    return {
        "task": sanitize_text(task),
        "last_result": sanitize_text(last_result),
        "steps_remaining": np.int64(steps_remaining),
        "status": np.int64(int(status)),
    }
