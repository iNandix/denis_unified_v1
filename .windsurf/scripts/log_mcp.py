#!/usr/bin/env python3
"""Log MCP tool usage for auditing."""

import json
import sys
from datetime import datetime

def main():
    tool_info = json.load(sys.stdin)
    tool_name = tool_info.get('tool_name', '')
    result = tool_info.get('result', {})

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "mcp_tool_use",
        "tool_name": tool_name,
        "result_summary": str(result)[:200],  # Truncate
        "agent_action_name": tool_info.get('agent_action_name', ''),
        "trajectory_id": tool_info.get('trajectory_id', ''),
        "execution_id": tool_info.get('execution_id', '')
    }

    with open('.windsurf/logs/mcp.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')

if __name__ == "__main__":
    main()
