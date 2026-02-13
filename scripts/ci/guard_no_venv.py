#!/usr/bin/env python3
"""
Git pre-commit hook to prevent committing venv/virtual environment files.

This script scans the staged files (git diff --cached --name-only) and fails
if any prohibited paths are found, preventing accidental commits of:
- .venv_preflight/
- .venvpreflight/
- .venv*/
- venv/
- env/
- site-packages/
- __pycache__/
- *.pyc

Usage:
    python scripts/ci/guard_no_venv.py

Exit codes:
    0 - No prohibited files found
    1 - Prohibited files found, commit blocked
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Set


# Prohibited path patterns (gitignoresque wildcards)
PROHIBITED_PATTERNS = [
    # Virtual environments
    ".venv_preflight/",
    ".venvpreflight/",
    ".venv*/",
    "venv/",
    "env/",
    # Python cache
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    # Package directories
    "site-packages/",
    "dist-packages/",
    # IDE
    ".vscode/",
    ".idea/",
    # OS
    ".DS_Store",
    "Thumbs.db",
    # Logs
    "*.log",
    # Temporary files
    "*.tmp",
    "*.temp",
    # Secrets (basic patterns)
    ".env",
    ".env.*",
    "*secret*",
    "*password*",
    "*key*",
]


def get_staged_files() -> List[str]:
    """Get list of staged files using git diff --cached --name-only."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        print(f"Error running git diff: {e}")
        return []


def is_prohibited_path(file_path: str) -> bool:
    """Check if a file path matches any prohibited pattern."""
    from fnmatch import fnmatch

    # Check exact matches and patterns
    for pattern in PROHIBITED_PATTERNS:
        if fnmatch(file_path, pattern):
            return True

        # Also check if any parent directory matches
        path_parts = Path(file_path).parts
        for i in range(len(path_parts)):
            parent_path = '/'.join(path_parts[:i+1])
            if parent_path and fnmatch(parent_path + '/', pattern):
                return True

    return False


def main() -> int:
    """Main function."""
    print("🔍 Checking for prohibited files in staged changes...")

    staged_files = get_staged_files()
    if not staged_files:
        print("✅ No staged files to check")
        return 0

    prohibited_files = []
    for file_path in staged_files:
        if file_path and is_prohibited_path(file_path):
            prohibited_files.append(file_path)

    if prohibited_files:
        print("❌ BLOCKED: Found prohibited files in staged changes!")
        print("\nProhibited files:")
        for file_path in prohibited_files:
            print(f"  🚫 {file_path}")
        print("\nThese files/directories should NOT be committed:")
        print("  - Virtual environments (.venv*, venv/, env/)")
        print("  - Python cache (__pycache__/, *.pyc)")
        print("  - IDE files (.vscode/, .idea/)")
        print("  - Secrets (.env*, *secret*, *password*)")
        print("  - OS files (.DS_Store, Thumbs.db)")
        print("  - Logs (*.log) and temp files (*.tmp)")
        print("\nTo fix:")
        print("  1. Unstage prohibited files: git reset HEAD <file>")
        print("  2. Remove from git if tracked: git rm --cached <file>")
        print("  3. Ensure .gitignore includes these patterns")
        print("  4. Try commit again")
        return 1
    else:
        print("✅ No prohibited files found in staged changes")
        return 0


if __name__ == "__main__":
    sys.exit(main())
