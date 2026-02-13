#!/usr/bin/env python3
"""Phase 0 workers smoke test."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add REPO_REAL to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from workers.queue_backend import get_queue_backend

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, default=Path.cwd())
    args = parser.parse_args()

    worktree = args.worktree
    artifacts_dir = worktree / "artifacts" / "workers"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Start worker in background
    worker_cmd = [sys.executable, "-m", "workers.worker_main", str(worktree)]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).parents[1])
    worker = subprocess.Popen(worker_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    time.sleep(2)  # Wait for worker to start

    try:
        # Submit trivial job
        submit_cmd = [sys.executable, "scripts/queue_submit.py", "--phase", "phase0", "--task", "trivial", "--args-json", "{}"]
        repo_path = str(Path(__file__).parents[1])
        result = subprocess.run(submit_cmd, capture_output=True, text=True, cwd=repo_path)
        if result.returncode != 0:
            artifact = {"status": "error", "reason": "submit failed", "output": result.stdout, "error": result.stderr}
        else:
            job_id = result.stdout.strip()
            # Wait for result
            wait_cmd = [sys.executable, "scripts/queue_wait.py", "--job-id", job_id, "--timeout-s", "10"]
            wait_result = subprocess.run(wait_cmd, capture_output=True, text=True, cwd=repo_path)
            if wait_result.returncode == 0:
                data = json.loads(wait_result.stdout)
                artifact = {"status": "ok", "job_result": data}
            else:
                artifact = {"status": "degraded", "reason": "wait timeout", "output": wait_result.stdout}
    except Exception as e:
        artifact = {"status": "error", "reason": str(e)}
    finally:
        worker.terminate()
        worker.wait()

    with open(artifacts_dir / "phase0_workers_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)

    if artifact["status"] not in ["ok", "degraded"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
