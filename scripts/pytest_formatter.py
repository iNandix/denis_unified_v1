#!/usr/bin/env python3
"""Pytest formatter - shows progress as X/total instead of percentage."""

import re
import subprocess
import sys


def run_pytest():
    """Run pytest and format output cleanly."""
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/test_control_plane.py", "-v", "--tb=short"],
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr

    # Extract test results
    passed_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    total_match = re.search(r"(\d+) passed", output)

    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    total = passed + failed

    # Show clean output
    for line in output.split("\n"):
        if "PASSED" in line or "FAILED" in line or "::test_" in line:
            print(line)

    # Summary
    print("\n" + "=" * 50)
    if failed == 0:
        pct = int((passed / total) * 100) if total > 0 else 0
        print(f"Progreso: {passed}/{total}")
        print(f"Resultado: ✅ {pct}% OK ({passed}/{total} passed)")
    else:
        pct = int((passed / total) * 100) if total > 0 else 0
        print(f"Progreso: {passed}/{total}")
        print(f"Resultado: ❌ {pct}% ({passed}/{total} passed, {failed} failed)")
    print("=" * 50)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_pytest())
