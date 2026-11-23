"""Detects benchmark tampering and empty submissions by inspecting the final workspace.

The verifier never runs the agent's copy of the tests or configuration (it rebuilds a clean
evaluation tree), so most tampering would have no effect anyway. It is still detected and
penalised: an agent that tries to game the evaluation should score zero, not merely fail
to benefit.
"""

import ast
from pathlib import Path, PurePosixPath

from bughunter.core.config import MAX_SUBMISSION_BYTES, MAX_SUBMISSION_FILES
from bughunter.evaluation.report import IntegrityReport, IntegrityViolation
from bughunter.sandbox.workspace import Workspace, file_digest, is_ignored

#: File names that change how Python or pytest start up. They have no place in app code.
FORBIDDEN_FILE_NAMES = frozenset({"conftest.py", "sitecustomize.py", "usercustomize.py"})
FORBIDDEN_SUFFIXES = (".pth",)
#: Modules that application code has no reason to import; importing them suggests an
#: attempt to interfere with the test run.
FORBIDDEN_IMPORTS = frozenset({"pytest", "_pytest", "pluggy", "bughunter"})


def _imported_modules(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()  # Broken code is a correctness failure, not tampering.
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and node.args and _is_dynamic_import(node.func):
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                modules.add(first.value.split(".")[0])
    return modules


def _is_dynamic_import(func: ast.expr) -> bool:
    """``__import__("x")`` or ``importlib.import_module("x")`` with a literal module name.

    This is a heuristic: computed module names are not detected. Process isolation, not
    static analysis, is the real defence (see README, "Known limitations").
    """
    if isinstance(func, ast.Name):
        return func.id in {"__import__", "import_module"}
    return isinstance(func, ast.Attribute) and func.attr == "import_module"


def check_integrity(workspace: Workspace) -> IntegrityReport:
    violations: list[IntegrityViolation] = []
    changed: list[str] = []
    seen: set[str] = set()
    editable_bytes = 0
    editable_files = 0

    for path in sorted(workspace.root.rglob("*")):
        rel = PurePosixPath(Path(path).relative_to(workspace.root).as_posix())
        if is_ignored(rel):
            continue
        key = str(rel)
        if path.is_symlink():
            violations.append(IntegrityViolation(kind="symlink", path=key, detail="symlink"))
            continue
        if path.is_dir():
            continue
        seen.add(key)
        baseline = workspace.baseline.get(key)

        if not workspace.is_editable(rel):
            if baseline is None:
                detail = "new file outside the editable paths"
                violations.append(IntegrityViolation(kind="protected", path=key, detail=detail))
            elif file_digest(path) != baseline:
                violations.append(
                    IntegrityViolation(kind="protected", path=key, detail="protected file modified")
                )
            continue

        editable_files += 1
        editable_bytes += path.stat().st_size
        if baseline is None or file_digest(path) != baseline:
            changed.append(key)
        if rel.name in FORBIDDEN_FILE_NAMES or rel.name.endswith(FORBIDDEN_SUFFIXES):
            violations.append(
                IntegrityViolation(
                    kind="forbidden_file", path=key, detail="file alters interpreter/test startup"
                )
            )
        if rel.suffix == ".py":
            source = path.read_text(encoding="utf-8", errors="replace")
            bad = sorted(_imported_modules(source) & FORBIDDEN_IMPORTS)
            if bad:
                violations.append(
                    IntegrityViolation(
                        kind="forbidden_import",
                        path=key,
                        detail=f"application code imports {', '.join(bad)}",
                    )
                )

    for key in sorted(set(workspace.baseline) - seen):
        rel = PurePosixPath(key)
        if workspace.is_editable(rel):
            changed.append(key)  # Deleting application files is a legitimate change.
        else:
            violations.append(
                IntegrityViolation(kind="protected", path=key, detail="protected file deleted")
            )

    if editable_files > MAX_SUBMISSION_FILES or editable_bytes > MAX_SUBMISSION_BYTES:
        violations.append(
            IntegrityViolation(
                kind="oversized",
                path=".",
                detail=f"{editable_files} files / {editable_bytes} bytes exceeds submission limits",
            )
        )
    return IntegrityReport(violations=tuple(violations), changed_files=tuple(sorted(changed)))
