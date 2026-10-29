"""Append-only spend ledger shared by every run."""

import json
import time
from collections import defaultdict
from pathlib import Path

from .pricing import Prices, Usage


class Ledger:
    def __init__(self, path: Path, prices: Prices):
        self.path = path
        self.prices = prices

    def record(self, *, run_id: str, stage: int, harness: str, model: str, usage: Usage, kind: str = "agent"):
        """Append one usage increment. Called as usage arrives, so a crash loses little."""
        if usage.total == 0:
            return
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "run_id": run_id,
            "stage": stage,
            "harness": harness,
            "model": model,
            "kind": kind,
            "tokens": usage.to_dict(),
            "cost_usd": round(self.prices.cost(model, usage), 6),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def total_usd(self) -> float:
        return sum(e["cost_usd"] for e in self.entries())

    def summary(self) -> str:
        groups = defaultdict(lambda: [0, 0.0])
        for e in self.entries():
            key = (e["at"][:10], e["harness"], e["model"], e["kind"])
            groups[key][0] += e["tokens"]["total"]
            groups[key][1] += e["cost_usd"]

        lines = [f"{'day':<11} {'harness':<8} {'model':<14} {'kind':<6} {'tokens':>12} {'cost':>10}"]
        for (day, harness, model, kind), (tokens, cost) in sorted(groups.items()):
            lines.append(f"{day:<11} {harness:<8} {model:<14} {kind:<6} {tokens:>12,} {cost:>10.4f}")
        lines.append(f"{'total':<52} {sum(t for t, _ in groups.values()):>12,} {self.total_usd():>10.4f}")
        return "\n".join(lines)
