#!/bin/bash
# =============================================================================
# GO / NO-GO GATE AUTOMATION
# =============================================================================
# Runs preflight + subset of fire drills + evaluates thresholds.
# Usage: ./go_no_go.sh [--json] [BASE_URL]
# Exit codes: 0 = GO, 2 = NO-GO, 3 = GO_WITH_RISK
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENIS_BASE_URL="${1:-${DENIS_BASE_URL:-http://localhost:8084}}"
JSON_OUTPUT="${JSON_OUTPUT:-false}"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--json] [BASE_URL]"
            echo ""
            echo "Exit codes:"
            echo "  0 = GO"
            echo "  2 = NO-GO"
            echo "  3 = GO_WITH_RISK"
            exit 0
            ;;
        http*)
            DENIS_BASE_URL="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Results storage
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
RISKS=()

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=============================================="
echo "  GO / NO-GO GATE"
echo "=============================================="
echo ""
echo "Base URL: $DENIS_BASE_URL"
echo ""

# =============================================================================
# Step 1: Preflight Check
# =============================================================================
log_info "Step 1: Running preflight..."

if ./scripts/production_preflight.sh "$DENIS_BASE_URL"; then
    log_pass "Preflight: PASS"
    ((PASS_COUNT++))
else
    PREFLIGHT_EXIT=$?
    if [ $PREFLIGHT_EXIT -eq 1 ]; then
        log_fail "Preflight: FAIL"
        ((FAIL_COUNT++))
    else
        log_warn "Preflight: WARN"
        ((WARN_COUNT++))
    fi
fi

echo ""

# =============================================================================
# Step 2: Check Critical Endpoints
# =============================================================================
log_info "Step 2: Checking critical endpoints..."

# /chat must be available
CHAT_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null \
    --max-time 10 \
    "$DENIS_BASE_URL/chat" \
    -d '{"message":"test","user_id":"go-no-go"}' 2>&1) || true

if [ "$CHAT_RESPONSE" = "200" ]; then
    log_pass "/chat: 200 OK"
    ((PASS_COUNT++))
else
    log_fail "/chat: $CHAT_RESPONSE"
    RISKS+=("Critical endpoint /chat failed")
    ((FAIL_COUNT++))
fi

# Check latency
CHAT_LATENCY=$(curl -s -w "%{time_total}" -o /dev/null \
    --max-time 10 \
    "$DENIS_BASE_URL/chat" \
    -d '{"message":"latency test","user_id":"go-no-go-latency"}' 2>&1) || echo "999"

LATENCY_MS=$(echo "$CHAT_LATENCY * 1000" | bc | cut -d. -f1)
echo "  /chat latency: ${LATENCY_MS}ms"

# Check if latency is acceptable (< 10s for now, as per SLO)
if [ "$LATENCY_MS" -lt 10000 ]; then
    log_pass "Latency acceptable: ${LATENCY_MS}ms"
    ((PASS_COUNT++))
else
    log_fail "Latency too high: ${LATENCY_MS}ms"
    RISKS+=("Latency exceeds 10s threshold")
    ((FAIL_COUNT++))
fi

echo ""

# =============================================================================
# Step 3: Check Metrics Availability
# =============================================================================
log_info "Step 3: Checking metrics..."

METRICS_AVAILABLE=false
if curl -s --max-time 5 "$DENIS_BASE_URL/metrics" | grep -q "chat_requests"; then
    METRICS_AVAILABLE=true
    log_pass "Metrics: Available"
    ((PASS_COUNT++))
else
    log_warn "Metrics: Not available"
    RISKS+=("Metrics endpoint not available - cannot verify SLOs")
    ((WARN_COUNT++))
fi

echo ""

# =============================================================================
# Step 4: Check Async Queue (if metrics available)
# =============================================================================
log_info "Step 4: Checking async queues..."

if [ "$METRICS_AVAILABLE" = "true" ]; then
    # Try to get queue depth
    QUEUE_DEPTH=$(curl -s --max-time 5 "$DENIS_BASE_URL/metrics" | \
        grep "celery_queue" | head -1 | awk '{print $2}' || echo "0")
    
    echo "  Queue depth: $QUEUE_DEPTH"
    
    # Check if queue is manageable (< 500)
    if [ "$QUEUE_DEPTH" -lt 500 ] 2>/dev/null; then
        log_pass "Queue depth acceptable"
        ((PASS_COUNT++))
    else
        log_warn "Queue depth high: $QUEUE_DEPTH"
        RISKS+=("Queue depth exceeds 500")
        ((WARN_COUNT++))
    fi
else
    log_warn "Cannot check queue - metrics unavailable"
    RISKS+=("Cannot verify queue health - metrics unavailable")
    ((WARN_COUNT++))
fi

echo ""

# =============================================================================
# Step 5: Check Graph Status (if available)
# =============================================================================
log_info "Step 5: Checking graph..."

GRAPH_LEGACY=$(curl -s --max-time 5 "$DENIS_BASE_URL/metrics" | \
    grep "graph_legacy_mode" | awk '{print $2}' || echo "unknown")

echo "  Graph legacy mode: $GRAPH_LEGACY"

if [ "$GRAPH_LEGACY" = "0" ] || [ "$GRAPH_LEGACY" = "unknown" ]; then
    if [ "$GRAPH_LEGACY" = "unknown" ]; then
        log_warn "Graph status unknown - cannot verify"
        RISKS+=("Graph status unavailable - cannot verify integrity")
        ((WARN_COUNT++))
    else
        log_pass "Graph: Healthy"
        ((PASS_COUNT++))
    fi
else
    log_warn "Graph in legacy mode - degraded"
    RISKS+=("Graph in legacy mode - reduced functionality")
    ((WARN_COUNT++))
fi

echo ""

# =============================================================================
# Determine GO / NO-GO
# =============================================================================
echo "=============================================="
echo "  RESULTS"
echo "=============================================="
echo ""
echo "Pass: $PASS_COUNT"
echo "Fail: $FAIL_COUNT"
echo "Warn: $WARN_COUNT"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${RED}OVERALL: NO-GO${NC}"
    echo ""
    echo "Reasons:"
    for risk in "${RISKS[@]}"; do
        echo "  - $risk"
    done
    
    if [ "$JSON_OUTPUT" = "true" ]; then
        cat << EOF
{
  "result": "NO-GO",
  "exit_code": 2,
  "pass": $PASS_COUNT,
  "fail": $FAIL_COUNT,
  "warn": $WARN_COUNT,
  "risks": $(printf '%s\n' "${RISKS[@]}" | jq -R . | jq -s .)
}
EOF
    fi
    
    exit 2
elif [ $WARN_COUNT -gt 0 ]; then
    echo -e "${YELLOW}OVERALL: GO WITH RISK${NC}"
    echo ""
    echo "Risks:"
    for risk in "${RISKS[@]}"; do
        echo "  - $risk"
    done
    
    if [ "$JSON_OUTPUT" = "true" ]; then
        cat << EOF
{
  "result": "GO_WITH_RISK",
  "exit_code": 3,
  "pass": $PASS_COUNT,
  "fail": $FAIL_COUNT,
  "warn": $WARN_COUNT,
  "risks": $(printf '%s\n' "${RISKS[@]}" | jq -R . | jq -s .)
}
EOF
    fi
    
    exit 3
else
    echo -e "${GREEN}OVERALL: GO${NC}"
    echo "All checks passed"
    
    if [ "$JSON_OUTPUT" = "true" ]; then
        cat << EOF
{
  "result": "GO",
  "exit_code": 0,
  "pass": $PASS_COUNT,
  "fail": $FAIL_COUNT,
  "warn": $WARN_COUNT,
  "risks": []
}
EOF
    fi
    
    exit 0
fi
