#!/usr/bin/env python3
"""Post-write code gates: run basic checks and suggest commands."""

import json
import os
import sys
import subprocess

def main():
    tool_info = json.load(sys.stdin)
    file_path = tool_info.get('file_path', '')
    if not file_path:
        return

    if file_path.endswith('.py'):
        # Try to compile Python file
        try:
            compile(open(file_path).read(), file_path, 'exec')
            print(f"Gates passed for {file_path}")
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            # Don't block, just log
    else:
        print(f"No gates for {file_path}")

    # Suggestions based on path
    if 'sprintorchestrator' in file_path or 'scripts/phase' in file_path:
        print("Suggested commands: python3 scripts/phase11_sprint_orchestrator_smoke.py --out-json phase11_sprint_orchestrator_smoke.json")
    elif 'contracts' in file_path:
        print("Suggested commands: make preflight && python3 scripts/phase11_sprint_orchestrator_smoke.py --out-json phase11_sprint_orchestrator_smoke.json")
    else:
        print(f"No suggestions for {file_path}")

if __name__ == "__main__":
    main()
