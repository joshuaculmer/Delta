"""Docker control: the egress proxy, agent containers, and test containers."""

import os
import subprocess
from pathlib import Path

from .config import ROOT

NETWORK = "delta-internal"
PROXY = "delta-proxy"
PROXY_PORT = 3128
PROXY_URL = f"http://{PROXY}:{PROXY_PORT}"


def docker(*args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=check, env=env)


def mount(source: Path, target: str, readonly: bool = False) -> list[str]:
    spec = f"type=bind,source={source.resolve()},target={target}"
    return ["--mount", spec + (",readonly" if readonly else "")]


def require_image(image: str):
    if docker("image", "inspect", image, check=False).returncode != 0:
        raise SystemExit(f"Image {image} not found. Build it with: docker build -t {image} images")


def ensure_proxy(image: str, allow_hosts: list[str]):
    """Start the allowlist proxy on an internal network. Agent containers reach the internet only through it."""
    if docker("network", "inspect", NETWORK, check=False).returncode != 0:
        docker("network", "create", "--internal", NETWORK)

    # Restart every time so the allowlist always matches config.

    docker("rm", "-f", PROXY, check=False)
    docker(
        "run", "-d", "--name", PROXY,
        *mount(ROOT / "delta" / "proxy.py", "/proxy.py", readonly=True),
        image, "python", "/proxy.py", str(PROXY_PORT), *allow_hosts,
    )
    docker("network", "connect", "--alias", PROXY, NETWORK, PROXY)


class AgentContainer:
    """A long-lived container the harness runs inside for one stage."""

    def __init__(self, name: str, image: str, mounts: list[str], env: dict[str, str]):
        self.name = name
        self.env = env
        env_flags = [flag for key in env for flag in ("-e", key)]
        docker("rm", "-f", name, check=False)
        docker(
            "run", "-d", "--name", name, "--network", NETWORK,
            "-e", f"HTTPS_PROXY={PROXY_URL}", "-e", f"HTTP_PROXY={PROXY_URL}",
            "-e", "NO_PROXY=localhost,127.0.0.1",
            *env_flags, *mounts, image, "sleep", "infinity",
            env={**os.environ, **env},
        )

    def exec(self, command: list[str], stdout) -> subprocess.Popen:
        """Run a command in the container. Secrets pass by name so they never appear in argv."""
        env_flags = [flag for key in self.env for flag in ("-e", key)]
        return subprocess.Popen(
            ["docker", "exec", *env_flags, self.name, *command],
            stdout=stdout, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, **self.env},
        )

    def remove(self):
        docker("rm", "-f", self.name, check=False)


def build(tag: str, dockerfile: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "build", "-t", tag, "-"], input=dockerfile, capture_output=True, text=True, encoding="utf-8", errors="replace")


def run_tests(image: str, submission: Path, tests: Path, out: Path, timeout_s: int = 1800) -> subprocess.CompletedProcess:
    """Run hidden tests against a copy of the workspace in an offline container.

    `out` holds job.json going in and results.json coming back.
    """
    return subprocess.run(
        [
            "docker", "run", "--rm", "--network", "none",
            *mount(submission, "/workspace"),
            *mount(tests, "/tests"),
            *mount(ROOT / "delta" / "test_runner.py", "/delta/test_runner.py", readonly=True),
            *mount(out, "/out"),
            image, "python", "/delta/test_runner.py",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
    )
