import json

import pytest

from bughunter.core.actions import (
    ActionError,
    EditFileArgs,
    ReadFileArgs,
    ToolName,
    make_action,
    parse_action,
)


def test_make_action_round_trips_through_parse() -> None:
    parsed = parse_action(make_action("read_file", path="app/main.py", start_line=2))
    assert parsed.tool is ToolName.READ_FILE
    assert parsed.args == ReadFileArgs(path="app/main.py", start_line=2)


def test_tool_indices_are_stable() -> None:
    # The Discrete action index is part of the public contract; reordering breaks agents.
    assert [t.slug for t in ToolName] == [
        "list_files",
        "read_file",
        "search_code",
        "run_command",
        "edit_file",
        "submit_solution",
    ]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ("not json", "JSON object"),
        ("", "JSON object"),
        ("[1, 2]", "JSON object"),
        ("42", "JSON object"),
        (json.dumps({"path": "x", "bogus": 1}), "bogus"),
        (json.dumps({}), "path"),
        (json.dumps({"path": "x", "start_line": 0}), "start_line"),
        (json.dumps({"path": "x", "start_line": 5, "end_line": 2}), "end_line"),
    ],
)
def test_invalid_read_file_args_raise_action_error(args: str, message: str) -> None:
    with pytest.raises(ActionError, match=message):
        parse_action({"tool": int(ToolName.READ_FILE), "args": args})


def test_unknown_tool_index_is_an_action_error() -> None:
    with pytest.raises(ActionError, match="unknown tool"):
        parse_action({"tool": 99, "args": "{}"})


@pytest.mark.parametrize("action", [None, "read", {"tool": 1}, {"tool": 1, "args": {}}])
def test_malformed_action_shape_is_a_type_error(action: object) -> None:
    with pytest.raises(TypeError):
        parse_action(action)


def test_edit_file_requires_exactly_one_mode() -> None:
    assert EditFileArgs(path="a.py", content="x").content == "x"
    assert EditFileArgs(path="a.py", old_str="a", new_str="b").new_str == "b"
    with pytest.raises(ValueError, match="either"):
        EditFileArgs(path="a.py")
    with pytest.raises(ValueError, match="either"):
        EditFileArgs(path="a.py", content="x", old_str="a", new_str="b")
    with pytest.raises(ValueError, match="together"):
        EditFileArgs(path="a.py", old_str="a")


def test_submit_takes_no_arguments() -> None:
    with pytest.raises(ActionError):
        parse_action(make_action("submit_solution", force=True))
