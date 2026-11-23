"""Per-episode bookkeeping: budget, status and an audit log of every action."""

import time
import uuid
from dataclasses import dataclass, field

from bughunter.core.actions import ToolName
from bughunter.core.observations import EpisodeStatus
from bughunter.evaluation.report import EvaluationReport


@dataclass(frozen=True)
class ActionRecord:
    step: int
    tool: str | None
    ok: bool
    duration_seconds: float


@dataclass
class Episode:
    challenge_id: str
    max_steps: int
    time_limit_seconds: float
    episode_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: EpisodeStatus = EpisodeStatus.RUNNING
    steps_taken: int = 0
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    actions: list[ActionRecord] = field(default_factory=list)
    report: EvaluationReport | None = None

    @property
    def done(self) -> bool:
        return self.status is not EpisodeStatus.RUNNING

    @property
    def steps_remaining(self) -> int:
        return max(self.max_steps - self.steps_taken, 0)

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - self.started_at

    def record(self, tool: ToolName | None, ok: bool, duration: float) -> None:
        self.steps_taken += 1
        self.actions.append(
            ActionRecord(
                step=self.steps_taken,
                tool=tool.slug if tool is not None else None,
                ok=ok,
                duration_seconds=round(duration, 4),
            )
        )

    def finish(self, status: EpisodeStatus) -> None:
        self.status = status
        self.finished_at = time.monotonic()

    def summary(self) -> dict[str, object]:
        tool_counts: dict[str, int] = {}
        for record in self.actions:
            key = record.tool or "invalid"
            tool_counts[key] = tool_counts.get(key, 0) + 1
        return {
            "episode_id": self.episode_id,
            "challenge_id": self.challenge_id,
            "status": self.status.name.lower(),
            "steps_taken": self.steps_taken,
            "invalid_actions": sum(not r.ok for r in self.actions),
            "tool_counts": tool_counts,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "score": self.report.score if self.report else 0.0,
            "resolved": self.report.resolved if self.report else False,
        }
