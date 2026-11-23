# BugHunter architecture (Sprint 1)

## Layers

```
external agent / scripted solver
        │  Gymnasium actions: {"tool": int, "args": JSON}
        ▼
core.environment.BugHunterEnv ── core.episode (budget, status, audit log)
        │                    └── core.tools (list/read/search/edit/run handlers)
        ├── challenges.registry → challenges.base.Challenge (challenge.yaml + assets)
        ├── sandbox.workspace   (disposable per-episode copy, path confinement)
        ├── sandbox.command_policy + sandbox.executor (allowlisted pytest, timeouts)
        └── evaluation.evaluator
              ├── integrity  (tamper / no-op detection against baseline hashes)
              ├── verifier   (fresh evaluation tree + trusted suites, JUnit results)
              └── reward     (weighted, hidden-gated score → EvaluationReport)
```

## Trust boundary

| Asset                            | Agent can see | Agent can modify | Used for scoring |
|----------------------------------|:-------------:|:----------------:|:----------------:|
| `starter/` copy (`app/`)         | yes           | yes (`app/` only)| yes: copied into the eval tree |
| `public_tests/` copy (`tests/`)  | yes           | no (tampering)   | no: trusted copy used instead |
| workspace `pytest.ini`           | yes           | no (tampering)   | no: verifier writes its own |
| `verifier/` hidden suites        | no            | no               | yes |
| `reference/` solution            | no            | no               | no: validates the verifier only |

"Agent can see" applies to the **tools**. Without process isolation, code the agent runs
through `run_command` executes as the host user and can read the installed package,
`verifier/` included. Closing that gap is the job of the planned Docker executor. Until then
every report carries `sandbox_isolated: false`.

## Design decisions

**Action space is `Dict{tool: Discrete(6), args: Text}`.** A bare `Discrete(6)` cannot carry
tool arguments. Arguments are a JSON object validated by per-tool Pydantic models. Random
samples (e.g. from `check_env`) are almost never valid JSON objects, so they exercise the
error path. An invalid action is reported to the agent and consumes a step. It never raises.

**Text spaces use `string.printable` with `min_length=0`.** Gymnasium's default `Text`
charset is alphanumeric with `min_length=1`, so real tool output (newlines, punctuation,
empty results) would fall outside the space. Output is sanitised and truncated to 10,000
characters with an explicit marker.

**`steps_remaining` is sized from the challenge** (`Discrete(max_steps + 1)`), not fixed at 101.

**Sparse reward.** Only `submit_solution` produces reward (the 0–100 score). Running out of
steps or time truncates the episode with reward 0. The time limit is checked *before* an
action executes, so a late submission is never evaluated.

**The verifier rebuilds instead of trusting the workspace.** It copies only the editable
paths into a new directory beside trusted test copies and its own `pytest.ini`
(`--import-mode=importlib`, `--continue-on-collection-errors`, plugin autoload disabled,
scrubbed environment). The agent's app is imported inside a fixture, so an import-time crash
fails every test instead of removing them. Results come from JUnit XML written outside the
evaluation tree.

**Tampering is penalised even when it would be ineffective.** Modified, deleted or added
protected files, `conftest.py`/`sitecustomize.py`/`.pth` files in app code, app code importing
`pytest`/`_pytest`/`pluggy`/`bughunter`, and symlinks all set the score to 0. The import
check is static (AST) and heuristic, and computed module names evade it.

**Hidden-test gating.** Supporting categories are multiplied by the hidden pass rate.
Without it, a comment-only change to the API-001 starter scores 37.5/100 (measured). With
it, the same change scores 0.

## Known gaps (not implemented in Sprint 1)

- Docker executor (CPU/memory limits, no network, non-root, read-only assets).
- Agent adapters (tool-calling bridge for Claude Code / Codex), benchmark runner, metrics,
  leaderboard, episode database.
- Challenges AUTH and DB.
- Difficulty calibration against real agents.
- Host-path redaction in command output is best-effort and is not a security control.
