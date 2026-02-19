#!/usr/bin/env python3
"""Start ContextHarvester as a daemon."""

import argparse
import os
import signal
import sys
import time

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from control_plane.repo_context import RepoContext, write_session_id

from denis_unified_v1.kernel.ghost_ide.context_harvester import ContextHarvester
from denis_unified_v1.kernel.ghost_ide.symbol_graph import SymbolGraph

parser = argparse.ArgumentParser(description="Start ContextHarvester daemon")
parser.add_argument("--workspace", default="/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
parser.add_argument("--node", default="nodo1")
args = parser.parse_args()

repo = RepoContext(args.workspace)
sid = write_session_id(args.node)

try:
    sg = SymbolGraph()
    sg.upsert_repo(repo.repo_id, repo.repo_name, getattr(repo, "remote_url", ""), repo.branch)
    sg.ensure_session(sid, args.node)
    print(f"Neo4j Repo+Session OK | repoid={repo.repo_id}")
except Exception as e:
    print(f"WARNING: Neo4j unavailable: {e} — continuing")

harvester = ContextHarvester(session_id=sid, watch_paths=[args.workspace], auto_start=False)

try:
    n = harvester.harvest_repo(args.workspace)
    print(f"Initial harvest: {n} symbols indexed")
except Exception as e:
    print(f"WARNING: Initial harvest failed: {e} — continuing")

harvester.start(blocking=False)
print(f"ContextHarvester ACTIVE | session={sid} | node={args.node} | watching={args.workspace}")


def shutdown(*_):
    harvester.stop()
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)

while True:
    time.sleep(30)
