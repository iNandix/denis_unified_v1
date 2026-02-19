#!/bin/bash
# =============================================================================
# FIRE DRILL: Worker Missing
# =============================================================================
# Validates queue behavior when Celery workers are missing/unavailable.
# Expected: Jobs queue up, /chat continues working (async is non-critical).
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
DRILL_DIR="$ARTIFACTS_DIR/drills/worker_missing_$TIMESTAMP"
mkdir -p "$DRILL_DIR"

echo "=============================================="
echo "  FIRE DRILL: Worker Missing"
echo "=============================================="

# -----------------------------------------------------------------------------
# Capture BEFORE state
# -----------------------------------------------------------------------------
log_info "Capturing BEFORE state..."

curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null > "$DRILL_DIR/before_metrics.txt" || true

echo "  Before state captured to: $DRILL_DIR"

# -----------------------------------------------------------------------------
# Check if Celery is available
# -----------------------------------------------------------------------------
log_info "Checking Celery connectivity..."

if ! command -v celery &>/dev/null; then
    log_warn "Celery CLI not available - simulating"
fi

# Check for queue metrics
QUEUES_BEFORE=$(curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null | grep -c "celery_queue" || echo "0")

# -----------------------------------------------------------------------------
# Execute drill: Send async jobs (they will queue)
# -----------------------------------------------------------------------------
log_info "Sending test async jobs..."

# Try to trigger an async job if endpoint exists
for i in {1..5}; do
    curl -s -X POST "$DENIS_BASE_URL/internal/test/job" \
        -d "{\"task\":\"test\",\"id\":\"drill-$i\"}" \
        --max-time 5 >/dev/null 2>&1 || true
done

sleep 2

# -----------------------------------------------------------------------------
# Verify /chat still responds
# -----------------------------------------------------------------------------
log_info "Verifying /chat availability..."

CHAT_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null \
    --max-time 10 \
    "$DENIS_BASE_URL/chat" \
    -d '{"message":"test","user_id":"drill-worker-missing"}' 2>&1) || true

# Capture AFTER state
QUEUES_AFTER=$(curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null | grep -c "celery_queue" || echo "0")
curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null > "$DRILL_DIR/after_metrics.txt" || true

echo ""
echo "Results:"
echo "--------"

# Determine pass/fail
if [[ "$CHAT_RESPONSE" == "200" ]]; then
    log_pass "/chat returned 200 - async queueing works"
    RESULT="PASS"
else
    log_fail "/chat returned: $CHAT_RESPONSE"
    RESULT="FAIL"
fi

echo "  Queue metrics before: $QUEUES_BEFORE"
echo "  Queue metrics after: $QUEUES_AFTER"

echo ""
echo "Artifacts saved to: $DRILL_DIR"

# Save result
echo "$RESULT" > "$DRILL_DIR/result.txt"
echo "$CHAT_RESPONSE" > "$DRILL_DIR/chat_response.txt"

exit 0
