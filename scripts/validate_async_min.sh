#!/bin/bash
set -euo pipefail

# Validate async_min observability endpoints + chat (when reachable).
#
# Behavior:
# - If server is unreachable: print UNREACHABLE and exit 0 (SKIP).
# - If reachable:
#   - /health and /telemetry are expected 200 with stable keys.
#   - /v1/chat/completions is "critical" and must succeed (otherwise exit 1).

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=denis_env.sh
source "$HERE/denis_env.sh"

BASE_URL="$(denis_base_url)"

echo "=== validate_async_min ==="
echo "DENIS_BASE_URL=$BASE_URL"
echo

if ! denis_is_reachable; then
  denis_print_unreachable
  echo "CHAT: SKIP (UNREACHABLE)"
  exit 0
fi

echo "1) GET /health (non-critical)"
health="$(curl -sS -m 2 --connect-timeout 1 -w "\n%{http_code}" "$(denis_url "/health")")"
health_code="$(echo "$health" | tail -n1)"
health_body="$(echo "$health" | sed '$d')"
if [[ "$health_code" != "200" ]]; then
  echo "FAIL /health http_code=$health_code"
  echo "$health_body"
  exit 1
fi
if ! echo "$health_body" | grep -q "\"status\"" || ! echo "$health_body" | grep -q "\"timestamp\""; then
  echo "FAIL /health missing required keys"
  echo "$health_body"
  exit 1
fi
echo "OK /health"
echo

echo "2) GET /telemetry (non-critical)"
tele="$(curl -sS -m 2 --connect-timeout 1 -w "\n%{http_code}" "$(denis_url "/telemetry")")"
tele_code="$(echo "$tele" | tail -n1)"
tele_body="$(echo "$tele" | sed '$d')"
if [[ "$tele_code" != "200" ]]; then
  echo "FAIL /telemetry http_code=$tele_code"
  echo "$tele_body"
  exit 1
fi
if ! echo "$tele_body" | grep -q "\"async\"" || ! echo "$tele_body" | grep -q "\"requests\""; then
  echo "FAIL /telemetry missing required keys"
  echo "$tele_body"
  exit 1
fi
echo "OK /telemetry"
if command -v jq >/dev/null 2>&1; then
  # Best-effort visibility; don't fail validation if parsing fails.
  echo "telemetry.graph.summary:"
  echo "$tele_body" | jq -c '.graph.summary? // empty' 2>/dev/null || true
fi
echo

echo "3) POST /v1/chat/completions (critical when reachable)"
chat_payload='{"model":"denis-local","messages":[{"role":"user","content":"ping"}],"max_tokens":16,"temperature":0}'
chat="$(curl -sS -m 10 --connect-timeout 2 -H "Content-Type: application/json" -d "$chat_payload" -w "\n%{http_code}" "$(denis_url "/v1/chat/completions")" || true)"
chat_code="$(echo "$chat" | tail -n1)"
chat_body="$(echo "$chat" | sed '$d')"
if [[ "$chat_code" != "200" ]]; then
  echo "FAIL /v1/chat/completions http_code=$chat_code"
  echo "$chat_body"
  exit 1
fi
if ! echo "$chat_body" | grep -q "\"choices\""; then
  echo "FAIL /v1/chat/completions missing choices"
  echo "$chat_body"
  exit 1
fi
echo "OK /v1/chat/completions"
echo

echo "=== PASS ==="
