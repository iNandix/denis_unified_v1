"""Data models for sprint orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@dataclass(frozen=True)
class GitProjectStatus:
    path: str
    name: str
    branch: str
    dirty: bool
    ahead: int
    behind: int
    head_sha: str
    last_commit: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkerAssignment:
    worker_id: str
    role: str
    provider: str
    task: str
    project_path: str
    priority: str = "medium"
    status: str = "planned"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SprintSession:
    session_id: str
    created_utc: str
    prompt: str
    workers_requested: int
    projects: list[GitProjectStatus]
    assignments: list[WorkerAssignment]
    status: str = "active"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["projects"] = [project.as_dict() for project in self.projects]
        payload["assignments"] = [assignment.as_dict() for assignment in self.assignments]
        return payload


@dataclass(frozen=True)
class SprintEvent:
    session_id: str
    worker_id: str
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: new_id("evt"))
    timestamp_utc: str = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
