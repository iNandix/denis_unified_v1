#!/usr/bin/env python3
"""Log read access for auditing."""

import json
import sys
from datetime import datetime

def main():
    tool_info = json.load(sys.stdin)
    file_path = tool_info.get('file_path', '')
    if not file_path:
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "read_code",
        "file_path": file_path,
        "agent_action_name": tool_info.get('agent_action_name', ''),
        "trajectory_id": tool_info.get('trajectory_id', ''),
        "execution_id": tool_info.get('execution_id', '')
    }

    with open('.windsurf/logs/access.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')

if __name__ == "__main__":
    main()
