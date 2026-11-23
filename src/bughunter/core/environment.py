"""The BugHunter Gymnasium environment.

One episode = one attempt at one challenge:

* ``reset()`` creates a fresh, disposable workspace from the challenge's starter repository.
* ``step(action)`` executes one tool call. Every call, valid or not, consumes one step.
* ``submit_solution`` ends the episode (``terminated=True``) and returns the evaluation score
  (0-100) as the reward. All other steps return reward 0.
* Exhausting the step or time budget ends the episode (``truncated=True``) with reward 0:
  unsubmitted work is not scored.
"""

import time
from typing import Any, SupportsFloat

import gymnasium as gym
from gymnasium import spaces

from bughunter.challenges.registry import ChallengeRegistry, default_registry
from bughunter.core import tools
from bughunter.core.actions import ActionError, ParsedAction, ToolName, parse_action
from bughunter.core.config import MAX_ACTION_ARGS_TEXT
from bughunter.core.episode import Episode
from bughunter.core.observations import (
    EpisodeStatus,
    build_observation_space,
    make_observation,
    text_space,
)
from bughunter.evaluation.evaluator import Evaluator
from bughunter.sandbox.command_policy import CommandPolicy
from bughunter.sandbox.executor import Executor, LocalExecutor
from bughunter.sandbox.workspace import Workspace

Observation = dict[str, Any]
Action = dict[str, Any]


class BugHunterEnv(gym.Env[Observation, Action]):
    metadata: dict[str, Any] = {"render_modes": []}  # noqa: RUF012 - Gymnasium API

    def __init__(
        self,
        challenge_id: str = "API-001",
        *,
        registry: ChallengeRegistry | None = None,
        executor: Executor | None = None,
    ) -> None:
        super().__init__()
        self.challenge = (registry or default_registry()).get(challenge_id)
        self.challenge_id = self.challenge.id
        spec = self.challenge.spec

        self.action_space = spaces.Dict(
            {
                "tool": spaces.Discrete(len(ToolName)),
                "args": text_space(MAX_ACTION_ARGS_TEXT),
            }
        )
        self.observation_space = build_observation_space(spec.limits.max_steps)

        self._executor: Executor = executor or LocalExecutor()
        self._evaluator = Evaluator(self._executor)
        self._policy = CommandPolicy(spec.allowed_commands)
        self._workspace: Workspace | None = None
        self._episode: Episode | None = None

    # ------------------------------------------------------------------ Gymnasium API

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[Observation, dict[str, Any]]:
        super().reset(seed=seed)
        self._cleanup_workspace()
        spec = self.challenge.spec
        self._workspace = Workspace.create(self.challenge)
        self._episode = Episode(
            challenge_id=self.challenge_id,
            max_steps=spec.limits.max_steps,
            time_limit_seconds=spec.limits.time_limit_seconds,
        )
        tool_names = ", ".join(sorted(t.slug for t in spec.allowed_tool_names))
        intro = (
            f"Episode started. The repository is ready. Available tools: {tool_names}. "
            f"Step budget: {spec.limits.max_steps}."
        )
        info = {
            "challenge_id": self.challenge_id,
            "challenge_version": spec.version,
            "allowed_tools": sorted(t.slug for t in spec.allowed_tool_names),
            "sandbox_isolated": self._executor.isolated,
        }
        return self._observation(intro), info

    def step(self, action: Action) -> tuple[Observation, SupportsFloat, bool, bool, dict[str, Any]]:
        episode = self._require_running_episode()
        started = time.monotonic()
        reward = 0.0
        tool: ToolName | None = None

        if episode.elapsed_seconds >= episode.time_limit_seconds:
            episode.record(None, ok=False, duration=0.0)
            episode.finish(EpisodeStatus.TRUNCATED_TIME)
            message = "Time limit exceeded before this action; the episode is not scored."
            return self._observation(message), reward, False, True, self._info(None, False)

        try:
            parsed = parse_action(action)
            tool = parsed.tool
            if tool not in self.challenge.spec.allowed_tool_names:
                result = tools.ToolResult(False, f"ERROR: tool {tool.slug} is not allowed")
            else:
                result = self._dispatch(parsed)
        except ActionError as exc:
            result = tools.ToolResult(False, f"ERROR: {exc}")

        episode.record(tool, result.ok, time.monotonic() - started)
        terminated = truncated = False
        output = result.output
        if episode.status is EpisodeStatus.SUBMITTED:
            terminated = True
            assert episode.report is not None
            reward = float(episode.report.score)
        elif episode.steps_remaining == 0:
            truncated = True
            episode.finish(EpisodeStatus.TRUNCATED_STEPS)
            output += "\n\nStep budget exhausted without a submission; the episode is not scored."

        return self._observation(output), reward, terminated, truncated, self._info(tool, result.ok)

    def close(self) -> None:
        self._cleanup_workspace()
        super().close()

    # ------------------------------------------------------------------ helpers

    @property
    def workspace(self) -> Workspace:
        """The current episode's workspace (for harnesses and tests, not for agents)."""
        if self._workspace is None:
            raise RuntimeError("no active episode; call reset() first")
        return self._workspace

    @property
    def episode(self) -> Episode:
        if self._episode is None:
            raise RuntimeError("no active episode; call reset() first")
        return self._episode

    def _require_running_episode(self) -> Episode:
        episode = self.episode
        if episode.done:
            raise RuntimeError("the episode has finished; call reset() to start a new one")
        return episode

    def _dispatch(self, parsed: ParsedAction) -> tools.ToolResult:
        workspace = self.workspace
        args: Any = parsed.args
        match parsed.tool:
            case ToolName.LIST_FILES:
                return tools.list_files(workspace, args)
            case ToolName.READ_FILE:
                return tools.read_file(workspace, args)
            case ToolName.SEARCH_CODE:
                return tools.search_code(workspace, args)
            case ToolName.RUN_COMMAND:
                timeout = self.challenge.spec.limits.command_timeout_seconds
                return tools.run_command(workspace, args, self._policy, self._executor, timeout)
            case ToolName.EDIT_FILE:
                return tools.edit_file(workspace, args)
            case ToolName.SUBMIT_SOLUTION:
                return self._submit()

    def _submit(self) -> tools.ToolResult:
        episode = self.episode
        report = self._evaluator.evaluate(self.challenge, self.workspace)
        episode.report = report
        episode.finish(EpisodeStatus.SUBMITTED)
        return tools.ToolResult(ok=True, output=report.agent_summary())

    def _observation(self, last_result: str) -> Observation:
        episode = self.episode
        return make_observation(
            task=self.challenge.spec.task,
            last_result=last_result,
            steps_remaining=episode.steps_remaining,
            status=episode.status,
        )

    def _info(self, tool: ToolName | None, ok: bool) -> dict[str, Any]:
        episode = self.episode
        info: dict[str, Any] = {
            "tool": tool.slug if tool is not None else None,
            "ok": ok,
            "steps_taken": episode.steps_taken,
        }
        if episode.done:
            info["episode"] = episode.summary()
            if episode.report is not None:
                info["evaluation"] = episode.report.model_dump(mode="json")
        return info

    def _cleanup_workspace(self) -> None:
        if self._workspace is not None:
            self._workspace.cleanup()
            self._workspace = None
