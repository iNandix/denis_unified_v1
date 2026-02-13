#!/usr/bin/env python3
"""Post-run command logging."""

import json
import sys
from datetime import datetime

def main():
    tool_info = json.load(sys.stdin)
    command = tool_info.get('command_line', '')
    exit_status = tool_info.get('exit_status', 0)

    with open('.windsurf/logs/commands.log', 'a') as f:
        timestamp = datetime.now().isoformat()
        f.write(f"[{timestamp}] {command} -> {exit_status}\n")

if __name__ == "__main__":
    main()
