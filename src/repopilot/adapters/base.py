"""Common interfaces for coding-agent adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentRunResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    trajectory_path: Path
    context_path: Path
    terminal_status: str | None = None

    @property
    def succeeded(self):
        if self.returncode != 0:
            return False

        if self.terminal_status is None:
            return True

        return self.terminal_status == "Submitted"

    def to_dict(self):
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "terminal_status": self.terminal_status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "trajectory_path": str(self.trajectory_path),
            "context_path": str(self.context_path),
            "succeeded": self.succeeded,
        }


class AgentAdapter(ABC):
    @abstractmethod
    def run(
        self,
        project,
        task,
        context,
        output_path,
    ):
        """Run an agent and return its structured result."""
