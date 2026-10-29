"""Command line: delta run | spend | check | image | fetch-scb."""

import argparse
import json
import subprocess
import sys

from . import problems
from .config import LEDGER, load_config, load_secrets
from .harnesses import Codex, Dummy
from .ledger import Ledger
from .pricing import Prices
from .runner import Run, RunSpec
from .validate import validate

HARNESSES = {"codex": Codex, "dummy": Dummy}


def parse_stages(arg: str | None, available: list[int]) -> list[int]:
    if not arg:
        return available
    low, _, high = arg.partition("-")
    return [n for n in available if int(low) <= n <= int(high or low)]


def cmd_run(args, cfg):
    problem = problems.load_problem(args.problem)
    model = "none" if args.harness == "dummy" else args.model
    if model is None:
        raise SystemExit("--model is required")
    spec = RunSpec(
        harness=HARNESSES[args.harness](),
        model=model,
        problem=problem,
        stages=parse_stages(args.stages, problem.stages()),
        memory=cfg.memory if args.memory is None else args.memory,
        budget_tokens=args.budget or cfg.budget_tokens,
        effort=args.effort or cfg.reasoning_effort,
    )
    summary = Run(spec, cfg, load_secrets()).execute()
    print(json.dumps(summary, indent=2))


def cmd_spend(args, cfg):
    print(Ledger(LEDGER, Prices(cfg.prices)).summary())


def cmd_check(args, cfg):
    """Validate each stage's reference solution. Every stage should pass strict."""
    problem = problems.load_problem(args.problem)
    image = problem.image(cfg.image)
    ok = True
    for n in parse_stages(args.stages, problem.stages()):
        result = validate(problem, n, image, problem.reference(n))
        ok &= result["strict"]
        print(f"stage {n}: {result['passed']}/{result['total']} strict={result['strict']}")
        if not result["strict"]:
            print(result["message"])
    sys.exit(0 if ok else 1)


def cmd_image(args, cfg):
    """Build a problem's image on top of the base image."""
    problem = problems.load_problem(args.problem)
    if not isinstance(problem, problems.ScbProblem):
        raise SystemExit(f"{problem.name} uses the base image {cfg.image}. Build it with: docker build -t {cfg.image} images")
    print(f"building {problem.image(cfg.image)} with {', '.join(problem.packages())}")
    problem.build_image(cfg.image)


def cmd_fetch_scb(args, cfg):
    """Check out the SlopCodeBench problem set at the pinned commit. Not committed to this repo."""
    dest = problems.SCB_DIR
    git = lambda *a: subprocess.run(["git", "-c", "core.longpaths=true", "-c", "core.autocrlf=false", "-C", str(dest), *a], check=True)
    if not (dest / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        git("init", "-q")
        git("remote", "add", "origin", problems.SCB_REPO)
    git("config", "core.longpaths", "true")
    git("config", "core.autocrlf", "false")
    git("fetch", "-q", "--depth", "1", "origin", problems.SCB_COMMIT)
    git("checkout", "-q", "--force", problems.SCB_COMMIT)
    print(f"scb-problems at {problems.SCB_COMMIT[:12]} in {dest}")


def main():
    parser = argparse.ArgumentParser(prog="delta")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a harness through a problem")
    run.add_argument("--harness", choices=HARNESSES, required=True)
    run.add_argument("--model")
    run.add_argument("--problem", default="ecommerce", help="native name, or scb:<name>")
    run.add_argument("--stages", help="e.g. 1-2 (default: all)")
    run.add_argument("--memory", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("--budget", type=int, help="tokens per stage")
    run.add_argument("--effort", help="reasoning effort")

    sub.add_parser("spend", help="summarize the spend ledger")

    check = sub.add_parser("check", help="validate a problem's reference solutions")
    check.add_argument("problem", nargs="?", default="ecommerce")
    check.add_argument("--stages")

    image = sub.add_parser("image", help="build an SCB problem's image")
    image.add_argument("problem")

    sub.add_parser("fetch-scb", help="check out the SlopCodeBench problem set")

    args = parser.parse_args()
    cfg = load_config()
    commands = {"run": cmd_run, "spend": cmd_spend, "check": cmd_check, "image": cmd_image, "fetch-scb": cmd_fetch_scb}
    commands[args.command](args, cfg)
