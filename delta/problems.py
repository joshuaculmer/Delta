"""Problem sources.

A problem supplies stage specs, hidden tests, reference solutions, and the image its
agents and tests run in. Delta reads two formats:

- Native: problems/<name>/stage<n>/{spec.md, tests/<category>/, reference/}
- SlopCodeBench: scb:<name>, read in place from a local scb-problems checkout
"""

import json
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import sandbox
from .config import PROBLEMS, ROOT

SCB_PREFIX = "scb:"
SCB_DIR = ROOT / "vendor" / "scb-problems"
SCB_REPO = "https://github.com/gabeorlanski/scb-problems"
SCB_COMMIT = "9cd9ca3a51c3d3e2a99d2488a25baf73a2204451"

# SCB marks the first lines of a spec with an HTML-comment canary. SCB strips it
# before showing the spec to agents, and so does Delta.

SCB_CANARY = re.compile(r"^<!-- [\s\S]+? -->\n?")

# Packages SCB's runner always provides to its tests.

SCB_TEST_PACKAGES = ["pytest-timeout", "jsonschema", "deepdiff"]


@dataclass
class TestJob:
    """Everything the test container needs, written to /out/job.json."""

    tests: Path
    job: dict


class Problem(ABC):
    name: str

    @abstractmethod
    def stages(self) -> list[int]: ...

    @abstractmethod
    def spec(self, n: int) -> str: ...

    @abstractmethod
    def reference(self, n: int) -> Path: ...

    @abstractmethod
    def prepare_tests(self, n: int, scratch: Path) -> TestJob:
        """Lay out stage n's tests under scratch and describe how to run them."""

    def image(self, base: str) -> str:
        return base

    def seed(self, workspace: Path):
        """Populate an empty workspace before stage 1."""


class NativeProblem(Problem):
    def __init__(self, name: str):
        self.name = name
        self.dir = PROBLEMS / name
        if not self.dir.is_dir():
            raise SystemExit(f"No problem at problems/{name}")

    def stages(self):
        return sorted(int(p.name.removeprefix("stage")) for p in self.dir.glob("stage*") if p.is_dir())

    def spec(self, n):
        return (self.dir / f"stage{n}" / "spec.md").read_text(encoding="utf-8")

    def reference(self, n):
        return self.dir / f"stage{n}" / "reference"

    def prepare_tests(self, n, scratch):
        return TestJob(tests=self.dir / f"stage{n}" / "tests", job={"mode": "http"})


class ScbProblem(Problem):
    def __init__(self, name: str):
        self.name = SCB_PREFIX + name
        self.dir = SCB_DIR / name
        if not (self.dir / "config.yaml").exists():
            raise SystemExit(f"No SCB problem '{name}'. Fetch the problem set with: python -m delta fetch-scb")
        self.config = yaml.safe_load((self.dir / "config.yaml").read_text(encoding="utf-8"))
        self.checkpoints = sorted(self.config["checkpoints"].items(), key=lambda kv: kv[1]["order"])
        self.entry_file = f"{self.config['entry_file']}.py"
        self.entry_command = f"python {self.entry_file}"

    def checkpoint(self, n: int) -> tuple[str, dict]:
        return self.checkpoints[n - 1]

    def stages(self):
        return list(range(1, len(self.checkpoints) + 1))

    def spec(self, n):
        text = (self.dir / f"{self.checkpoint(n)[0]}.md").read_text(encoding="utf-8")
        text = SCB_CANARY.sub("", text)
        return (
            text.replace("%%%ENTRYPOINT:entry_command%%%", self.entry_command)
            .replace("%%%ENTRYPOINT:entry_file%%%", self.entry_file)
        )

    def reference(self, n):
        return self.dir / "solutions" / self.checkpoint(n)[0]

    def assets(self) -> dict[str, dict]:
        return self.config.get("static_assets") or {}

    def seed(self, workspace):
        for asset in self.assets().values():
            source = self.dir / asset["path"]
            target = workspace / asset.get("save_path", asset["path"])
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def prepare_tests(self, n, scratch):
        name, checkpoint = self.checkpoint(n)
        include_prior = checkpoint.get("include_prior_tests", True)
        later = {f"test_{c}.py" for c, _ in self.checkpoints[n:]}
        prior = {f"test_{c}.py" for c, _ in self.checkpoints[: n - 1]}
        excluded = later | (set() if include_prior else prior)

        tests = scratch / "tests"
        shutil.copytree(self.dir / "tests", tests, ignore=lambda d, names: [x for x in names if x in excluded])

        env = {"SCBENCH_CHECKPOINT": name}
        if self.assets():
            env["SCBENCH_ASSETS_DIR"] = "/tests/assets"
            for asset_name, asset in self.assets().items():
                source = self.dir / asset["path"]
                target = tests / "assets" / asset_name
                if source.is_dir():
                    shutil.copytree(source, target, dirs_exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                env[f"SCBENCH_ASSET_{asset_name.upper()}"] = f"/tests/assets/{asset_name}"

        markers = {k: v.get("group", "FUNCTIONALITY").lower() for k, v in (self.config.get("markers") or {}).items()}
        return TestJob(tests=tests, job={
            "mode": "scb",
            "entry_file": self.entry_file,
            "entrypoint": f"python /workspace/{self.entry_file}",
            "checkpoint": name,
            "timeout": checkpoint.get("timeout") or self.config.get("timeout") or 30,
            "custom_markers": markers,
            "env": env,
        })

    def packages(self) -> list[str]:
        """Union of reference-solution requirements and test dependencies."""
        packages = set(SCB_TEST_PACKAGES) | set(self.config.get("test_dependencies") or [])
        for requirements in (self.dir / "solutions").glob("checkpoint_*/requirements.txt"):
            for line in requirements.read_text(encoding="utf-8").splitlines():
                line = line.split("#")[0].strip()
                if line and not line.startswith("-"):
                    packages.add(line)
        return sorted(packages)

    def image(self, base):
        return f"delta-scb-{self.config['name'].replace('_', '-')}:dev"

    def build_image(self, base: str):
        """Build the problem image: the base image plus the problem's packages, baked in."""
        dockerfile = (
            f"FROM {base}\nUSER root\n"
            f"RUN pip install --no-cache-dir {' '.join(json.dumps(p) for p in self.packages())}\n"
            "USER agent\n"
        )
        result = sandbox.build(self.image(base), dockerfile)
        if result.returncode != 0:
            raise SystemExit(result.stdout + result.stderr)


def load_problem(name: str) -> Problem:
    if name.startswith(SCB_PREFIX):
        return ScbProblem(name.removeprefix(SCB_PREFIX))
    return NativeProblem(name)
