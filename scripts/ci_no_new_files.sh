#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-origin/main}"
NEW_FILES=$(git diff --name-status "$BASE"...HEAD | awk '$1=="A"{print $2}')

ALLOW_REGEX='^(denis_unified_v1/denis_unified_v1/tests/|denis_unified_v1/denis_unified_v1/schemas/|denis_unified_v1/denis_unified_v1/observability/|scripts/)'

if echo "$NEW_FILES" | grep -E '\.py$' >/dev/null 2>&1; then
  BLOCKED=$(echo "$NEW_FILES" | grep -E '\.py$' | grep -Ev "$ALLOW_REGEX" || true)
  if [ -n "${BLOCKED:-}" ]; then
    echo "ERROR: New .py files detected outside allowlist:"
    echo "$BLOCKED"
    echo
    echo "Create a tracked issue with exact paths or update allowlist intentionally."
    exit 1
  fi
fi

echo "OK: no blocked new files."
