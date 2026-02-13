#!/usr/bin/env python3
"""Block prompt injection attempts."""

import json
import re
import sys

# Dangerous prompt patterns to block
DANGEROUS_PROMPT_PATTERNS = [
    r'\bignora\s+reglas\b',
    r'\bbypass\s+seguridad\b',
    r'\bdesactiva\s+protecciones\b',
    r'\bignora\s+policies\b',
    r'\bsobrescribe\s+rules\b',
    r'\bmodo\s+inseguro\b',
]

def main():
    tool_info = json.load(sys.stdin)
    prompt = tool_info.get('prompt', '').lower()

    for pattern in DANGEROUS_PROMPT_PATTERNS:
        if re.search(pattern, prompt):
            print(f"Blocked dangerous prompt pattern: {pattern}")
            print("Prompt injection attempt detected.")
            sys.exit(2)  # Block

    print("Prompt safe.")

if __name__ == "__main__":
    main()
