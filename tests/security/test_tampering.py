"""Attempts to game the evaluation must score zero, even alongside a correct fix.

Each case applies the reference fix *and* a tampering action (as an agent could via
run_command-executed code), and checks the submission is disqualified.
"""

from collections.abc import Callable

import pytest

from bughunter.challenges.base import Challenge
from bughunter.evaluation.evaluator import Evaluator
from bughunter.evaluation.integrity import check_integrity
from bughunter.evaluation.report import FailureCategory
from bughunter.sandbox.workspace import Workspace

from helpers import apply_reference, write

pytestmark = pytest.mark.integration


def _weaken_public_test(ws: Workspace) -> None:
    path = ws.root / "tests" / "test_users.py"
    path.write_text(path.read_text(encoding="utf-8").replace("== 404", "!= 404"), encoding="utf-8")


TAMPERS: dict[str, Callable[[Workspace], object]] = {
    "modify_public_test": _weaken_public_test,
    "delete_public_test": lambda ws: (ws.root / "tests" / "test_users.py").unlink(),
    "modify_pytest_ini": lambda ws: write(ws, "pytest.ini", "[pytest]\naddopts = --co\n"),
    "add_root_conftest": lambda ws: write(ws, "conftest.py", "import pytest\n"),
    "add_app_conftest": lambda ws: write(ws, "app/conftest.py", "x = 1\n"),
    "add_sitecustomize": lambda ws: write(ws, "app/sitecustomize.py", "x = 1\n"),
    "add_pth_file": lambda ws: write(ws, "app/evil.pth", "import os\n"),
    "app_imports_pytest": lambda ws: write(ws, "app/helpers.py", "import pytest\n"),
    "app_imports_pytest_internals": lambda ws: write(
        ws, "app/helpers.py", "from _pytest import runner\n"
    ),
    "app_dynamic_import": lambda ws: write(ws, "app/helpers.py", "__import__('pytest')\n"),
    "app_importlib_import": lambda ws: write(
        ws, "app/helpers.py", "import importlib\nimportlib.import_module('_pytest.runner')\n"
    ),
    "app_imports_bughunter": lambda ws: write(
        ws, "app/helpers.py", "import bughunter.evaluation\n"
    ),
}


@pytest.mark.parametrize("tamper", sorted(TAMPERS))
def test_tampering_scores_zero(api001: Challenge, workspace: Workspace, tamper: str) -> None:
    apply_reference(api001, workspace)
    TAMPERS[tamper](workspace)
    report = Evaluator().evaluate(api001, workspace)
    assert report.integrity.tampered
    assert report.score == 0
    assert report.failure_category is FailureCategory.TAMPERING


def test_weakened_public_tests_are_not_what_gets_run(
    api001: Challenge, workspace: Workspace
) -> None:
    """Even ignoring the penalty, scoring uses trusted test copies, not the agent's."""
    _weaken_public_test(workspace)
    write(workspace, "app/main.py", (workspace.root / "app/main.py").read_text() + "\n")
    report = Evaluator().evaluate(api001, workspace)
    public = next(c for c in report.categories if c.category.value == "public")
    assert (public.passed, public.total) == (2, 4)  # Same as the untouched broken starter.


def test_legitimate_new_app_module_is_not_tampering(workspace: Workspace) -> None:
    write(workspace, "app/lookup.py", "def find(users, user_id):\n    return None\n")
    integrity = check_integrity(workspace)
    assert not integrity.tampered
    assert integrity.changed_files == ("app/lookup.py",)


def test_build_artefacts_are_ignored(workspace: Workspace) -> None:
    write(workspace, "tests/__pycache__/test_users.cpython-312.pyc", "junk")
    write(workspace, ".pytest_cache/v/cache/lastfailed", "{}")
    integrity = check_integrity(workspace)
    assert not integrity.tampered
    assert integrity.no_changes
