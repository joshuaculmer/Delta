"""Paths, config files, and secrets."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBLEMS = ROOT / "problems"
RUNS = ROOT / "runs"
LEDGER = ROOT / "ledger.jsonl"


@dataclass
class Config:
    image: str
    budget_tokens: int
    memory: bool
    memory_strip: list[str]
    reasoning_effort: str
    max_total_spend_usd: float
    worst_case_output_share: float
    allow_hosts: list[str]
    initial_backoff_s: int
    max_backoff_s: int
    max_pauses: int
    prices: dict


def load_config() -> Config:
    with (ROOT / "config" / "delta.toml").open("rb") as f:
        c = tomllib.load(f)
    with (ROOT / "config" / "prices.toml").open("rb") as f:
        prices = tomllib.load(f)["models"]
    return Config(
        image=c["sandbox"]["image"],
        budget_tokens=c["run"]["budget_tokens"],
        memory=c["run"]["memory"],
        memory_strip=c["run"]["memory_strip"],
        reasoning_effort=c["run"]["reasoning_effort"],
        max_total_spend_usd=c["spend"]["max_total_spend_usd"],
        worst_case_output_share=c["spend"]["worst_case_output_share"],
        allow_hosts=c["sandbox"]["allow_hosts"],
        initial_backoff_s=c["rate_limit"]["initial_backoff_s"],
        max_backoff_s=c["rate_limit"]["max_backoff_s"],
        max_pauses=c["rate_limit"]["max_pauses"],
        prices=prices,
    )


def load_secrets() -> dict[str, str]:
    """Read KEY=VALUE pairs from .env. Keys are lowercased."""
    path = ROOT / ".env"
    secrets = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                secrets[key.strip().lower()] = value.strip().strip('"').strip("'")
    return secrets
