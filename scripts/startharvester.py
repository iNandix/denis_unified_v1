#!/usr/bin/env python3
import os
import sys
import hashlib
import subprocess
from datetime import datetime

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah/denis_unified_v1")

from kernel.ghostide.contextharvester import ContextHarvester


def get_repo_id(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=repo_path, capture_output=True, text=True
        )
        if result.returncode == 0:
            remote_url = result.stdout.strip()
            return hashlib.sha256(remote_url.encode()).hexdigest()[:12]
    except:
        pass
    return hashlib.sha256(repo_path.encode()).hexdigest()[:12]


def get_repo_name(repo_path: str) -> str:
    return os.path.basename(os.path.abspath(repo_path))


def main():
    repo_path = os.getcwd()
    node_id = os.environ.get("NODE_ID", "nodo1")
    repo_id = get_repo_id(repo_path)
    repo_name = get_repo_name(repo_path)
    date_str = datetime.now().isoformat()

    session_id = hashlib.sha256((date_str + node_id + repo_id).encode()).hexdigest()[:12]

    session_info = f"{session_id}|{repo_id}|{repo_name}"
    os.makedirs("/tmp/denis", exist_ok=True)
    with open("/tmp/denis/sessionid.txt", "w") as f:
        f.write(session_info)

    print(f"Starting Harvester for {repo_name}")
    print(f"  session_id: {session_id}")
    print(f"  repo_id: {repo_id}")
    print(f"  repo_name: {repo_name}")

    harvester = ContextHarvester(session_id=session_id, watch_paths=["."])

    print("\nHarvesting last commits...")
    result = harvester.harvest_last_commits(repo_path, n=5)
    print(f"  Indexed {result['symbols_indexed']} symbols from {len(result['commits'])} commits")

    print("\nStarting watch loop...")
    print("(Ctrl+C to stop)")

    try:
        import time

        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping harvester...")
        harvester.close()


if __name__ == "__main__":
    main()
