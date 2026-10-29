# Delta — Design

Delta measures how a coding agent's choices affect the cost of future change (ETC, "Easier To Change"). An agent builds a project from zero across many stages. Each stage extends the agent's own prior code. Delta records tokens, cost, and time per stage. A codebase that stays easy to change keeps later stages cheap.

Status: tracer bullet. One problem, two stages, one harness.

## Core Decisions

| Area | Decision |
|---|---|
| ETC metric | Total tokens and active time to complete all stages |
| Outcome report | Stage reached and per-stage completion |
| Workspace | Agent's own code carries forward; never replaced by a reference solution |
| Starting point | Empty workspace |
| Problem shape | Python API, black-box HTTP tests |
| First problem | E-commerce API |
| Session | One agent session per stage; no conversation carried between stages |
| Tests | Hidden from the agent |
| Feedback | `delta-validate`, unlimited calls, reports failing test names and descriptions |
| Advancement gate | Isolated-correct |
| Auto-submit | Strict-correct ends the session |
| Budget | 2M total tokens per stage |
| Prompt | Identical for every harness; encourages no practice |
| Memory | Workspace files persist; one config flag controls it |
| Harness-native memory | Wiped between stages |
| Network | Model API only, through an allowlist proxy |
| Dependencies | Baked into the image |
| Concurrency | One provider at a time |

## Stage Lifecycle

1. Delta starts a fresh container from the problem image.
2. Delta copies the previous stage's final workspace into `/workspace`. Stage 1 starts empty.
3. If memory is off, Delta strips non-code files before the copy (see Memory).
4. Delta launches the harness headless with the rendered prompt.
5. The agent works and calls `delta-validate` as often as it likes.
6. The session ends on one of three events.
   - Strict-correct validate → submitted
   - Budget exhausted → stopped
   - Harness exits on its own → ended
7. Delta runs a final validate on the workspace and records the result.
8. Delta snapshots the workspace and writes the stage record.
9. If the final result is isolated-correct, the run advances. Otherwise the run stops at this stage.

## Test Categories

Vocabulary follows SlopCodeBench.

| Category | Checks |
|---|---|
| Core | Behavior shown explicitly in the spec |
| Error | Failure-mode behavior |
| Functionality | Hidden, exhaustive correctness |
| Regression | Prior stages' tests, as carried forward by this stage |

| Level | Passes |
|---|---|
| Core-correct | All core tests |
| Isolated-correct | All core, error, and functionality tests |
| Strict-correct | All tests, regression included |

- Each stage directory holds every test that must pass at that stage, regression included.
- A stage may drop or change earlier tests when its feature changes earlier behavior.
- Specs state normalization rules (key order, sort order, number formats) so trivial choices don't fail tests.

## Validate

- Command inside the sandbox: `delta-validate`.
- Requests go through a mounted IPC directory (`/delta-ipc`). The script drops a request file and waits for the host's response file. No network path is needed.
- Tests never enter the agent's container.
- Host copies the workspace, starts the agent's server in a separate offline test container, and runs the stage's tests over HTTP.
- Test category comes from the test's directory (`tests/core/`, `tests/error/`, ...). The description is the test's docstring.
- Output to the agent: pass/fail per level, plus name and description of every failing test (regression included).
- Output withheld: assertion messages, expected values, test source.
- Strict-correct triggers auto-submit. Delta ends the session.
- Every call is logged with timestamp, duration, results, and cumulative tokens at call time.
- Validate time counts toward the stage's time metric.

## Prompt

Rendered identically for every harness. `memory` and `spec` are the only variables.

```
Implement the specification below in Python. Work only in /workspace.

Run `delta-validate` to check your work. It reports the names and
descriptions of failing tests. When every test passes, your work is
submitted and the session ends.
{% if memory %}
Files you leave in the workspace persist to future tasks.
{% endif %}
Your task is:

{{ spec }}
```

- The spec reaches the agent through the prompt only. No spec file is written to the workspace.
- Earlier specs and run history are never shown.

## Memory

- Config flag: `memory = true | false`.
- On: the whole workspace carries forward, including any notes, plans, or `AGENTS.md`/`CLAUDE.md` the agent wrote.
- Off: Delta deletes files matching `memory_strip` in `config/delta.toml` at each stage boundary. Default globs cover `*.md`, `*.markdown`, `notes/`, and `plans/`. `*.txt` stays because `requirements.txt` is code.
- Harness-native memory outside the workspace (`~/.claude`, `~/.codex`, Pi state) never persists. A fresh container per stage enforces this.
- The seed contains no memory files.

## Sandbox

- Docker, one fresh container per stage, non-root user.
- Only `/workspace` persists between stages.
- Image bakes in Python, a fixed set of packages, and the harness CLIs at pinned versions.
- Agent containers sit on an internal Docker network (`delta-internal`) with no direct route out.
- An allowlist CONNECT proxy (`delta/proxy.py`, container `delta-proxy`) is the only exit. `allow_hosts` in `config/delta.toml` lists permitted hosts.
- Test containers run with no network.
- API keys enter as environment variables passed by name, so they never appear in command lines. Keys never get written into the workspace or snapshots.
- Agents can read their own key from the environment. This is unavoidable while the harness itself calls the API.

## Harness Adapters

Each harness implements one interface.

| Member | Job |
|---|---|
| `home` | Container path for native state; Delta mounts a fresh per-stage directory there |
| `env` | Environment variables, including auth |
| `command` | Headless invocation for a prompt and model |
| `resume_command` | Continues the same session after a pause |
| `parse_line` | Output line → session id, rate-limit flag, or fatal error |
| `usage` | Cumulative stage usage, read from the mounted home directory |
| `extra_mounts` | Optional per-stage mounts |

- Delta polls usage every 2 seconds and appends increments to the ledger. A crash loses at most one poll.
- Delta enforces the token budget between model requests. One request can overshoot it.
- The CLI version is pinned in `images/Dockerfile`.

| Harness | Auth | Usage source | Status |
|---|---|---|---|
| Codex CLI 0.166.0 | `CODEX_API_KEY` (from `OpenAI_API_Key` in `.env`) | `token_count` events in rollout files | Working |
| Dummy | None | Zero | Working; copies the reference solution, for free pipeline tests |
| Pi | OpenAI key | TBD; SCB's MIT-licensed parser available | Next |
| Claude Code | Pro OAuth credentials | TBD | Later |

Codex notes:
- `codex exec` ignores `OPENAI_API_KEY`. It needs `CODEX_API_KEY`.
- Flags go before the `resume` subcommand.
- A resumed session appends to the same rollout file and continues the running total, so Delta takes the latest total per file.
- Codex reports cache writes separately (`cache_write_input_tokens`). `input_tokens` includes cached and cache-write tokens.
- Codex tries to reach `chatgpt.com` for telemetry and plugins. The proxy blocks it without breaking the run.

## Rate Limits

- The adapter detects a rate-limit failure. Quota and billing errors count as fatal, not as rate limits.
- Delta pauses with exponential backoff (60s doubling to 900s, up to 30 pauses), then resumes the same session with the prompt `Continue.`
- Paused time is excluded from the time metric.
- A run can be left unattended overnight.

## Cost and Spend Ledger

- Cost comes from tokens times list prices in `config/prices.toml`.
- Prices are recorded per token class (input, cached input, cache write, output).
- `ledger.jsonl` lives outside all workspaces. It is append-only.
- Every session writes to the ledger, including debug, crashed, and aborted sessions.
- `delta spend` totals spending by model, harness, and day.
- `max_total_spend_usd` is a hard stop. Delta refuses a session if the ledger total plus that stage's worst-case cost would exceed it.
- An OpenAI dashboard spend limit on the key serves as an external backstop.

| Model (API id) | Input | Cached input | Cache write | Output |
|---|---|---|---|---|
| `gpt-6.1-sol` | $2.00 | $0.10 | $2.50 | $10.00 |
| `gpt-6-luna` | $0.10 | $0.01 | $0.125 | $0.50 |

Per million tokens, from third-party sources. Verify on OpenAI's pricing page.

- Worst-case stage cost for the spend cap assumes no cache hits and 10% output.

## Stage Record

One JSON file per stage at `runs/<run-id>/stage-<n>/record.json`.

```json
{
  "run_id": "2026-10-29T14-02-11_codex_luna",
  "problem": "ecommerce",
  "stage": 2,
  "harness": { "name": "codex", "version": "x.y.z" },
  "model": { "name": "gpt-6-luna", "reasoning_effort": "high" },
  "memory": true,
  "budget_tokens": 2000000,
  "outcome": "submitted | budget_exhausted | harness_exited | error | interrupted",
  "error": null,
  "final": { "core": true, "isolated": true, "strict": false, "failing": ["..."] },
  "advanced": true,
  "tokens": { "input": 0, "cached_input": 0, "cache_write": 0, "output": 0, "reasoning": 0, "total": 0 },
  "cost_usd": 0.0,
  "time": { "active_s": 0, "paused_s": 0, "validate_s": 0 },
  "delta_vs_prev_stage": { "tokens": 0, "active_s": 0, "cost_usd": 0.0 },
  "validate_calls": [
    {
      "at_s": 0,
      "duration_s": 0,
      "tokens_so_far": 0,
      "core": false, "isolated": false, "strict": false,
      "passed": 0, "total": 0,
      "failing": [{ "name": "...", "category": "core", "description": "..." }]
    }
  ],
  "pauses": [{ "start_s": 0, "duration_s": 0, "reason": "rate_limit" }]
}
```

- A run summary at `runs/<run-id>/summary.json` aggregates stage records and reports stage reached.
- Each stage directory also keeps `prompt.txt`, `trace.jsonl` (raw harness output), `workspace/` (final snapshot), and `harness-home/` (native state, never carried forward).

## Usage

```
docker build -t delta-sandbox:dev images         # once, and after Dockerfile changes
python -m delta check ecommerce                  # reference solutions must pass strict
python -m delta run --harness dummy              # free end-to-end pipeline test
python -m delta run --harness codex --model gpt-6-luna [--stages 1-2] [--no-memory] [--budget N]
python -m delta spend                            # ledger totals
python -m delta fetch-scb                        # SCB problem set into vendor/
python -m delta image scb:file_backup            # SCB problem image
```

## Repository Layout

```
Delta/
  DESIGN.md
  delta/                 # Python package, stdlib only on the host
    cli.py               # run | spend | check | image | fetch-scb
    runner.py            # stage lifecycle, prompt
    problems.py          # native and SCB problem formats
    sandbox.py           # Docker control
    validate.py          # host side of validate
    test_runner.py       # runs inside the test container
    proxy.py             # egress allowlist proxy
    ledger.py
    pricing.py
    config.py
    harnesses/
      base.py
      codex.py
      dummy.py
  images/
    Dockerfile
    delta-validate       # agent-side validate command
  problems/
    ecommerce/
      stage<n>/
        spec.md
        tests/{core,error,functionality,regression}/
        reference/       # never shown to agents
  config/
    delta.toml           # budget, memory flag, spend cap, allowlist
    prices.toml
  vendor/scb-problems/   # gitignored, fetched on demand
  runs/                  # gitignored
  ledger.jsonl           # gitignored
  .env                   # gitignored
```

## SlopCodeBench Adapter

Delta runs SCB problems in their original format, read in place. Problem names take the form `scb:<name>`.

- `python -m delta fetch-scb` checks out `gabeorlanski/scb-problems` at a pinned commit into `vendor/scb-problems` (gitignored). Delta never commits or redistributes SCB files.
- The fetch disables `core.autocrlf`. Converted line endings change file sizes and checksums and break SCB tests.
- `python -m delta image scb:<name>` builds `delta-scb-<name>:dev` on the base image, baking in the union of the problem's reference-solution requirements, its `test_dependencies`, and SCB's default test packages.

| SCB concept | Delta mapping |
|---|---|
| Checkpoint `n` (by `order`) | Stage `n` |
| `checkpoint_n.md` | Spec, with the leading canary comment stripped and `%%%ENTRYPOINT:…%%%` placeholders filled |
| `entry_file: foo` | Agent writes `/workspace/foo.py`; tests run `python /workspace/foo.py` |
| `tests/test_checkpoint_k.py`, k ≤ n | Hidden tests for stage n (prior files only when `include_prior_tests`) |
| Markers and file | Category, using SCB's priority rules |
| `static_assets` | Copied into the workspace before stage 1 and into `tests/assets/<name>` for tests |
| `solutions/checkpoint_n/` | Reference for `check` and the dummy harness |

- Delta's prompt replaces SCB's `just-solve` prompt, so the agent sees Delta's validate instructions and memory line.
- SCB case tests have no docstrings, so their failing tests show `(no description)`. The case id in the test name still identifies the case.

## Problem Format

- Stage 1 fixes the server contract. `run.sh` at the workspace root serves on `127.0.0.1:$PORT`, and `GET /health` returns 200 when ready.
- The spec lists the baked-in packages as available: fastapi, uvicorn, flask, sqlalchemy, pydantic, httpx, requests, pytest.
- Tests read the base URL from `DELTA_BASE_URL` and must not depend on order or on server state from other tests.
- The current e-commerce stages are placeholders (product catalog, then carts) that exist to exercise the pipeline.

## Tracer Bullet Scope

Done when all of these hold.

- One command runs Codex + Luna through stages 1 and 2 of the e-commerce API.
- Validate gates and auto-submits.
- Each stage writes a complete record and trace.
- The ledger captures every session, and `delta spend` reports totals.
- A rate-limited session pauses and resumes.

## Relation to SlopCodeBench

Delta shares SCB's core setup. Both carry the agent's own code forward, hide tests, use black-box specs, run native harnesses headless in Docker, and use a neutral prompt.

| | SCB | Delta |
|---|---|---|
| Primary metric | Static quality (erosion, verbosity) | Tokens and time to change |
| Test feedback | None | `delta-validate` with failing names and descriptions |
| Stop condition | Agent decides; 2h wall clock | Strict pass or token budget |
| Failed checkpoint | Scored zero; run continues | Run stops unless isolated-correct |
| Agent memory files | Not addressed | Persist by default; flag-controlled |

Delta keeps workspace snapshots, so SCB's erosion and verbosity metrics can run later without new agent runs.

## Open

- Listing available packages in the spec may steer framework choice.
- Real stage specs and tests for the e-commerce problem.
- Pin the remaining image dependencies (base image digest, pip packages to exact versions).
- Curveball placement for longer problems.
- Traffic proxy for exact token accounting.
