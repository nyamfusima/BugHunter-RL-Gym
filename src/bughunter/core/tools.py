"""Environment-side implementations of the agent tools (excluding submission).

Every handler returns a :class:`ToolResult`; agent mistakes (bad paths, refused commands,
missing files) are reported as ``ok=False`` results, never raised. Output never contains
absolute host paths, only workspace-relative ones.
"""

import contextlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bughunter.core.actions import (
    EditFileArgs,
    ListFilesArgs,
    ReadFileArgs,
    RunCommandArgs,
    SearchCodeArgs,
)
from bughunter.core.config import MAX_LIST_ENTRIES, MAX_READ_BYTES, MAX_SEARCH_RESULTS
from bughunter.sandbox.command_policy import CommandPolicy, CommandPolicyError
from bughunter.sandbox.executor import Executor
from bughunter.sandbox.workspace import Workspace, WorkspaceError


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str


def redact_host_paths(text: str, workspace: Workspace) -> str:
    """Replace host locations (workspace, Python installation) in command output.

    Best-effort only: it hides incidental leaks such as traceback paths that point at the
    installed BugHunter package. It does not stop code run by the agent from discovering
    those paths itself; that needs process isolation.
    """
    replacements = {str(workspace.root): "."}
    for prefix in {sys.prefix, sys.base_prefix, sys.exec_prefix}:
        replacements[str(Path(prefix).resolve())] = "<python>"
        replacements[prefix] = "<python>"
        # Tools such as pytest also print paths relative to the working directory. On
        # Windows there is no relative form across drives (ValueError).
        with contextlib.suppress(ValueError):
            replacements[os.path.relpath(prefix, workspace.root)] = "<python>"
    for original, replacement in sorted(replacements.items(), key=lambda kv: -len(kv[0])):
        for variant in {original, original.replace("\\", "/")}:
            text = re.sub(re.escape(variant), replacement, text, flags=re.IGNORECASE)
    return text


def _fail(message: str) -> ToolResult:
    return ToolResult(ok=False, output=f"ERROR: {message}")


def _read_text(workspace: Workspace, rel_path: str) -> str:
    path = workspace.resolve(rel_path)
    if not path.is_file():
        raise WorkspaceError(f"not a file: {rel_path}")
    if path.stat().st_size > MAX_READ_BYTES:
        raise WorkspaceError(f"file too large to read: {rel_path}")
    return path.read_bytes().decode("utf-8", errors="replace")


def list_files(workspace: Workspace, args: ListFilesArgs) -> ToolResult:
    try:
        start = workspace.resolve(args.path)
    except WorkspaceError as exc:
        return _fail(str(exc))
    if not start.is_dir():
        return _fail(f"not a directory: {args.path}")
    files = workspace.iter_files(start)
    lines = [str(f) for f in files[:MAX_LIST_ENTRIES]]
    if len(files) > MAX_LIST_ENTRIES:
        lines.append(f"... {len(files) - MAX_LIST_ENTRIES} more files not shown")
    return ToolResult(ok=True, output="\n".join(lines) if lines else "(no files)")


def read_file(workspace: Workspace, args: ReadFileArgs) -> ToolResult:
    try:
        text = _read_text(workspace, args.path)
    except WorkspaceError as exc:
        return _fail(str(exc))
    lines = text.splitlines()
    first = args.start_line or 1
    last = min(args.end_line or len(lines), len(lines))
    if lines and first > len(lines):
        return _fail(f"start_line {first} is past the end of the file ({len(lines)} lines)")
    width = len(str(last))
    numbered = [f"{n:>{width}} | {lines[n - 1]}" for n in range(first, last + 1)]
    header = f"{args.path} (lines {first}-{last} of {len(lines)})"
    return ToolResult(ok=True, output="\n".join([header, *numbered]))


def search_code(workspace: Workspace, args: SearchCodeArgs) -> ToolResult:
    try:
        start = workspace.resolve(args.path)
    except WorkspaceError as exc:
        return _fail(str(exc))
    try:
        matcher = re.compile(args.pattern if args.regex else re.escape(args.pattern))
    except re.error as exc:
        return _fail(f"invalid regular expression: {exc}")

    targets = [workspace.relative(start)] if start.is_file() else workspace.iter_files(start)
    matches: list[str] = []
    for rel in targets:
        try:
            text = _read_text(workspace, str(rel))
        except WorkspaceError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if matcher.search(line):
                matches.append(f"{rel}:{number}: {line.strip()}")
                if len(matches) >= MAX_SEARCH_RESULTS:
                    matches.append(f"... stopped after {MAX_SEARCH_RESULTS} matches")
                    return ToolResult(ok=True, output="\n".join(matches))
    return ToolResult(ok=True, output="\n".join(matches) if matches else "(no matches)")


def edit_file(workspace: Workspace, args: EditFileArgs) -> ToolResult:
    try:
        path = workspace.resolve(args.path)
    except WorkspaceError as exc:
        return _fail(str(exc))
    rel = workspace.relative(path)
    if not workspace.is_editable(rel):
        editable = ", ".join(str(p) for p in workspace.editable_paths)
        return _fail(f"{rel} is read-only; only files under {editable} may be modified")
    if path.is_dir():
        return _fail(f"{rel} is a directory")

    if args.content is not None:
        new_text = args.content
        action = "created" if not path.exists() else "rewrote"
    else:
        assert args.old_str is not None and args.new_str is not None
        if not path.is_file():
            return _fail(f"file not found: {rel}")
        current = path.read_bytes().decode("utf-8", errors="replace")
        occurrences = current.count(args.old_str)
        if occurrences != 1:
            return _fail(f"old_str must match exactly once in {rel}; found {occurrences} matches")
        new_text = current.replace(args.old_str, args.new_str, 1)
        action = "edited"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(new_text.encode("utf-8"))
    return ToolResult(ok=True, output=f"{action} {rel} ({len(new_text.splitlines())} lines)")


def run_command(
    workspace: Workspace,
    args: RunCommandArgs,
    policy: CommandPolicy,
    executor: Executor,
    timeout: float,
) -> ToolResult:
    try:
        argv = policy.build_argv(args.command, workspace)
    except CommandPolicyError as exc:
        return _fail(str(exc))
    result = executor.run(argv, cwd=workspace.root, timeout=timeout)
    output = redact_host_paths(result.output, workspace)
    if result.timed_out:
        return _fail(f"command timed out after {timeout:.0f}s\n{output}")
    return ToolResult(ok=True, output=f"$ {args.command}\n[exit code {result.exit_code}]\n{output}")
