#!/bin/bash
# =============================================================================
# PRODUCTION PREFLIGHT CHECK
# =============================================================================
# Validates critical and observability endpoints before deployment.
# Usage: ./production_preflight.sh [--strict] [--json] [BASE_URL]
# =============================================================================

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENIS_BASE_URL="${1:-${DENIS_BASE_URL:-http://localhost:8084}}"
STRICT_MODE="${STRICT_MODE:-false}"
JSON_OUTPUT="${JSON_OUTPUT:-false}"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --strict)
            STRICT_MODE=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--strict] [--json] [BASE_URL]"
            echo ""
            echo "Options:"
            echo "  --strict    Make /health and /telemetry CRITICAL (fail if unreachable)"
            echo "  --json      Output machine-readable JSON"
            echo "  BASE_URL    Base URL (default: http://localhost:8084)"
            exit 0
            ;;
        http*)
            DENIS_BASE_URL="$1"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Results storage
declare -A RESULTS
RESULTS[chat]=""
RESULTS[health]=""
RESULTS[telemetry]=""
RESULTS[metrics]=""

# Latency storage
declare -A LATENCIES
LATENCIES[chat]="0"
LATENCIES[health]="0"
LATENCIES[telemetry]="0"
LATENCIES[metrics]="0"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_endpoint() {
    local endpoint="$1"
    local critical="$2"  # "CRITICAL" or "OBS"
    local timeout="${3:-5}"
    
    local full_url="${DENIS_BASE_URL}${endpoint}"
    local start_time
    local http_code
    local response
    local elapsed
    
    start_time=$(date +%s%3N)
    
    # Try with curl (with timeout)
    response=$(curl -s -w "\n%{http_code}" \
        --max-time "$timeout" \
        --connect-timeout 3 \
        "$full_url" 2>&1) || true
    
    elapsed=$(($(date +%s%3N) - start_time))
    
    # Extract HTTP code (last line)
    http_code=$(echo "$response" | tail -n1)
    
    # Store latency
    LATENCIES[${endpoint//\//}]="$elapsed"
    
    # Determine status
    if [[ "$http_code" == "200" ]]; then
        RESULTS[${endpoint//\//}]="PASS|$elapsed"
        return 0
    elif [[ "$http_code" == "000" ]]; then
        # Connection failed
        RESULTS[${endpoint//\//}]="UNREACHABLE|0"
        return 1
    else
        RESULTS[${endpoint//\//}]="FAIL|$http_code"
        return 1
    fi
}

print_result() {
    local endpoint="$1"
    local critical="$2"
    local result="${RESULTS[${endpoint//\//}]}"
    local status="${result%%|*}"
    local extra="${result##*|}"
    
    local symbol color
    case "$status" in
        PASS)
            symbol="✓"
            color="$GREEN"
            ;;
        FAIL)
            symbol="✗"
            color="$RED"
            ;;
        UNREACHABLE|WARN)
            symbol="⚠"
            color="$YELLOW"
            ;;
        *)
            symbol="?"
            color="$RED"
            ;;
    esac
    
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        return 0
    fi
    
    printf "  %-20s %b%s%b" "$endpoint" "$color" "$symbol" "$NC"
    
    case "$status" in
        PASS)
            printf " PASS (${extra}ms)"
            ;;
        FAIL)
            printf " FAIL (HTTP $extra)"
            ;;
        UNREACHABLE)
            printf " UNREACHABLE"
            ;;
        *)
            printf " UNKNOWN"
            ;;
    esac
    
    if [[ "$critical" == "CRITICAL" ]]; then
        printf " [CRITICAL]"
    fi
    
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================

echo "=============================================="
echo "  PRODUCTION PREFLIGHT CHECK"
echo "=============================================="
echo ""
echo "Base URL: $DENIS_BASE_URL"
echo "Strict Mode: $STRICT_MODE"
echo ""

# Track exit code
EXIT_CODE=0
FAILED_CRITICAL=0

# -----------------------------------------------------------------------------
# Check /chat (CRITICAL)
# -----------------------------------------------------------------------------
echo "Checking endpoints..."

check_endpoint "/chat" "CRITICAL" 10
if [[ "${RESULTS[chat]}" == UNREACHABLE* ]]; then
    log_error "/chat is UNREACHABLE - system DOWN"
    FAILED_CRITICAL=1
    EXIT_CODE=1
elif [[ "${RESULTS[chat]}" == FAIL* ]]; then
    log_error "/chat returned error"
    FAILED_CRITICAL=1
    EXIT_CODE=1
fi

# -----------------------------------------------------------------------------
# Check /health (OBS or CRITICAL in strict mode)
# -----------------------------------------------------------------------------
HEALTH_CRITICAL="OBS"
if [[ "$STRICT_MODE" == "true" ]]; then
    HEALTH_CRITICAL="CRITICAL"
fi

check_endpoint "/health" "$HEALTH_CRITICAL" 5
if [[ "${RESULTS[health]}" == UNREACHABLE* ]] && [[ "$STRICT_MODE" == "true" ]]; then
    log_warn "/health unreachable in strict mode"
    FAILED_CRITICAL=1
    EXIT_CODE=1
fi

# Try alternate ports for telemetry/metrics
for alt_port in 8085 8084; do
    if [[ -z "${RESULTS[telemetry]}" ]] || [[ "${RESULTS[telemetry]}" == UNREACHABLE* ]]; then
        check_endpoint "/telemetry" "OBS" 5 2>/dev/null || true
    fi
    if [[ -z "${RESULTS[metrics]}" ]] || [[ "${RESULTS[metrics]}" == UNREACHABLE* ]]; then
        check_endpoint "/metrics" "OBS" 5 2>/dev/null || true
    fi
done

# -----------------------------------------------------------------------------
# Try 8085 for health if 8084 fails
# -----------------------------------------------------------------------------
if [[ "${RESULTS[health]}" == UNREACHABLE* ]]; then
    ALT_URL="${DENIS_BASE_URL/:8084/:8085}"
    DENIS_BASE_URL="$ALT_URL" check_endpoint "/health" "$HEALTH_CRITICAL" 5 2>/dev/null || true
fi

# =============================================================================
# Print Results
# =============================================================================

echo ""
echo "Results:"
echo "--------"

print_result "/chat" "CRITICAL"
print_result "/health" "$HEALTH_CRITICAL"
print_result "/telemetry" "OBS"
print_result "/metrics" "OBS"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="

if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}  ✓ ALL CHECKS PASSED${NC}"
    echo "=============================================="
    echo ""
    echo "Latencies:"
    printf "  /chat:        %sms\n" "${LATENCIES[chat]}"
    printf "  /health:      %sms\n" "${LATENCIES[health]}"
    printf "  /telemetry:   %sms\n" "${LATENCIES[telemetry]}"
    printf "  /metrics:     %sms\n" "${LATENCIES[metrics]}"
else
    if [[ $FAILED_CRITICAL -gt 0 ]]; then
        echo -e "${RED}  ✗ CRITICAL CHECKS FAILED${NC}"
        echo "=============================================="
        echo ""
        echo -e "${RED}System is NOT ready for production.${NC}"
        echo ""
        echo "To debug:"
        echo "  1. Check if server is running: ps aux | grep uvicorn"
        echo "  2. Check logs: kubectl logs -l app=denis -n denis"
        echo "  3. Try curl manually: curl -v ${DENIS_BASE_URL}/chat"
    else
        echo -e "${YELLOW}  ⚠ WARNINGS PRESENT (non-blocking)${NC}"
        echo "=============================================="
    fi
fi

echo ""

# JSON output if requested
if [[ "$JSON_OUTPUT" == "true" ]]; then
    cat << EOF
{
  "timestamp": "$(date -Iseconds)",
  "base_url": "$DENIS_BASE_URL",
  "strict_mode": $STRICT_MODE,
  "results": {
    "chat": {"status": "${RESULTS[chat]%%|*}", "latency_ms": ${LATENCIES[chat]}},
    "health": {"status": "${RESULTS[health]%%|*}", "latency_ms": ${LATENCIES[health]}},
    "telemetry": {"status": "${RESULTS[telemetry]%%|*}", "latency_ms": ${LATENCIES[telemetry]}},
    "metrics": {"status": "${RESULTS[metrics]%%|*}", "latency_ms": ${LATENCIES[metrics]}}
  },
  "exit_code": $EXIT_CODE
}
EOF
fi

exit $EXIT_CODE
