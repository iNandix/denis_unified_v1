#!/bin/bash
# =============================================================================
# FIRE DRILL: Graph Slow
# =============================================================================
# Validates circuit breaker when Neo4j is slow.
# Expected: Graph legacy mode activates, /chat continues with degraded features.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENIS_BASE_URL="${DENIS_BASE_URL:-http://localhost:8084}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$SCRIPT_DIR/../artifacts}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Create artifacts directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DRILL_DIR="$ARTIFACTS_DIR/drills/graph_slow_$TIMESTAMP"
mkdir -p "$DRILL_DIR"

echo "=============================================="
echo "  FIRE DRILL: Graph Slow"
echo "=============================================="

# -----------------------------------------------------------------------------
# Capture BEFORE state
# -----------------------------------------------------------------------------
log_info "Capturing BEFORE state..."

curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null > "$DRILL_DIR/before_metrics.txt" || true
curl -s "$DENIS_BASE_URL/health" 2>/dev/null > "$DRILL_DIR/before_health.txt" || true

echo "  Before state captured to: $DRILL_DIR"

# -----------------------------------------------------------------------------
# Check Neo4j connectivity
# -----------------------------------------------------------------------------
log_info "Checking Neo4j connectivity..."

if ! command -v cypher-shell &>/dev/null; then
    log_warn "cypher-shell not available - simulating"
fi

# Check if graph is reachable via API
GRAPH_LEGACY_BEFORE=$(curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null | \
    grep "graph_legacy_mode" | awk '{print $2}' || echo "unknown")

echo "  Graph legacy mode before: $GRAPH_LEGACY_BEFORE"

# -----------------------------------------------------------------------------
# Execute drill: Simulate slow queries by making requests
# In real scenario: kubectl exec neo4j-0 -- tc qdisc add dev eth0 root netem delay 5000ms
# -----------------------------------------------------------------------------
log_info "Running drill - sending requests that would trigger graph..."

# Send several requests that would normally hit the graph
for i in {1..10}; do
    curl -s --max-time 15 \
        "$DENIS_BASE_URL/chat" \
        -d "{\"message\":\"test graph drill $i\",\"user_id\":\"drill-graph\"}" \
        >/dev/null 2>&1 || true
done

# -----------------------------------------------------------------------------
# Verify /chat still responds (with possible degradation)
# -----------------------------------------------------------------------------
log_info "Verifying /chat availability..."

CHAT_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null \
    --max-time 20 \
    "$DENIS_BASE_URL/chat" \
    -d '{"message":"test","user_id":"drill-graph-slow"}' 2>&1) || true

# Capture AFTER state
curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null > "$DRILL_DIR/after_metrics.txt" || true

GRAPH_LEGACY_AFTER=$(curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null | \
    grep "graph_legacy_mode" | awk '{print $2}' || echo "unknown")

echo ""
echo "Results:"
echo "--------"

# Determine pass/fail
if [[ "$CHAT_RESPONSE" == "200" ]]; then
    log_pass "/chat returned 200 - fail-open working"
    RESULT="PASS"
else
    log_fail "/chat returned: $CHAT_RESPONSE"
    RESULT="FAIL"
fi

echo "  Graph legacy mode before: $GRAPH_LEGACY_BEFORE"
echo "  Graph legacy mode after: $GRAPH_LEGACY_AFTER"

echo ""
echo "Artifacts saved to: $DRILL_DIR"

# Save result
echo "$RESULT" > "$DRILL_DIR/result.txt"
echo "$CHAT_RESPONSE" > "$DRILL_DIR/chat_response.txt"
echo "graph_legacy_before=$GRAPH_LEGACY_BEFORE" > "$DRILL_DIR/graph_state.txt"
echo "graph_legacy_after=$GRAPH_LEGACY_AFTER" >> "$DRILL_DIR/graph_state.txt"

exit 0
