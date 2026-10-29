"""Zero-cost harness for testing the pipeline.

Copies the stage's reference solution into the workspace and calls delta-validate.
"""

from pathlib import Path

from .. import sandbox
from ..pricing import Usage
from .base import Event, Harness


class Dummy(Harness):
    name = "dummy"
    home = "/dummy-home"

    def version(self, image: str) -> str:
        return "0"

    def env(self, secrets):
        return {}

    def command(self, prompt, model, effort):
        return ["bash", "-c", "cp -r /reference/. /workspace/ && delta-validate"]

    def resume_command(self, session_id, prompt, model, effort):
        return self.command(prompt, model, effort)

    def parse_line(self, line):
        return Event()

    def usage(self, home):
        return Usage()

    def extra_mounts(self, reference: Path):
        return sandbox.mount(reference, "/reference", readonly=True)
