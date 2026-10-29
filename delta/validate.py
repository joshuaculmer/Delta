"""Host side of validate: run hidden tests, score levels, and format feedback for the agent."""

import json
import shutil
import tempfile
import time
from pathlib import Path

from . import sandbox
from .problems import Problem

ISOLATED_CATEGORIES = {"core", "error", "functionality"}


def validate(problem: Problem, n: int, image: str, workspace: Path) -> dict:
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="delta-validate-") as tmp:
        scratch = Path(tmp)
        job = problem.prepare_tests(n, scratch)

        # Tests always run from a scratch copy, so agent code can't alter the originals.

        tests = job.tests
        if scratch not in tests.parents:
            tests = shutil.copytree(job.tests, scratch / "tests")

        submission = shutil.copytree(workspace, scratch / "submission", symlinks=True)
        out = scratch / "out"
        out.mkdir()
        (out / "job.json").write_text(json.dumps(job.job))
        proc = sandbox.run_tests(image, submission, tests, out)
        results_path = out / "results.json"
        if not results_path.exists():
            raise RuntimeError(f"Test runner produced no results:\n{proc.stdout}\n{proc.stderr}")
        raw = json.loads(results_path.read_text())

    tests_ = raw["tests"]
    failing = [t for t in tests_ if not t["passed"]]
    result = {
        "duration_s": round(time.time() - started, 2),
        "mode": job.job["mode"],
        "has_entry": raw["has_entry"],
        "healthy": raw["healthy"],
        "collection_error": raw.get("collection_error", False),
        "core": all(t["passed"] for t in tests_ if t["category"] == "core"),
        "isolated": all(t["passed"] for t in tests_ if t["category"] in ISOLATED_CATEGORIES),
        "strict": bool(tests_) and not failing and not raw.get("collection_error"),
        "passed": len(tests_) - len(failing),
        "total": len(tests_),
        "failing": [{k: t[k] for k in ("name", "category", "description")} for t in failing],
    }
    result["message"] = format_message(result, job.job)
    return result


def format_message(r: dict, job: dict) -> str:
    """Feedback shown to the agent: levels plus names and descriptions of failing tests."""
    if r["strict"]:
        return f"All {r['total']} tests passed. Your work has been submitted."

    lines = []
    if job["mode"] == "http" and not r["has_entry"]:
        lines.append("No run.sh found in /workspace.")
    elif job["mode"] == "http" and not r["healthy"]:
        lines.append("Server did not answer GET /health with 200 within 30 seconds.")
    elif job["mode"] == "scb" and not r["has_entry"]:
        lines.append(f"No {job['entry_file']} found in /workspace.")
    if r["collection_error"]:
        lines.append("The test suite could not be collected.")

    mark = lambda ok: "PASS" if ok else "FAIL"
    lines += [
        f"{r['passed']}/{r['total']} tests passed.",
        f"core: {mark(r['core'])}  isolated: {mark(r['isolated'])}  strict: {mark(r['strict'])}",
        "",
        "Failing tests:",
    ]
    for t in r["failing"]:
        lines.append(f"- [{t['category']}] {t['name']}: {t['description'] or '(no description)'}")
    return "\n".join(lines)
