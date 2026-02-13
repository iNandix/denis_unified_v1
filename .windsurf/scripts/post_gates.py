#!/usr/bin/env python3
"""Post-write code gates: run basic checks."""

import os
import sys
import subprocess

def main():
    file_path = os.getenv('WINDSURF_FILE_PATH', '')
    if not file_path:
        return

    if file_path.endswith('.py'):
        # Try to compile Python file
        try:
            compile(open(file_path).read(), file_path, 'exec')
            print(f"Gates passed for {file_path}")
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            # Don't block, just log
    else:
        print(f"No gates for {file_path}")

if __name__ == "__main__":
    main()
