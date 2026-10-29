"""Runs inside the offline test container.

Reads /out/job.json, runs /tests with pytest against /workspace, and writes /out/results.json.

Modes:
- http: start the submission with run.sh, wait for GET /health, test over HTTP.
- scb:  SlopCodeBench tests, which launch the entrypoint themselves.
"""

import inspect
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

PORT = 8000
BASE_URL = f"http://127.0.0.1:{PORT}"
STARTUP_TIMEOUT_S = 30


def http_category(item, job) -> str:
    return Path(item.path).relative_to("/tests").parts[0]


def scb_category(item, job) -> str:
    """SlopCodeBench's grouping rules, in their priority order."""
    if Path(item.path).name != f"test_{job['checkpoint']}.py":
        return "regression"
    markers = {m.name for m in item.iter_markers()}
    if "error" in markers:
        return "error"
    if "regression" in markers:
        return "regression"
    for marker in markers:
        if marker in job["custom_markers"]:
            return job["custom_markers"][marker]
    if "functionality" in markers:
        return "functionality"
    return "core"


class Collector:
    def __init__(self, job):
        self.job = job
        self.category = scb_category if job["mode"] == "scb" else http_category
        self.tests = {}
        self.collection_error = False

    def pytest_collection_modifyitems(self, items):
        for item in items:
            doc = inspect.getdoc(getattr(item, "obj", None)) or ""
            self.tests[item.nodeid] = {
                "name": item.name, "category": self.category(item, self.job), "description": doc, "passed": False,
            }

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_error = True

    def pytest_runtest_logreport(self, report):
        test = self.tests.get(report.nodeid)
        if test is None:
            return
        if report.when == "call":
            test["passed"] = report.passed
        elif report.failed:
            test["passed"] = False


def server_healthy() -> bool:
    deadline = time.time() + STARTUP_TIMEOUT_S
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def run_http(job, collector):
    os.environ["DELTA_BASE_URL"] = BASE_URL
    has_entry = Path("/workspace/run.sh").exists()
    server = None
    if has_entry:
        with open("/out/server.log", "w") as log:
            server = subprocess.Popen(
                ["bash", "run.sh"], cwd="/workspace", stdout=log, stderr=subprocess.STDOUT,
                env={**os.environ, "PORT": str(PORT)}, start_new_session=True,
            )
    healthy = has_entry and server_healthy()
    pytest.main(["/tests", "-q", "-p", "no:cacheprovider", "--import-mode=importlib", "--rootdir=/tests"], plugins=[collector])
    if server is not None:
        try:
            os.killpg(server.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return has_entry, healthy


def run_scb(job, collector):
    os.environ.update(job["env"])
    os.chdir("/workspace")
    pytest.main([
        "/tests", "-q", "-p", "no:cacheprovider", "--rootdir=/tests", "--confcutdir=/tests",
        f"--entrypoint={job['entrypoint']}", f"--checkpoint={job['checkpoint']}", f"--timeout={job['timeout']}",
    ], plugins=[collector])
    return Path("/workspace", job["entry_file"]).exists(), True


def main():
    job = json.loads(Path("/out/job.json").read_text())
    collector = Collector(job)
    has_entry, healthy = (run_scb if job["mode"] == "scb" else run_http)(job, collector)
    with open("/out/results.json", "w") as f:
        json.dump({
            "has_entry": has_entry,
            "healthy": healthy,
            "collection_error": collector.collection_error,
            "tests": list(collector.tests.values()),
        }, f, indent=2)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
