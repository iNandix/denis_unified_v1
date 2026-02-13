#!/usr/bin/env python3
"""Block reading of secret files per DENIS policy."""

import os
import re
import sys

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
]

def main():
    file_path = os.getenv('WINDSURF_FILE_PATH', '')
    if not file_path:
        return  # Allow if no file

    for pattern in SECRET_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            print(f"Reading secret file blocked: {file_path}")
            print("Secrets are ignored per .codeiumignore. Use explicit user request if needed.")
            sys.exit(2)  # Block the action

    print(f"SAFE file read allowed: {file_path}")

if __name__ == "__main__":
    main()
