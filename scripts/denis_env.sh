#!/bin/bash
set -euo pipefail

# Single source of truth for Ops scripts.
# Usage:
#   source scripts/denis_env.sh
#   echo "$(denis_base_url)"
#
# Env:
#   DENIS_BASE_URL (default: http://127.0.0.1:9999)

denis_base_url() {
  echo "${DENIS_BASE_URL:-http://127.0.0.1:9999}"
}

denis_url() {
  local path="${1:-/}"
  local base
  base="$(denis_base_url)"
  echo "${base%/}${path}"
}

denis_probe_http_code() {
  # Prints HTTP code, or 000 if connection failed.
  local path="${1:-/health}"
  local url
  url="$(denis_url "$path")"
  local code=""
  if code="$(curl -sS -o /dev/null --connect-timeout 1 -m 2 -w "%{http_code}" "$url" 2>/dev/null)"; then
    echo "$code"
  else
    echo "000"
  fi
}

denis_is_reachable() {
  # Uses /health as the reachability probe.
  local code
  code="$(denis_probe_http_code "/health")"
  [[ "$code" != "000" ]]
}

denis_print_unreachable() {
  echo "UNREACHABLE: cannot connect to $(denis_url "/health")"
  echo "Set DENIS_BASE_URL=http://HOST:PORT (current: $(denis_base_url))"
}
