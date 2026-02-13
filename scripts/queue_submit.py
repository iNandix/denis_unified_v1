#!/usr/bin/env python3
"""CLI tool to submit job to queue."""

import argparse
import json
import sys
from pathlib import Path

# Add REPO_REAL to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from workers.job_protocol import JobRequest
from workers.queue_backend import get_queue_backend

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--args-json", required=True)
    parser.add_argument("--worktree", type=Path, default=Path.cwd())
    args = parser.parse_args()

    args_dict = json.loads(args.args_json)
    request = JobRequest.create(args.phase, args.task, args_dict)
    backend = get_queue_backend(args.worktree)
    job_id = backend.enqueue(request)
    print(job_id)

if __name__ == "__main__":
    main()
