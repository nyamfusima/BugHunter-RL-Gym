"""Runs the trusted test suites against the agent's submission.

The verifier does **not** run tests inside the agent's workspace. It assembles a fresh
evaluation tree containing only the agent's editable files, trusted copies of the public
tests, the hidden suites and a verifier-owned pytest configuration::

    <eval>/pytest.ini            # written by the verifier
    <eval>/conftest.py           # from challenge verifier/
    <eval>/app/...               # the agent's editable paths, copied from the workspace
    <eval>/bh_tests/public/...   # trusted copy of the public tests
    <eval>/bh_tests/<category>/  # hidden suites (hidden, regression, edge_cases)

Results are read from a JUnit XML file written outside the evaluation tree, never from the
agent's own test output.
"""

import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from bughunter.challenges.base import Challenge, TestCategory
from bughunter.evaluation.report import TestCaseResult, TestOutcome
from bughunter.sandbox.executor import Executor
from bughunter.sandbox.workspace import Workspace

TESTS_PACKAGE = "bh_tests"

_PYTEST_INI = f"""\
[pytest]
pythonpath = .
testpaths = {TESTS_PACKAGE}
addopts = -p no:cacheprovider --import-mode=importlib --continue-on-collection-errors
junit_family = xunit2
"""
# --continue-on-collection-errors: the public tests import the agent's app at module level.
# Without it, a submission that fails to import aborts the whole run (exit code 2) and the
# hidden suites never execute; with it, the broken module is recorded as an error and every
# other suite still runs and fails on its own merits.


@dataclass
class VerifierRun:
    results: list[TestCaseResult] = field(default_factory=list)
    error: str | None = None
    exit_code: int | None = None
    duration_seconds: float = 0.0
    output_tail: str = ""


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def build_evaluation_tree(challenge: Challenge, workspace: Workspace, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for rel in workspace.iter_files():
        if workspace.is_editable(rel):
            target = dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(workspace.root.joinpath(*rel.parts), target)

    (dest / "pytest.ini").write_text(_PYTEST_INI, encoding="utf-8")
    for item in challenge.verifier_dir.iterdir():
        if item.is_file() and item.suffix == ".py":
            shutil.copyfile(item, dest / item.name)

    tests_root = dest / TESTS_PACKAGE
    _copy_tree(challenge.public_tests_dir, tests_root / TestCategory.PUBLIC.value)
    for category in challenge.verifier_categories:
        _copy_tree(challenge.verifier_dir / category.value, tests_root / category.value)


def _category_of(testcase: ET.Element) -> TestCategory | None:
    # Normal tests have classname "bh_tests.<category>.<module>"; collection errors have an
    # empty classname and the module path in "name".
    ident = testcase.get("classname") or testcase.get("name") or ""
    for category in TestCategory:
        if ident.startswith(f"{TESTS_PACKAGE}.{category.value}."):
            return category
    return None


def parse_junit(path: Path) -> list[TestCaseResult]:
    root = ET.parse(path).getroot()
    results: list[TestCaseResult] = []
    for testcase in root.iter("testcase"):
        category = _category_of(testcase)
        if category is None:
            continue
        if testcase.find("error") is not None:
            outcome = TestOutcome.ERROR
        elif testcase.find("failure") is not None:
            outcome = TestOutcome.FAILED
        elif testcase.find("skipped") is not None:
            outcome = TestOutcome.SKIPPED
        else:
            outcome = TestOutcome.PASSED
        name = f"{testcase.get('classname', '')}::{testcase.get('name', '')}".strip(":")
        results.append(TestCaseResult(category=category, name=name, outcome=outcome))
    return results


def run_verifier(challenge: Challenge, workspace: Workspace, executor: Executor) -> VerifierRun:
    start = time.monotonic()
    eval_root = Path(tempfile.mkdtemp(prefix="bughunter-eval-"))
    report_dir = Path(tempfile.mkdtemp(prefix="bughunter-junit-"))
    junit_path = report_dir / "results.xml"
    run = VerifierRun()
    try:
        build_evaluation_tree(challenge, workspace, eval_root)
        argv = [
            sys.executable, "-m", "pytest",
            "-c", str(eval_root / "pytest.ini"),
            "--rootdir", str(eval_root),
            f"--junitxml={junit_path}",
            "-q", "--no-header",
        ]  # fmt: skip
        result = executor.run(
            argv, cwd=eval_root, timeout=challenge.spec.evaluation.timeout_seconds
        )
        run.exit_code = result.exit_code
        run.output_tail = result.output[-4000:]
        if result.timed_out:
            run.error = "verifier timed out"
        elif result.exit_code not in (0, 1):
            run.error = f"pytest exited with code {result.exit_code}"
        elif not junit_path.is_file():
            run.error = "verifier produced no results"
        else:
            run.results = parse_junit(junit_path)
            if not run.results:
                run.error = "verifier recorded no test results"
    except Exception as exc:  # Evaluation must always yield a report.
        run.error = f"verifier failed: {type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(eval_root, ignore_errors=True)
        shutil.rmtree(report_dir, ignore_errors=True)
        run.duration_seconds = time.monotonic() - start
    return run
