"""The agent-facing tools must not reach outside the workspace or into trusted assets.

These are policy checks on the file and command tools. They are NOT a substitute for
process isolation (see README, "Known limitations").
"""

import os
import sys

import pytest

from bughunter.challenges.base import Challenge
from bughunter.core.actions import make_action
from bughunter.core.environment import BugHunterEnv
from bughunter.core.tools import redact_host_paths
from bughunter.sandbox.command_policy import CommandPolicy, CommandPolicyError
from bughunter.sandbox.workspace import Workspace, WorkspaceError


def test_workspace_contains_no_trusted_assets(workspace: Workspace) -> None:
    files = {str(p) for p in workspace.iter_files()}
    assert "app/repository.py" in files
    assert "tests/test_users.py" in files
    assert not any(part in f for f in files for part in ("verifier", "reference", "hidden"))
    assert "challenge.yaml" not in files


def test_workspace_is_outside_the_challenge_package(
    api001: Challenge, workspace: Workspace
) -> None:
    assert not workspace.root.is_relative_to(api001.root)


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "app/../../x",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        "\\\\server\\share\\x",
        "app\\..\\..\\x",
        "nul\x00byte",
    ],
)
def test_resolve_refuses_escaping_paths(workspace: Workspace, path: str) -> None:
    with pytest.raises(WorkspaceError):
        workspace.resolve(path)


def test_resolve_refuses_symlinks(
    workspace: Workspace, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    try:
        os.symlink(outside, workspace.root / "link", target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks requires extra privileges on this platform")
    with pytest.raises(WorkspaceError, match="symbolic"):
        workspace.resolve("link/anything")


@pytest.mark.parametrize(
    "path", ["tests/test_users.py", "pytest.ini", "conftest.py", "README.md", "../escape.py"]
)
def test_edit_file_only_writes_editable_paths(env: BugHunterEnv, path: str) -> None:
    env.reset()
    before = {str(p) for p in env.workspace.iter_files()}
    obs, *_, info = env.step(make_action("edit_file", path=path, content="x = 1\n"))
    assert not info["ok"]
    assert obs["last_result"].startswith("ERROR:")
    assert {str(p) for p in env.workspace.iter_files()} == before


@pytest.mark.parametrize(
    "command",
    [
        "python -c 'print(1)'",
        "ls",
        "cat /etc/passwd",
        "pytest; rm -rf /",
        "pytest -p some_plugin",
        "pytest --rootdir=/",
        "pytest -c ../other.ini",
        "pytest --confcutdir=..",
        "pytest --pyargs bughunter",
        "pytest ../",
        "pytest C:/Windows",
        "pytest -k",
        "pytest 'unterminated",
    ],
)
def test_command_policy_refuses(workspace: Workspace, command: str) -> None:
    policy = CommandPolicy((("pytest",), ("python", "-m", "pytest")))
    with pytest.raises(CommandPolicyError):
        policy.build_argv(command, workspace)


@pytest.mark.parametrize(
    "command",
    ["pytest", "python -m pytest -q", "pytest tests/test_users.py::test_health -x --tb=short"],
)
def test_command_policy_allows_test_runs(workspace: Workspace, command: str) -> None:
    policy = CommandPolicy((("pytest",), ("python", "-m", "pytest")))
    argv = policy.build_argv(command, workspace)
    assert argv[1:3] == ["-m", "pytest"]


def test_tool_output_never_reveals_the_host_workspace_path(env: BugHunterEnv) -> None:
    env.reset()
    secrets = {str(env.workspace.root), sys.prefix, sys.base_prefix, "site-packages"}
    secrets |= {s.replace("\\", "/") for s in secrets}
    for action in (
        make_action("list_files"),
        make_action("read_file", path="../outside"),
        make_action("run_command", command="pytest -v --tb=long"),
    ):
        obs, *_ = env.step(action)
        lowered = obs["last_result"].lower()
        leaked = [s for s in secrets if s.lower() in lowered]
        assert not leaked, obs["last_result"]


def test_redaction_covers_python_installation_paths(workspace: Workspace) -> None:
    relative = os.path.relpath(sys.prefix, workspace.root)
    text = (
        f'File "{sys.prefix}\\Lib\\site-packages\\x.py" and {workspace.root}\\app\\main.py '
        f"and {relative}\\Lib\\y.py"
    )
    redacted = redact_host_paths(text, workspace)
    assert sys.prefix not in redacted
    assert relative not in redacted
    assert str(workspace.root) not in redacted
    assert "<python>" in redacted
