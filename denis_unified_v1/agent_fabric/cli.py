#!/usr/bin/env python3
"""Agent Fabric CLI — Run agent tasks with goal input."""

import sys
import os
import json

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from denis_unified_v1.agent_fabric.manager import AgentFabricManager, GoalInput


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m denis_unified_v1.agent_fabric.cli <goal_text>")
        print("Or: denis_agent_fabric <goal_text>")
        sys.exit(1)

    goal_text = " ".join(sys.argv[1:])
    repo_root = os.getcwd()

    goal = GoalInput(goal_text=goal_text, repo_root=repo_root, profile="auto")

    manager = AgentFabricManager(repo_root)

    print(f"Executing goal: {goal_text}")
    print("-" * 40)

    report = manager.run(goal)

    print(f"\nTrace ID: {report.trace_id}")
    print(f"Profile: {report.selected_profile}")
    print(f"Tasks: {len(report.tasks)}")
    print(f"Results: {len(report.results)}")

    for result in report.results:
        status = "✓" if result.ok else "✗"
        print(f"  {status} {result.task_id}: {result.summary[:60]}")

    print(f"\nReport: {report.artifacts[0]}")


if __name__ == "__main__":
    main()
