"""Interface every harness adapter implements."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..pricing import Usage


@dataclass
class Event:
    """What Delta needs from one line of harness output."""

    session_id: str | None = None
    rate_limited: bool = False
    fatal: str | None = None


class Harness(ABC):
    name: str

    # Where the harness keeps native state inside the container. Delta mounts a fresh
    # per-stage directory here, so native memory never crosses stages.

    home: str

    @abstractmethod
    def version(self, image: str) -> str: ...

    @abstractmethod
    def env(self, secrets: dict[str, str]) -> dict[str, str]: ...

    @abstractmethod
    def command(self, prompt: str, model: str, effort: str) -> list[str]: ...

    @abstractmethod
    def resume_command(self, session_id: str, prompt: str, model: str, effort: str) -> list[str]: ...

    @abstractmethod
    def parse_line(self, line: str) -> Event: ...

    @abstractmethod
    def usage(self, home: Path) -> Usage:
        """Cumulative usage for the stage, read from the mounted home directory."""

    def extra_mounts(self, reference: Path) -> list[str]:
        """Extra mounts for a stage, given the stage's reference solution."""
        return []
