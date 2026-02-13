#!/usr/bin/env python3
"""CLI tool to wait for job result."""

import argparse
import json
import sys
import time
from pathlib import Path

# Add REPO_REAL to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from workers.queue_backend import get_queue_backend

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--timeout-s", type=int, default=30)
    parser.add_argument("--worktree", type=Path, default=Path.cwd())
    args = parser.parse_args()

    backend = get_queue_backend(args.worktree)
    start = time.time()
    while time.time() - start < args.timeout_s:
        result = backend.get_result(args.job_id)
        if result:
            print(json.dumps(result.as_dict(), indent=2))
            return
        time.sleep(0.5)
    print(json.dumps({"status": "timeout"}))

if __name__ == "__main__":
    main()
