"""Run a harness through a problem's stages."""

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import sandbox
from .config import LEDGER, RUNS, Config
from .harnesses import Harness
from .ledger import Ledger
from .pricing import Prices, Usage
from .problems import Problem
from .validate import validate

POLL_S = 2

PROMPT = """Implement the specification below in Python. Work only in /workspace.

Run `delta-validate` to check your work. It reports the names and
descriptions of failing tests. When every test passes, your work is
submitted and the session ends.
{memory_line}
Your task is:

{spec}
"""

MEMORY_LINE = "\nFiles you leave in the workspace persist to future tasks.\n"

# Sent when a session resumes after a rate-limit pause. Identical for every harness.

RESUME_PROMPT = "Continue."


@dataclass
class RunSpec:
    harness: Harness
    model: str
    problem: Problem
    stages: list[int]
    memory: bool
    budget_tokens: int
    effort: str


def render_prompt(spec: str, memory: bool) -> str:
    return PROMPT.format(memory_line=MEMORY_LINE if memory else "", spec=spec.strip())


def strip_memory(workspace: Path, patterns: list[str]):
    for pattern in patterns:
        for path in workspace.glob(pattern):
            if path.is_file():
                path.unlink()


def redact(root: Path, secrets: list[str]):
    """Replace secret values in every file under root.

    Harnesses can write their environment to disk. Codex shell snapshots do.
    """
    needles = [s.encode() for s in secrets if len(s) >= 8]
    for path in root.rglob("*"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            data = path.read_bytes()
        except OSError:
            continue
        cleaned = data
        for needle in needles:
            cleaned = cleaned.replace(needle, b"[REDACTED]")
        if cleaned != data:
            path.write_bytes(cleaned)


class OutputReader(threading.Thread):
    """Copies harness output to the trace file and tracks the events Delta acts on."""

    def __init__(self, proc, harness: Harness, trace):
        super().__init__(daemon=True)
        self.proc, self.harness, self.trace = proc, harness, trace
        self.session_id = None
        self.rate_limited = False
        self.fatal = None

    def run(self):
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", errors="replace")
            self.trace.write(line)
            self.trace.flush()
            event = self.harness.parse_line(line)
            self.session_id = event.session_id or self.session_id
            self.rate_limited = self.rate_limited or event.rate_limited
            self.fatal = event.fatal or self.fatal


class Run:
    def __init__(self, spec: RunSpec, cfg: Config, secrets: dict[str, str]):
        self.spec, self.cfg, self.secrets = spec, cfg, secrets
        self.prices = Prices(cfg.prices)
        self.ledger = Ledger(LEDGER, self.prices)
        problem_slug = spec.problem.name.replace(":", "-")
        self.run_id = f"{time.strftime('%Y-%m-%dT%H-%M-%S')}_{problem_slug}_{spec.harness.name}_{spec.model}"
        self.dir = RUNS / self.run_id

    def execute(self) -> dict:
        self.image = self.spec.problem.image(self.cfg.image)
        sandbox.require_image(self.image)
        sandbox.ensure_proxy(self.cfg.image, self.cfg.allow_hosts)
        self.harness_version = self.spec.harness.version(self.image)
        self.dir.mkdir(parents=True)
        print(f"run {self.run_id}")

        records, prev_workspace, reached = [], None, 0
        for n in self.spec.stages:
            worst = self.prices.worst_case(self.spec.model, self.spec.budget_tokens, self.cfg.worst_case_output_share)
            spent = self.ledger.total_usd()
            if spent + worst > self.cfg.max_total_spend_usd:
                print(f"stage {n} refused: ledger ${spent:.2f} + worst case ${worst:.2f} exceeds cap ${self.cfg.max_total_spend_usd:.2f}")
                break

            record = self.run_stage(n, prev_workspace, records[-1] if records else None)
            records.append(record)
            print(f"stage {n}: {record['outcome']}, isolated={record['final']['isolated']}, "
                  f"strict={record['final']['strict']}, tokens={record['tokens']['total']:,}, "
                  f"cost=${record['cost_usd']:.4f}, active={record['time']['active_s']:.0f}s")
            if not record["advanced"]:
                break
            reached = n
            prev_workspace = self.dir / f"stage-{n}" / "workspace"

        summary = {
            "run_id": self.run_id,
            "problem": self.spec.problem.name,
            "harness": {"name": self.spec.harness.name, "version": self.harness_version},
            "model": self.spec.model,
            "memory": self.spec.memory,
            "stages_attempted": [r["stage"] for r in records],
            "stage_reached": reached,
            "tokens_total": sum(r["tokens"]["total"] for r in records),
            "cost_usd": round(sum(r["cost_usd"] for r in records), 6),
            "active_s": round(sum(r["time"]["active_s"] for r in records), 1),
        }
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary

    def run_stage(self, n: int, prev_workspace: Path | None, prev_record: dict | None) -> dict:
        spec, harness, problem = self.spec, self.spec.harness, self.spec.problem
        stage_dir = self.dir / f"stage-{n}"
        workspace, home, ipc = stage_dir / "workspace", stage_dir / "harness-home", stage_dir / "ipc"

        if prev_workspace:
            shutil.copytree(prev_workspace, workspace, symlinks=True)
            if not spec.memory:
                strip_memory(workspace, self.cfg.memory_strip)
        else:
            workspace.mkdir(parents=True)
            problem.seed(workspace)
        home.mkdir()
        (ipc / "requests").mkdir(parents=True)
        (ipc / "responses").mkdir()

        prompt = render_prompt(problem.spec(n), spec.memory)
        (stage_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

        mounts = [
            *sandbox.mount(workspace, "/workspace"),
            *sandbox.mount(home, harness.home),
            *sandbox.mount(ipc, "/delta-ipc"),
            *harness.extra_mounts(problem.reference(n)),
        ]
        container = sandbox.AgentContainer(
            f"delta-{self.run_id}-s{n}".replace(":", "-").replace(".", "-"),
            self.image, mounts, harness.env(self.secrets),
        )

        recorded = Usage()
        validate_calls, pauses = [], []
        started, paused_s = time.monotonic(), 0.0
        backoff = self.cfg.initial_backoff_s
        outcome = None
        active = lambda: time.monotonic() - started - paused_s

        def ledger_sync() -> Usage:
            nonlocal recorded
            usage = harness.usage(home)
            self.ledger.record(run_id=self.run_id, stage=n, harness=harness.name, model=spec.model, usage=usage - recorded)
            recorded = usage
            return usage

        trace = (stage_dir / "trace.jsonl").open("w", encoding="utf-8")
        proc = container.exec(harness.command(prompt, spec.model, spec.effort), stdout=subprocess.PIPE)
        reader = OutputReader(proc, harness, trace)
        reader.start()

        try:
            while outcome is None:
                time.sleep(POLL_S)
                usage = ledger_sync()
                if usage.total >= spec.budget_tokens:
                    outcome = "budget_exhausted"
                    break

                for request in sorted((ipc / "requests").glob("*.json")):
                    result = validate(problem, n, self.image, workspace)
                    validate_calls.append({
                        "at_s": round(active(), 1),
                        "tokens_so_far": usage.total,
                        **{k: v for k, v in result.items() if k != "message"},
                    })
                    response = ipc / "responses" / request.name
                    response.with_suffix(".tmp").write_text(json.dumps({"strict": result["strict"], "message": result["message"]}))
                    response.with_suffix(".tmp").replace(response)
                    request.unlink()
                    if result["strict"]:
                        outcome = "submitted"
                        break

                if outcome is None and proc.poll() is not None:
                    reader.join(timeout=5)
                    if reader.rate_limited and reader.session_id and len(pauses) < self.cfg.max_pauses:
                        print(f"stage {n}: rate limited, pausing {backoff}s")
                        pause_start = time.monotonic()
                        time.sleep(backoff)
                        pauses.append({"start_s": round(active(), 1), "duration_s": backoff, "reason": "rate_limit"})
                        paused_s += time.monotonic() - pause_start
                        backoff = min(backoff * 2, self.cfg.max_backoff_s)
                        proc = container.exec(
                            harness.resume_command(reader.session_id, RESUME_PROMPT, spec.model, spec.effort), stdout=subprocess.PIPE,
                        )
                        session_id = reader.session_id
                        reader = OutputReader(proc, harness, trace)
                        reader.session_id = session_id
                        reader.start()
                        continue
                    outcome = "error" if reader.fatal else "harness_exited"
        except KeyboardInterrupt:
            outcome = "interrupted"
        finally:
            proc.kill()
            container.remove()
            reader.join(timeout=5)
            trace.close()
            active_s = active()
            usage = ledger_sync()
            redact(stage_dir, list(self.secrets.values()))

        final = validate(problem, n, self.image, workspace)
        cost = self.prices.cost(spec.model, usage)
        record = {
            "run_id": self.run_id,
            "problem": problem.name,
            "stage": n,
            "harness": {"name": harness.name, "version": self.harness_version},
            "model": {"name": spec.model, "reasoning_effort": spec.effort},
            "memory": spec.memory,
            "budget_tokens": spec.budget_tokens,
            "outcome": outcome,
            "error": reader.fatal,
            "final": {k: final[k] for k in ("core", "isolated", "strict", "passed", "total", "failing")},
            "advanced": final["isolated"] and outcome != "interrupted",
            "tokens": usage.to_dict(),
            "cost_usd": round(cost, 6),
            "time": {
                "active_s": round(active_s, 1),
                "paused_s": round(paused_s, 1),
                "validate_s": round(sum(c["duration_s"] for c in validate_calls), 1),
            },
            "delta_vs_prev_stage": None if prev_record is None else {
                "tokens": usage.total - prev_record["tokens"]["total"],
                "active_s": round(active_s - prev_record["time"]["active_s"], 1),
                "cost_usd": round(cost - prev_record["cost_usd"], 6),
            },
            "validate_calls": validate_calls,
            "pauses": pauses,
        }
        (stage_dir / "record.json").write_text(json.dumps(record, indent=2))
        if outcome == "interrupted":
            raise KeyboardInterrupt
        return record
