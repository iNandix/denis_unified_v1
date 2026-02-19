#!/usr/bin/env python3
"""Denis Load CP — CLI to load ContextPack into queue."""

import os
import subprocess
import sys
from pathlib import Path

# Add denis_unified_v1 to path so control_plane can be imported
# Works whether called from CLI or directly
script_dir = Path(__file__).resolve().parent
denis_root = script_dir.parent  # denis_unified_v1
sys.path.insert(0, str(denis_root))

from control_plane.models import ContextPack
from control_plane.cp_queue import CPQueue


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Denis Load CP — CLI to load ContextPack into queue"
    )
    parser.add_argument("path", nargs="?", help="Path to ContextPack JSON file")
    parser.add_argument("--test", action="store_true", help="Test mode - load sample CP")
    args = parser.parse_args()

    if args.test:
        # Test mode - create sample CP
        from datetime import datetime, timedelta

        cp = ContextPack(
            cp_id="test_cp_001",
            mission="Test ContextPack",
            model="gpt-4o",
            repo_id="test/repo",
            repo_name="test-repo",
            branch="main",
        )
        cp.source = "test"
        queue = CPQueue()
        queue.push(cp)
        print(f"✅ Test CP loaded: {cp.cp_id}")
        return

    path = args.path
    if not path:
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--file-filter=*.json", "--filename=/tmp/"],
                capture_output=True,
                text=True,
            )
            path = result.stdout.strip()
            if not path:
                print("No file selected")
                sys.exit(1)
        except FileNotFoundError:
            print("zenity not found and no file path provided")
            sys.exit(1)

    if not os.path.exists(path):
        print(f"Error: File not found: {path}")
        sys.exit(1)

    try:
        cp = ContextPack.from_json(path)
    except Exception as e:
        print(f"Error loading ContextPack: {e}")
        sys.exit(1)

    cp.source = "manual_file"

    queue = CPQueue()
    queue.push(cp)

    notify_path = "/tmp/denis_cp_manual_loaded.json"
    cp.to_json(notify_path)

    try:
        subprocess.run(
            [
                "notify-send",
                "Denis · CP Cargado",
                f"{cp.repo_name} · {cp.mission[:60]}",
                "--expire-time=5000",
            ],
            capture_output=True,
        )
    except Exception:
        pass

    print(f"✅ CP {cp.cp_id} cargado — {cp.repo_name} · {cp.branch}")


if __name__ == "__main__":
    main()
