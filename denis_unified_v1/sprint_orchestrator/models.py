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
    phase: str = ""

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
        payload["assignments"] = [
            assignment.as_dict() for assignment in self.assignments
        ]
        return payload


@dataclass(frozen=True)
class SprintTask:
    """A concrete task assigned to a worker."""

    task_id: str
    session_id: str
    worker_id: str
    kind: str  # e.g., "qcli.search", "implementation", "validation"
    description: str
    project_path: str  # Path to project root for this task
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, done, error
    created_utc: str = field(default_factory=utc_now)
    started_utc: str | None = None
    completed_utc: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SprintEvent:
    session_id: str
    worker_id: str
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: new_id("evt"))
    timestamp_utc: str = field(default_factory=utc_now)
    trace_id: str | None = None
    task_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventEnvelope:
    event: SprintEvent
    envelope_id: str = field(default_factory=lambda: new_id("env"))
    published_utc: str = field(default_factory=utc_now)
    source: str = "sprint_orchestrator"  # e.g., "cli", "worker", "bus"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event"] = self.event.as_dict()
        return payload
