#!/usr/bin/env python3
"""Block reading of secret files per DENIS policy."""

import json
import os
import re
import sys
from datetime import datetime

# Secret file patterns to block
SECRET_PATTERNS = [
    r'\.env$',
    r'\.env\.',
    r'.*secret.*',
    r'.*key.*',
    r'.*token.*',
    r'id_rsa.*',
    r'\.ssh/',
    r'.*\.gguf$',
    r'.*\.bin$',
    r'.*\.pt$',
    r'.*\.pem$',
]

def main():
    tool_info = json.load(sys.stdin)
    file_path = tool_info.get('file_path', '')
    if not file_path:
        return  # Allow if no file

    for pattern in SECRET_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            print(f"Reading secret file blocked: {file_path}")
            print("Secrets are ignored per .codeiumignore. Use explicit user request if needed.")
            with open('.windsurf/logs/blocked_reads.log', 'a') as f:
                f.write(f"{datetime.now().isoformat()} BLOCKED: {file_path}\n")
            sys.exit(2)  # Block the action

    print(f"SAFE file read allowed: {file_path}")

if __name__ == "__main__":
    main()
