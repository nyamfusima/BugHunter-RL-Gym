"""Run one scripted BugHunter episode end-to-end and save the evaluation report.

This drives the environment with a *scripted* solver, not an AI agent. It exists to
demonstrate the full episode lifecycle and to sanity-check scoring:

    python scripts/run_episode.py                     # applies the reference fix -> 100
    python scripts/run_episode.py --solution partial  # plausible off-by-one fix -> partial
    python scripts/run_episode.py --solution noop     # submits without changes -> 0
    python scripts/run_episode.py --solution tamper   # fix + weakened tests -> 0
"""

import argparse
import json
from pathlib import Path
from typing import Any

import gymnasium as gym

import bughunter  # noqa: F401 - registers BugHunter-v0
from bughunter.core.actions import make_action
from bughunter.core.environment import BugHunterEnv

BUGGY_LINE = "        return self._users[user_id]\n"
OFF_BY_ONE_FIX = (
    "        if 1 <= user_id <= len(self._users):\n"
    "            return self._users[user_id - 1]\n"
    "        return None\n"
)


def show(step: str, obs: dict[str, Any], reward: float = 0.0) -> None:
    result = str(obs["last_result"])
    preview = result if len(result) < 600 else result[:600] + "\n  ..."
    print(f"\n--- {step}  (steps left: {obs['steps_remaining']}, reward: {reward})")
    print("  " + preview.replace("\n", "\n  "))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--challenge", default="API-001")
    parser.add_argument(
        "--solution", choices=["reference", "partial", "noop", "tamper"], default="reference"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    args = parser.parse_args()

    env = gym.make("BugHunter-v0", challenge_id=args.challenge)
    core: BugHunterEnv = env.unwrapped  # type: ignore[assignment]
    try:
        obs, info = env.reset(seed=args.seed)
        print(f"Challenge {info['challenge_id']} v{info['challenge_version']}")
        print(f"Sandbox isolated: {info['sandbox_isolated']}")
        print("\n" + str(obs["task"]))

        def act(label: str, tool: str, **tool_args: Any) -> tuple[Any, ...]:
            result = env.step(make_action(tool, **tool_args))
            show(label, result[0], float(result[1]))
            return result

        act("explore", "list_files")
        act("locate", "search_code", pattern="def get_user")
        act("inspect", "read_file", path="app/repository.py")
        act("reproduce", "run_command", command="pytest -q --tb=line")

        if args.solution in ("reference", "tamper"):
            fixed = (core.challenge.reference_dir / "app" / "repository.py").read_text("utf-8")
            act("fix", "edit_file", path="app/repository.py", content=fixed)
        elif args.solution == "partial":
            act("fix", "edit_file", path="app/repository.py", old_str=BUGGY_LINE,
                new_str=OFF_BY_ONE_FIX)  # fmt: skip
        if args.solution == "tamper":
            # The edit tool refuses protected files, so simulate what code executed through
            # run_command could do: weaken the public tests directly on disk.
            act("tamper (refused by tool)", "edit_file", path="tests/test_users.py", content="")
            tests = core.workspace.root / "tests" / "test_users.py"
            tests.write_text(tests.read_text("utf-8").replace("== 404", "!= 404"), "utf-8")
            print(
                "\n--- tamper: weakened tests/test_users.py on disk (simulated run_command abuse)"
            )
        if args.solution != "noop":
            act("verify", "run_command", command="pytest -q --tb=line")

        _, reward, terminated, truncated, info = act("submit", "submit_solution")
        assert terminated and not truncated

        evaluation = info["evaluation"]
        episode = info["episode"]
        args.out.mkdir(parents=True, exist_ok=True)
        out_file = args.out / f"{args.challenge}-{args.solution}-{episode['episode_id'][:8]}.json"
        out_file.write_text(
            json.dumps({"episode": episode, "evaluation": evaluation}, indent=2), "utf-8"
        )

        print("\n=== Evaluation (operator view)")
        print(f"score:            {evaluation['score']} / 100   (reward {reward})")
        print(f"resolved:         {evaluation['resolved']}")
        print(f"failure category: {evaluation['failure_category']}")
        for cat in evaluation["categories"]:
            print(
                f"  {cat['category']:<11} {cat['passed']:>2}/{cat['total']:<2} tests  "
                f"{cat['points']:>6.2f} / {cat['max_points']:.0f} pts"
            )
        print(f"  valid submission          {evaluation['valid_submission_points']:>6.2f} / 5 pts")
        for violation in evaluation["integrity"]["violations"]:
            print(f"  integrity violation: {violation['path']}: {violation['detail']}")
        print(f"steps: {episode['steps_taken']}, tools: {episode['tool_counts']}")
        print(f"sandbox isolated: {evaluation['sandbox_isolated']}")
        print(f"report written to {out_file}")
    finally:
        env.close()


if __name__ == "__main__":
    main()
