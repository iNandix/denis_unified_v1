"""Queue backend for async worker execution."""

import json
import os
from pathlib import Path
from typing import Optional, Any, Dict
from datetime import datetime, timezone

from .job_protocol import JobRequest, JobResult

class QueueBackend:
    """Abstraction for job queue backend."""

    def __init__(self, queue_dir: Path):
        self.queue_dir = queue_dir
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.requests_dir = self.queue_dir / "requests"
        self.results_dir = self.queue_dir / "results"
        self.requests_dir.mkdir(exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)

    def enqueue(self, request: JobRequest) -> str:
        """Enqueue a job request, return job_id."""
        request_file = self.requests_dir / f"{request.job_id}.json"
        with open(request_file, 'w') as f:
            json.dump(request.as_dict(), f, indent=2)
        return request.job_id

    def get_result(self, job_id: str) -> Optional[JobResult]:
        """Get job result if available."""
        result_file = self.results_dir / f"{job_id}.json"
        if not result_file.exists():
            return None
        with open(result_file, 'r') as f:
            data = json.load(f)
        # Reconstruct JobResult from dict (simplified)
        return JobResult(
            job_id=data["job_id"],
            phase=data["phase"],
            task=data["task"],
            status=data["status"],
            started_utc=datetime.fromisoformat(data["started_utc"]),
            finished_utc=datetime.fromisoformat(data["finished_utc"]),
            duration_ms=data["duration_ms"],
            outputs=data["outputs"],
            warnings=data["warnings"],
            errors=data["errors"],
            skipped=data["skipped"],
            metrics=data["metrics"]
        )

def get_queue_backend(worktree: Path) -> QueueBackend:
    """Get queue backend, preferring local filesystem."""
    queue_dir = worktree / ".queue"
    return QueueBackend(queue_dir)
