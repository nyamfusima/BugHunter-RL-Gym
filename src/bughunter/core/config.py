"""Global constants shared by the environment, tools and evaluator."""

import string

#: Characters allowed in Gymnasium ``Text`` spaces. Tool output is sanitised to this set.
TEXT_CHARSET: str = string.printable

#: Maximum length of any text observation field. Longer output is truncated with a marker.
MAX_OBSERVATION_TEXT: int = 10_000

#: Maximum length of the JSON-encoded tool arguments in an action.
MAX_ACTION_ARGS_TEXT: int = 100_000

#: Hard ceiling on a challenge's step budget (keeps observation spaces bounded).
MAX_STEPS_CEILING: int = 500

#: Size limits applied to agent file operations.
MAX_READ_BYTES: int = 1_000_000
MAX_WRITE_BYTES: int = 200_000
MAX_LIST_ENTRIES: int = 500
MAX_SEARCH_RESULTS: int = 200
MAX_SEARCH_PATTERN_LENGTH: int = 200

#: Limits applied to the agent's editable files at submission time.
MAX_SUBMISSION_FILES: int = 200
MAX_SUBMISSION_BYTES: int = 2_000_000

#: Directory and file names that are build artefacts, ignored by listings and integrity checks.
IGNORED_DIR_NAMES: frozenset[str] = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache"})
IGNORED_FILE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")

TRUNCATION_MARKER: str = "\n...[output truncated]"
