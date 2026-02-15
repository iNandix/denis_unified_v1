#!/usr/bin/env python3
"""Protect critical paths from unauthorized changes."""

import json
import re
import sys

PROTECTED_PATHS = [
    r'^contracts/',
    r'^tools/ide_graph/',
    r'^\.windsurf/',
]

def main():
    tool_info = json.load(sys.stdin)
    file_path = tool_info.get('file_path', '')
    prompt = tool_info.get('prompt', '')

    if not file_path:
        return

    protected = any(re.match(pattern, file_path) for pattern in PROTECTED_PATHS)
    if protected and 'APPROVED:' not in prompt:
        print(f"Blocked write to protected path: {file_path}")
        print("Include 'APPROVED:' in your prompt to override.")
        sys.exit(2)  # Block

    print(f"Allowed write to {file_path}")

if __name__ == "__main__":
    main()
