#!/usr/bin/env python3
"""Allowlist MCP tool usage per DENIS policy."""

import os
import sys

# Allowed MCP tools for DENIS workspace
ALLOWED_TOOLS = {
    "denis-files",
    "denis-git",
    "web-fetch",
    "agent-memory",
    "time",
    "denis-control-plane",
    # seq-thinking deactivated by default
}

def main():
    tool_name = os.getenv('WINDSURF_MCP_TOOL_NAME', '')
    if not tool_name:
        return  # Allow if no tool

    if tool_name not in ALLOWED_TOOLS:
        print(f"MCP tool blocked: {tool_name}")
        print("Only allowed tools: " + ", ".join(ALLOWED_TOOLS))
        sys.exit(2)  # Block the action

    print(f"MCP tool allowed: {tool_name}")

if __name__ == "__main__":
    main()
