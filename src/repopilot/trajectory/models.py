"""Structured trajectory event models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PathReference:
    path: str
    category: str

    def to_dict(self):
        return {
            "path": self.path,
            "category": self.category,
        }


@dataclass(frozen=True)
class CommandEvent:
    index: int
    call_id: str
    command: str
    status: str
    returncode: int | None
    output: str
    exception_info: str | None
    started_at: float | None
    completed_at: float | None
    paths: tuple[PathReference, ...]

    def to_dict(self):
        return {
            "index": self.index,
            "call_id": self.call_id,
            "command": self.command,
            "status": self.status,
            "returncode": self.returncode,
            "output": self.output,
            "exception_info": self.exception_info,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "paths": [
                path.to_dict()
                for path in self.paths
            ],
        }


@dataclass(frozen=True)
class ParsedTrajectory:
    source_path: str
    trajectory_format: str | None
    exit_status: str | None
    model: str | None
    api_calls: int | None
    cost: float | None
    events: tuple[CommandEvent, ...]

    def to_dict(self):
        return {
            "schema_version": 1,
            "source_path": self.source_path,
            "trajectory_format": self.trajectory_format,
            "exit_status": self.exit_status,
            "model": self.model,
            "api_calls": self.api_calls,
            "cost": self.cost,
            "event_count": len(self.events),
            "events": [
                event.to_dict()
                for event in self.events
            ],
        }
