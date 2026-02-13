#!/usr/bin/env python3
"""Allowlist MCP tool usage per DENIS policy."""

import json
import os
import sys
from datetime import datetime

# Allowed MCP tools for DENIS workspace
ALLOWED_TOOLS = {
    "denis-files",
    "denis-git",
    "web-fetch",
    "agent-memory",
    "time",
    "denis-control-plane",
    "seq-thinking",  # optional
}

def main():
    tool_info = json.load(sys.stdin)
    tool_name = tool_info.get('tool_name', '')
    if not tool_name:
        return  # Allow if no tool

    if tool_name not in ALLOWED_TOOLS:
        print(f"MCP tool blocked: {tool_name}")
        print("Only allowed tools: " + ", ".join(ALLOWED_TOOLS))
        with open('.windsurf/logs/blocked_mcps.log', 'a') as f:
            f.write(f"{datetime.now().isoformat()} BLOCKED: {tool_name}\n")
        sys.exit(2)  # Block the action

    print(f"MCP tool allowed: {tool_name}")

if __name__ == "__main__":
    main()
