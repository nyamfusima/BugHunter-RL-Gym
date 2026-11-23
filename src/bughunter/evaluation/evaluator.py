"""Evaluation pipeline: integrity check, then trusted verification, then scoring."""

import time

from bughunter.challenges.base import Challenge
from bughunter.evaluation.integrity import check_integrity
from bughunter.evaluation.report import EvaluationReport
from bughunter.evaluation.reward import compute_score
from bughunter.evaluation.verifier import run_verifier
from bughunter.sandbox.executor import Executor, LocalExecutor
from bughunter.sandbox.workspace import Workspace


class Evaluator:
    def __init__(self, executor: Executor | None = None) -> None:
        self.executor: Executor = executor or LocalExecutor()

    def evaluate(self, challenge: Challenge, workspace: Workspace) -> EvaluationReport:
        start = time.monotonic()
        integrity = check_integrity(workspace)
        # The verifier runs even for disqualified submissions so reports show the raw pass
        # rates (useful for calibration); disqualification is applied during scoring.
        run = run_verifier(challenge, workspace, self.executor)
        breakdown = compute_score(
            challenge.spec.evaluation.weights, run.results, integrity, run.error
        )
        return EvaluationReport(
            challenge_id=challenge.id,
            challenge_version=challenge.spec.version,
            score=breakdown.score,
            resolved=breakdown.resolved,
            failure_category=breakdown.failure_category,
            categories=breakdown.categories,
            valid_submission_points=breakdown.valid_submission_points,
            integrity=integrity,
            tests=tuple(run.results),
            evaluation_error=run.error,
            sandbox_isolated=self.executor.isolated,
            duration_seconds=round(time.monotonic() - start, 3),
        )
