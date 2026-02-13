"""Worker main for async job execution."""

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

from .job_protocol import JobRequest, JobResult
from .queue_backend import get_queue_backend

def execute_task(phase: str, task: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a task, return outputs."""
    if task == "trivial":
        return {"message": "Hello from worker"}
    else:
        raise ValueError(f"Unknown task {task}")

def run_worker(worktree: Path, poll_interval: int = 1):
    """Poll queue and execute jobs."""
    backend = get_queue_backend(worktree)
    while True:
        for request_file in backend.requests_dir.glob("*.json"):
            with open(request_file, 'r') as f:
                data = json.load(f)
            # Reconstruct JobRequest
            request = JobRequest(
                job_id=data["job_id"],
                phase=data["phase"],
                task=data["task"],
                args=data["args"],
                created_utc=datetime.fromisoformat(data["created_utc"])
            )
            started = datetime.now(timezone.utc)
            try:
                outputs = execute_task(request.phase, request.task, request.args)
                status = "ok"
                errors = []
            except Exception as e:
                outputs = {}
                status = "error_internal"
                errors = [str(e)]
            finished = datetime.now(timezone.utc)
            duration = int((finished - started).total_seconds() * 1000)
            result = JobResult(
                job_id=request.job_id,
                phase=request.phase,
                task=request.task,
                status=status,
                started_utc=started,
                finished_utc=finished,
                duration_ms=duration,
                outputs=outputs,
                warnings=[],
                errors=errors,
                skipped=False,
                metrics={}
            )
            result_file = backend.results_dir / f"{request.job_id}.json"
            with open(result_file, 'w') as f:
                json.dump(result.as_dict(), f, indent=2)
            request_file.unlink()  # Remove request after processing
        time.sleep(poll_interval)

if __name__ == "__main__":
    import sys
    worktree = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    run_worker(worktree)
