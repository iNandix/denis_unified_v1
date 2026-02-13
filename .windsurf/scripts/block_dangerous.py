#!/usr/bin/env python3
"""Block dangerous commands per DENIS policy."""

import json
import os
import re
import sys
from datetime import datetime

# Dangerous patterns that require confirmation (DESTRUCTIVE)
DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\b',
    r'\bdd\b',
    r'\bmkfs\b',
    r'\bparted\b',
    r'\bwipefs\b',
    r'\bchmod\s+.*\b',
    r'\bchown\s+.*\b',
    r'\bkill\s+-9\b',
    r'\bgit\s+reset\s+--hard\b',
    r'\bgit\s+clean\s+-fdx\b',
    r'\bgit\s+push\s+--force\b',
    r'\btruncate\b',
    r'\brm\s+.*\.env\b',
    r'\brm\s+.*secret\b',
    r'\brm\s+.*key\b',
    r'\brm\s+.*token\b',
]

def main():
    tool_info = json.load(sys.stdin)
    command = tool_info.get('command_line', '')
    if not command:
        return  # Allow if no command

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"DESTRUCTIVE command blocked: {command}")
            print("Requires explicit confirmation from user. Retry after confirmation.")
            with open('.windsurf/logs/blocked_commands.log', 'a') as f:
                f.write(f"{datetime.now().isoformat()} BLOCKED: {command}\n")
            sys.exit(2)  # Block the action

    print(f"SAFE command allowed: {command}")

if __name__ == "__main__":
    main()
