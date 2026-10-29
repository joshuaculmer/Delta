"""OpenAI Codex CLI adapter.

Usage comes from token_count events in Codex rollout files. Each event carries the
session's running total, and a resumed session appends to the same file, so the
latest total per file is the session's usage.
"""

import json
import re
from pathlib import Path

from .. import sandbox
from ..pricing import Usage
from .base import Event, Harness

RATE_LIMIT = re.compile(r"\b429\b|rate.?limit", re.IGNORECASE)
NO_QUOTA = re.compile(r"insufficient_quota|quota exceeded|billing", re.IGNORECASE)


class Codex(Harness):
    name = "codex"
    home = "/codex-home"

    def version(self, image: str) -> str:
        out = sandbox.docker("run", "--rm", image, "codex", "--version").stdout
        return out.strip().removeprefix("codex-cli ").strip()

    def env(self, secrets: dict[str, str]) -> dict[str, str]:
        key = secrets.get("openai_api_key") or secrets.get("codex_api_key")
        if not key:
            raise SystemExit("Missing OpenAI_API_Key in .env")
        return {"CODEX_API_KEY": key, "CODEX_HOME": self.home}

    def _flags(self, model: str, effort: str) -> list[str]:
        return [
            "--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
            "-m", model, "-c", f'model_reasoning_effort="{effort}"',
        ]

    def command(self, prompt, model, effort):
        return ["codex", "exec", *self._flags(model, effort), "-C", "/workspace", prompt]

    def resume_command(self, session_id, prompt, model, effort):
        return ["codex", "exec", *self._flags(model, effort), "resume", session_id, prompt]

    def parse_line(self, line: str) -> Event:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return Event()

        if event.get("type") == "thread.started":
            return Event(session_id=event.get("thread_id"))

        # Codex retries transient errors itself. Only a failed turn ends the session.

        if event.get("type") == "turn.failed":
            message = event.get("error", {}).get("message", "")
            if RATE_LIMIT.search(message) and not NO_QUOTA.search(message):
                return Event(rate_limited=True)
            return Event(fatal=message or "turn failed")
        return Event()

    def usage(self, home: Path) -> Usage:
        total = Usage()
        for rollout in (home / "sessions").rglob("rollout-*.jsonl"):
            latest = None
            for line in rollout.read_text(encoding="utf-8", errors="replace").splitlines():
                if '"token_count"' not in line:
                    continue
                try:
                    info = json.loads(line)["payload"].get("info") or {}
                except (json.JSONDecodeError, KeyError):
                    continue
                latest = info.get("total_token_usage") or latest
            if latest:
                total += Usage(
                    input=latest.get("input_tokens", 0),
                    cached_input=latest.get("cached_input_tokens", 0),
                    cache_write=latest.get("cache_write_input_tokens", 0),
                    output=latest.get("output_tokens", 0),
                    reasoning=latest.get("reasoning_output_tokens", 0),
                )
        return total
