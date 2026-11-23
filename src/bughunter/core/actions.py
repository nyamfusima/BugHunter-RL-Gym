"""Action contract: which tools exist, their validated arguments, and action parsing.

A Gymnasium action is a dict ``{"tool": int, "args": str}``, where ``tool`` indexes
:class:`ToolName` and ``args`` is a JSON object holding that tool's arguments. Agents that
think in tool calls can build actions with :func:`make_action`.
"""

import json
from enum import IntEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from bughunter.core.config import MAX_SEARCH_PATTERN_LENGTH, MAX_WRITE_BYTES


class ToolName(IntEnum):
    """Tools available to agents. The integer value is the Gymnasium action index."""

    LIST_FILES = 0
    READ_FILE = 1
    SEARCH_CODE = 2
    RUN_COMMAND = 3
    EDIT_FILE = 4
    SUBMIT_SOLUTION = 5

    @property
    def slug(self) -> str:
        return self.name.lower()

    @classmethod
    def from_slug(cls, slug: str) -> "ToolName":
        try:
            return cls[slug.upper()]
        except KeyError:
            raise ValueError(f"unknown tool {slug!r}") from None


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListFilesArgs(_Args):
    path: str = "."


class ReadFileArgs(_Args):
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.start_line and self.end_line and self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class SearchCodeArgs(_Args):
    pattern: str = Field(min_length=1, max_length=MAX_SEARCH_PATTERN_LENGTH)
    path: str = "."
    regex: bool = False


class RunCommandArgs(_Args):
    command: str = Field(min_length=1, max_length=1_000)


class EditFileArgs(_Args):
    """Either replace a whole file (``content``) or one exact snippet (``old_str``/``new_str``)."""

    path: str
    content: str | None = Field(default=None, max_length=MAX_WRITE_BYTES)
    old_str: str | None = Field(default=None, min_length=1, max_length=MAX_WRITE_BYTES)
    new_str: str | None = Field(default=None, max_length=MAX_WRITE_BYTES)

    @model_validator(mode="after")
    def _check_mode(self) -> Self:
        whole_file = self.content is not None
        replace = self.old_str is not None or self.new_str is not None
        if whole_file == replace:
            raise ValueError("provide either 'content', or both 'old_str' and 'new_str'")
        if replace and (self.old_str is None or self.new_str is None):
            raise ValueError("'old_str' and 'new_str' must be provided together")
        return self


class SubmitSolutionArgs(_Args):
    pass


ToolArgs = (
    ListFilesArgs
    | ReadFileArgs
    | SearchCodeArgs
    | RunCommandArgs
    | EditFileArgs
    | SubmitSolutionArgs
)

ARGS_MODELS: dict[ToolName, type[_Args]] = {
    ToolName.LIST_FILES: ListFilesArgs,
    ToolName.READ_FILE: ReadFileArgs,
    ToolName.SEARCH_CODE: SearchCodeArgs,
    ToolName.RUN_COMMAND: RunCommandArgs,
    ToolName.EDIT_FILE: EditFileArgs,
    ToolName.SUBMIT_SOLUTION: SubmitSolutionArgs,
}


class ParsedAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool: ToolName
    args: ToolArgs


class ActionError(ValueError):
    """The action is well-formed for the action space but its arguments are invalid."""


def parse_action(action: Any) -> ParsedAction:
    """Validate a Gymnasium action and return the typed tool call.

    Raises:
        TypeError: the action does not have the shape of the action space (a caller bug).
        ActionError: the tool index or JSON arguments are invalid (an agent mistake; this
            is reported back to the agent as an error observation).
    """
    if not isinstance(action, dict) or set(action) != {"tool", "args"}:
        raise TypeError("action must be a dict with exactly the keys 'tool' and 'args'")
    raw_tool, raw_args = action["tool"], action["args"]
    if not isinstance(raw_args, str):
        raise TypeError("action['args'] must be a JSON string")
    try:
        tool = ToolName(int(raw_tool))
    except (TypeError, ValueError):
        raise ActionError(f"unknown tool index {raw_tool!r}") from None

    try:
        payload = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        raise ActionError(f"args for {tool.slug} must be a JSON object: {exc.msg}") from None
    if not isinstance(payload, dict):
        raise ActionError(f"args for {tool.slug} must be a JSON object")

    try:
        args = ARGS_MODELS[tool].model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'args'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ActionError(f"invalid args for {tool.slug}: {details}") from None
    return ParsedAction(tool=tool, args=args)  # type: ignore[arg-type]


def make_action(tool: ToolName | str, **args: Any) -> dict[str, Any]:
    """Build a Gymnasium action from a tool name and keyword arguments."""
    tool_name = ToolName.from_slug(tool) if isinstance(tool, str) else tool
    return {"tool": int(tool_name), "args": json.dumps(args)}
