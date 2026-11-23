"""Decides which agent commands may run, and rewrites them into an exact argv.

Commands are never passed to a shell. Sprint 1 supports pytest only, with an allowlist of
options: options such as ``-p`` (load a plugin), ``--rootdir``, ``-c`` or ``--confcutdir``
could load code or configuration from outside the workspace, so they are refused, and
positional paths must stay inside the workspace.
"""

import shlex
import sys

from bughunter.sandbox.workspace import Workspace, WorkspaceError


class CommandPolicyError(ValueError):
    pass


_PYTEST_FLAGS = frozenset(
    {"-q", "-v", "-vv", "-x", "-s", "-l", "-ra", "-rA", "--no-header", "--collect-only", "--co"}
)
_PYTEST_VALUE_OPTIONS = frozenset({"-k", "--tb", "--maxfail", "--durations"})
_PYTEST_PREFIX_OPTIONS = ("--tb=", "--maxfail=", "--durations=")


class CommandPolicy:
    def __init__(self, allowed_prefixes: tuple[tuple[str, ...], ...]) -> None:
        self.allowed_prefixes = allowed_prefixes

    def build_argv(self, command: str, workspace: Workspace) -> list[str]:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise CommandPolicyError(f"could not parse command: {exc}") from None
        if not tokens:
            raise CommandPolicyError("empty command")

        prefix = next(
            (p for p in self.allowed_prefixes if tuple(tokens[: len(p)]) == p),
            None,
        )
        if prefix is None:
            allowed = ", ".join(" ".join(p) for p in self.allowed_prefixes) or "none"
            raise CommandPolicyError(f"command not permitted. Allowed commands: {allowed}")
        if prefix[-1] != "pytest":
            raise CommandPolicyError(f"no execution policy for {' '.join(prefix)!r}")
        args = self._check_pytest_args(tokens[len(prefix) :], workspace)
        return [sys.executable, "-m", "pytest", *args]

    @staticmethod
    def _check_pytest_args(args: list[str], workspace: Workspace) -> list[str]:
        checked: list[str] = []
        expect_value = False
        for arg in args:
            if expect_value:
                checked.append(arg)
                expect_value = False
            elif arg in _PYTEST_FLAGS or arg.startswith(_PYTEST_PREFIX_OPTIONS):
                checked.append(arg)
            elif arg in _PYTEST_VALUE_OPTIONS:
                checked.append(arg)
                expect_value = True
            elif arg.startswith("-"):
                raise CommandPolicyError(f"pytest option not permitted: {arg}")
            else:
                path_part = arg.split("::", 1)[0]
                try:
                    workspace.resolve(path_part)
                except WorkspaceError as exc:
                    raise CommandPolicyError(str(exc)) from None
                checked.append(arg)
        if expect_value:
            raise CommandPolicyError("option is missing its value")
        return checked
