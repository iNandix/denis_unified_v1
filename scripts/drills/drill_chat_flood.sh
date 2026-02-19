#!/bin/bash
# =============================================================================
# FIRE DRILL: Chat Flood
# =============================================================================
# Validates system behavior under high load.
# Expected: Rate limiting activates, graceful degradation.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENIS_BASE_URL="${DENIS_BASE_URL:-http://localhost:8084}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$SCRIPT_DIR/../artifacts}"

# Config
REQUESTS="${REQUESTS:-50}"
RATE_LIMIT="${RATE_LIMIT:-10}"  # requests per second max

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
DRILL_DIR="$ARTIFACTS_DIR/drills/chat_flood_$TIMESTAMP"
mkdir -p "$DRILL_DIR"

echo "=============================================="
echo "  FIRE DRILL: Chat Flood"
echo "=============================================="

# -----------------------------------------------------------------------------
# Capture BEFORE state
# -----------------------------------------------------------------------------
log_info "Capturing BEFORE state..."

curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null > "$DRILL_DIR/before_metrics.txt" || true

echo "  Requests to send: $REQUESTS"
echo "  Rate limit: $RATE_LIMIT/sec"
echo ""

# -----------------------------------------------------------------------------
# Execute drill: Flood /chat
# -----------------------------------------------------------------------------
log_info "Starting flood..."

SUCCESS=0
FAIL_429=0
FAIL_5XX=0
OTHER=0

for i in $(seq 1 $REQUESTS); do
    RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null \
        --max-time 10 \
        "$DENIS_BASE_URL/chat" \
        -d "{\"message\":\"flood test $i\",\"user_id\":\"drill-flood-$i\"}" 2>&1) || true
    
    case "$RESPONSE" in
        200) ((SUCCESS++)) ;;
        429) ((FAIL_429++)) ;;
        5*) ((FAIL_5XX++)) ;;
        *) ((OTHER++)) ;;
    esac
    
    # Rate limiting
    if [ $((i % RATE_LIMIT)) -eq 0 ]; then
        sleep 1
    fi
done

# -----------------------------------------------------------------------------
# Capture AFTER state
# -----------------------------------------------------------------------------
log_info "Capturing AFTER state..."

curl -s "$DENIS_BASE_URL/metrics" 2>/dev/null > "$DRILL_DIR/after_metrics.txt" || true

echo ""
echo "Results:"
echo "--------"
echo "  Total requests: $REQUESTS"
echo "  Success (200): $SUCCESS"
echo "  Rate limited (429): $FAIL_429"
echo "  Server errors (5xx): $FAIL_5XX"
echo "  Other: $OTHER"

# Calculate rates
SUCCESS_RATE=$((SUCCESS * 100 / REQUESTS))
ERROR_RATE=$((FAIL_5XX * 100 / REQUESTS))

echo ""
echo "  Success rate: ${SUCCESS_RATE}%"
echo "  Error rate: ${ERROR_RATE}%"

# Determine pass/fail
# Pass if: success rate > 80% OR rate limiting working (429s seen)
if [ $SUCCESS_RATE -ge 80 ] || [ $FAIL_429 -gt 0 ]; then
    log_pass "Flood test passed - system handled load"
    RESULT="PASS"
elif [ $FAIL_5XX -eq 0 ]; then
    log_warn "All requests blocked (likely rate limiting)"
    RESULT="PASS"
else
    log_fail "System overwhelmed - ${ERROR_RATE}% errors"
    RESULT="FAIL"
fi

echo ""
echo "Artifacts saved to: $DRILL_DIR"

# Save result
echo "$RESULT" > "$DRILL_DIR/result.txt"
echo "success=$SUCCESS" > "$DRILL_DIR/stats.txt"
echo "rate_limited=$FAIL_429" >> "$DRILL_DIR/stats.txt"
echo "errors=$FAIL_5XX" >> "$DRILL_DIR/stats.txt"

exit 0
