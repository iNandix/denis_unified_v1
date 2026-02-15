#!/usr/bin/env python3
"""Log command results for auditing."""

import json
import sys
from datetime import datetime

def main():
    tool_info = json.load(sys.stdin)
    command_line = tool_info.get('command_line', '')
    exit_status = tool_info.get('exit_status', 0)
    duration_ms = tool_info.get('duration_ms', None)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "run_command",
        "command_line": command_line,
        "exit_status": exit_status,
        "duration_ms": duration_ms,
        "agent_action_name": tool_info.get('agent_action_name', ''),
        "trajectory_id": tool_info.get('trajectory_id', ''),
        "execution_id": tool_info.get('execution_id', '')
    }

    with open('.windsurf/logs/commands.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')

if __name__ == "__main__":
    main()
