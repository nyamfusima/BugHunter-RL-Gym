"""Command execution backends.

Only :class:`LocalExecutor` exists in Sprint 1. It runs commands as host subprocesses with a
timeout and a scrubbed environment, and it provides **no isolation**: code under test can
read and write anything the host user can. A Docker-backed executor is planned; until it
exists, BugHunter must not be used to run untrusted agents.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: Host variables passed through to child processes. Everything else is dropped.
_PASSTHROUGH_ENV = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "TMPDIR")

_FIXED_ENV = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONIOENCODING": "utf-8",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "NO_COLOR": "1",
}


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    output: str
    timed_out: bool
    duration_seconds: float


class Executor(Protocol):
    #: Whether commands run in an isolated sandbox. Reported in every evaluation.
    isolated: bool

    def run(self, argv: list[str], cwd: Path, timeout: float) -> CommandResult: ...


def scrubbed_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ}
    env.update(_FIXED_ENV)
    return env


class LocalExecutor:
    """Runs commands directly on the host. NOT a sandbox."""

    isolated = False

    def run(self, argv: list[str], cwd: Path, timeout: float) -> CommandResult:
        start = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 - argv is policy-checked, no shell
                argv,
                cwd=cwd,
                env=scrubbed_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.output.decode("utf-8", "replace") if exc.output else ""
            return CommandResult(None, partial, True, time.monotonic() - start)
        output = completed.stdout.decode("utf-8", "replace")
        return CommandResult(completed.returncode, output, False, time.monotonic() - start)
