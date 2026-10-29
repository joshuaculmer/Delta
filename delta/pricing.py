"""Token usage and cost."""

from dataclasses import asdict, dataclass, fields


@dataclass
class Usage:
    """Token counts. `input` includes cached and cache-write tokens; `output` includes reasoning."""

    input: int = 0
    cached_input: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    def __sub__(self, other: "Usage") -> "Usage":
        return Usage(*(getattr(self, f.name) - getattr(other, f.name) for f in fields(self)))

    def to_dict(self) -> dict:
        return {**asdict(self), "total": self.total}

    @classmethod
    def from_dict(cls, d: dict) -> "Usage":
        return cls(**{f.name: d.get(f.name, 0) for f in fields(cls)})


class Prices:
    """Per-million-token prices keyed by model name."""

    def __init__(self, table: dict):
        self.table = table

    def rates(self, model: str) -> dict:
        if model not in self.table:
            raise KeyError(f"No prices for model '{model}' in config/prices.toml")
        return self.table[model]

    def cost(self, model: str, usage: Usage) -> float:
        if model == "none":
            return 0.0
        r = self.rates(model)
        uncached = usage.input - usage.cached_input - usage.cache_write
        return (
            uncached * r["input"]
            + usage.cached_input * r["cached_input"]
            + usage.cache_write * r["cache_write"]
            + usage.output * r["output"]
        ) / 1_000_000

    def worst_case(self, model: str, budget_tokens: int, output_share: float) -> float:
        """Cost of a full budget with no cache hits and the given output share."""
        if model == "none":
            return 0.0
        r = self.rates(model)
        output = budget_tokens * output_share
        return ((budget_tokens - output) * r["input"] + output * r["output"]) / 1_000_000
