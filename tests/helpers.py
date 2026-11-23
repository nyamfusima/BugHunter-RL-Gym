"""Plain helpers shared by BugHunter's own tests."""

from pathlib import Path

from bughunter.challenges.base import Challenge
from bughunter.sandbox.workspace import Workspace


def reference_source(challenge: Challenge, rel_path: str) -> str:
    return (challenge.reference_dir / rel_path).read_text(encoding="utf-8")


def apply_reference(challenge: Challenge, workspace: Workspace) -> None:
    """Copy the trusted reference solution into a workspace (test helper only)."""
    for path in sorted(challenge.reference_dir.rglob("*.py")):
        rel = path.relative_to(challenge.reference_dir)
        target = workspace.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def write(workspace: Workspace, rel_path: str, text: str) -> Path:
    path = workspace.root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
