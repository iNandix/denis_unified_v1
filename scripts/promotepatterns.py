#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah/denis_unified_v1")

from kernel.ghostide.symbolgraph import SymbolGraph
from kernel.ghostide.redundancy_detector import RedundancyDetector


def main():
    dry_run = "--dry-run" in sys.argv

    sg = SymbolGraph()
    detector = RedundancyDetector("promoter", sg)

    print("=== Pattern Promotion Candidates ===")
    print("Looking for patterns with frequency >= 10\n")

    candidates = detector.suggest_new_implicit_tasks()

    if not candidates:
        print("No candidates found.")
        return

    for c in candidates:
        print(f"Pattern: {c['name']}")
        print(f"  Intent: {c['intent']}")
        print(f"  Frequency: {c['frequency']}")
        print(f"  Tasks: {c['tasks']}")
        print()

    if dry_run:
        print("[DRY RUN] No changes made.")
        return

    print("Promoting patterns to IMPLICITTASKS...")
    for c in candidates:
        response = input(f"Promote '{c['name']}' (freq={c['frequency']})? [y/N]: ")
        if response.lower() == "y":
            print(f"  -> Would add to IMPLICITTASKS (manual step required)")


if __name__ == "__main__":
    main()
