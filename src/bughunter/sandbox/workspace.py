"""The agent's disposable, per-episode working copy of a challenge repository."""

import hashlib
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from bughunter.challenges.base import Challenge
from bughunter.core.config import IGNORED_DIR_NAMES, IGNORED_FILE_SUFFIXES


class WorkspaceError(ValueError):
    """An agent request that the workspace refuses (reported back to the agent)."""


def is_ignored(rel_path: PurePosixPath) -> bool:
    """Build artefacts (bytecode, caches) are invisible to listings and integrity checks."""
    if any(part in IGNORED_DIR_NAMES for part in rel_path.parts):
        return True
    return rel_path.name.endswith(IGNORED_FILE_SUFFIXES)


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """Map every non-ignored file under ``root`` (posix relative path) to its SHA-256."""
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if is_ignored(rel) or path.is_dir():
            continue
        result[str(rel)] = "<symlink>" if path.is_symlink() else file_digest(path)
    return result


def _ignore_artefacts(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in IGNORED_DIR_NAMES or n.endswith(IGNORED_FILE_SUFFIXES)}


class Workspace:
    """A fresh copy of ``starter/`` plus ``public_tests/`` in a private temporary directory.

    All agent-supplied paths go through :meth:`resolve`, which confines them to the
    workspace. This is a policy boundary for the file tools, *not* a security boundary:
    code the agent runs via ``run_command`` executes with the host user's permissions
    unless a sandboxed executor is used.
    """

    def __init__(self, root: Path, editable_paths: tuple[str, ...]) -> None:
        self.root = root.resolve()
        self.editable_paths = tuple(PurePosixPath(p) for p in editable_paths)
        #: Hashes of the pristine workspace, taken before the agent could act.
        self.baseline: dict[str, str] = snapshot(self.root)

    @classmethod
    def create(cls, challenge: Challenge) -> "Workspace":
        root = Path(tempfile.mkdtemp(prefix=f"bughunter-{challenge.id.lower()}-"))
        shutil.copytree(challenge.starter_dir, root, dirs_exist_ok=True, ignore=_ignore_artefacts)
        shutil.copytree(
            challenge.public_tests_dir,
            root / challenge.spec.workspace.public_tests_dir,
            ignore=_ignore_artefacts,
        )
        return cls(root, challenge.spec.workspace.editable_paths)

    def resolve(self, rel_path: str) -> Path:
        """Resolve an agent-supplied relative path, refusing anything outside the workspace."""
        if "\x00" in rel_path:
            raise WorkspaceError("path contains a NUL byte")
        normalized = rel_path.replace("\\", "/").strip() or "."
        if (
            PurePosixPath(normalized).is_absolute()
            or PureWindowsPath(normalized).drive
            or PureWindowsPath(normalized).is_absolute()
        ):
            raise WorkspaceError(f"path must be relative to the repository root: {rel_path!r}")
        if ".." in PurePosixPath(normalized).parts:
            raise WorkspaceError(f"path may not contain '..': {rel_path!r}")

        candidate = self.root.joinpath(*PurePosixPath(normalized).parts)
        # Refuse symlinks anywhere along the path, then confirm the resolved location.
        probe = candidate
        while probe != self.root:
            if probe.is_symlink():
                raise WorkspaceError(f"symbolic links are not permitted: {rel_path!r}")
            probe = probe.parent
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise WorkspaceError(f"path escapes the repository: {rel_path!r}")
        return resolved

    def relative(self, path: Path) -> PurePosixPath:
        return PurePosixPath(path.resolve().relative_to(self.root).as_posix())

    def is_editable(self, rel_path: PurePosixPath) -> bool:
        return any(rel_path.is_relative_to(editable) for editable in self.editable_paths)

    def iter_files(self, start: Path | None = None) -> list[PurePosixPath]:
        base = start or self.root
        files: list[PurePosixPath] = []
        for path in sorted(base.rglob("*")):
            rel = self.relative(path) if not path.is_symlink() else None
            if rel is None or is_ignored(rel) or not path.is_file():
                continue
            files.append(rel)
        return files

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
