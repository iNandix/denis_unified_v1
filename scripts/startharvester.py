#!/usr/bin/env python3
import argparse
import hashlib
import logging
import os
import signal
import sys
import time
from datetime import date

_ROOT = "/media/jotah/SSD_denis/home_jotah"
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [harvester] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

_SESSION_PATH = "/tmp/denis/sessionid.txt"
_NODE_ID = os.environ.get("DENIS_NODE_ID", "nodo1")


def _compute_session_id(repo_id: str) -> str:
    raw = f"{date.today().isoformat()}|{_NODE_ID}|{repo_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def main() -> None:
    parser = argparse.ArgumentParser(description="Denis ContextHarvester daemon")
    parser.add_argument(
        "--workspace",
        default="/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
        help="Path to Denis workspace root",
    )
    args = parser.parse_args()
    workspace: str = os.path.abspath(args.workspace)

    from kernel.ghostide.repocontext import RepoContext
    from kernel.ghostide.contextharvester import ContextHarvester

    repo = RepoContext.from_workspace(workspace)
    repo_id = repo.repo_id
    repo_name = repo.repo_name
    branch = repo.branch

    session_id = _compute_session_id(repo_id)

    os.makedirs("/tmp/denis", exist_ok=True)
    with open(_SESSION_PATH, "w") as fh:
        fh.write(f"{session_id}|{repo_id}|{repo_name}|{branch}")
    logger.info("Session: %s | repo: %s | branch: %s", session_id, repo_name, branch)

    harvester = ContextHarvester(
        session_id=session_id,
        watch_paths=[workspace],
    )

    try:
        n_syms = harvester.harvest_last_commits(workspace, n=10)
        logger.info("Git history: %d symbols indexed from last 10 commits", n_syms)
    except Exception as exc:
        logger.warning("harvestLastCommits failed (skip): %s", exc)

    try:
        harvester.harvest_repo(workspace)
        logger.info("Initial repo harvest complete")
    except Exception as exc:
        logger.warning("harvestRepo failed (skip): %s", exc)

    harvester.start(blocking=False)
    logger.info("ContextHarvester active — watching %s", workspace)

    def _shutdown(signum, frame):
        logger.info("Shutting down harvester (signal %s)", signum)
        harvester.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
