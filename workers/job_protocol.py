"""Job protocol for async worker execution."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict
import uuid

@dataclass
class JobRequest:
    job_id: str
    phase: str
    task: str
    args: Dict[str, Any]
    created_utc: datetime

    @classmethod
    def create(cls, phase: str, task: str, args: Dict[str, Any]) -> 'JobRequest':
        return cls(
            job_id=str(uuid.uuid4()),
            phase=phase,
            task=task,
            args=args,
            created_utc=datetime.now(timezone.utc)
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "phase": self.phase,
            "task": self.task,
            "args": self.args,
            "created_utc": self.created_utc.isoformat()
        }

@dataclass
class JobResult:
    job_id: str
    phase: str
    task: str
    status: str  # ok, degraded, skipped, error_internal
    started_utc: datetime
    finished_utc: datetime
    duration_ms: int
    outputs: Dict[str, Any]
    warnings: list[str]
    errors: list[str]
    skipped: bool
    metrics: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "phase": self.phase,
            "task": self.task,
            "status": self.status,
            "started_utc": self.started_utc.isoformat(),
            "finished_utc": self.finished_utc.isoformat(),
            "duration_ms": self.duration_ms,
            "outputs": self.outputs,
            "warnings": self.warnings,
            "errors": self.errors,
            "skipped": self.skipped,
            "metrics": self.metrics
        }
