#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-denis_unified_v1/denis_unified_v1}"
echo "== Denis Agent Preflight =="
echo "ROOT=$ROOT"
echo

echo "-- Kernel tree (top 200) --"
find "$ROOT/kernel" -type f -name "*.py" | sort | head -200 || true
echo

echo "-- Route keywords --"
rg -n "FAST_TALK|PROJECT/IDE|PROJECT_IDE|VERIFY|VERIFY_SAFE|TOOL" "$ROOT/kernel" "$ROOT/services" "$ROOT/api" || true
echo

echo "-- Schema validation signals --"
rg -n "jsonschema|validate\\(|context_pack_.*schema|additionalProperties\\s*:\\s*false" "$ROOT" || true
echo

echo "-- Decision trace signals --"
rg -n "DecisionTrace|decision_trace|trace_id|request_id|span_id" "$ROOT/kernel" "$ROOT/observability" "$ROOT/services" "$ROOT/api" || true
echo
