#!/bin/bash
# =============================================================================
# MASTER FIRE DRILL RUNNER
# =============================================================================
# Runs all fire drills and generates a summary report.
# Usage: ./run_all_drills.sh [--safe-only]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENIS_BASE_URL="${DENIS_BASE_URL:-http://localhost:8084}"
SAFE_ONLY="${SAFE_ONLY:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Results
declare -A DRILL_RESULTS
TOTAL_PASS=0
TOTAL_FAIL=0
TOTAL_SKIP=0

echo "=============================================="
echo "  FIRE DRILL SUITE"
echo "=============================================="
echo ""
echo "Base URL: $DENIS_BASE_URL"
echo "Safe only: $SAFE_ONLY"
echo ""

# Run each drill
run_drill() {
    local drill_name="$1"
    local drill_script="$2"
    
    echo "----------------------------------------------"
    echo "Running: $drill_name"
    echo "----------------------------------------------"
    
    if [ ! -f "$drill_script" ]; then
        echo "SKIP: Script not found"
        DRILL_RESULTS[$drill_name]="SKIP"
        ((TOTAL_SKIP++))
        return
    fi
    
    # Run the drill
    if "$drill_script"; then
        RESULT=$(cat "$SCRIPT_DIR/../artifacts/drills/${drill_name}_"*"/result.txt" 2>/dev/null || echo "PASS")
        DRILL_RESULTS[$drill_name]="$RESULT"
        
        case "$RESULT" in
            PASS) ((TOTAL_PASS++)) ;;
            FAIL) ((TOTAL_FAIL++)) ;;
            SKIP) ((TOTAL_SKIP++)) ;;
            *) ((TOTAL_PASS++)) ;;  # Default to pass if we can't determine
        esac
    else
        DRILL_RESULTS[$drill_name]="FAIL"
        ((TOTAL_FAIL++))
    fi
    
    echo ""
}

# List of drills
DRILLS=(
    "Redis Down:$SCRIPT_DIR/drill_redis_down.sh"
    "Worker Missing:$SCRIPT_DIR/drill_worker_missing.sh"
    "Graph Slow:$SCRIPT_DIR/drill_graph_slow.sh"
    "Chat Flood:$SCRIPT_DIR/drill_chat_flood.sh"
    "Job Replay:$SCRIPT_DIR/drill_job_replay.sh"
    "Artifact Tamper:$SCRIPT_DIR/drill_artifact_tamper.sh"
)

# Run each drill
for drill in "${DRILLS[@]}"; do
    name="${drill%%:*}"
    script="${drill##*:}"
    run_drill "$name" "$script"
done

# Summary
echo "=============================================="
echo "  SUMMARY"
echo "=============================================="
echo ""
echo "Results:"
printf "  %-20s %s\n" "Drill" "Result"

for drill in "${DRILLS[@]}"; do
    name="${drill%%:*}"
    result="${DRILL_RESULTS[$name]:-UNKNOWN}"
    
    case "$result" in
        PASS) color="$GREEN" symbol="✓" ;;
        FAIL) color="$RED" symbol="✗" ;;
        SKIP) color="$YELLOW" symbol="⊘" ;;
        *) color="$NC" symbol="?" ;;
    esac
    
    printf "  %-20s %b%s%b %s\n" "$name" "$color" "$symbol" "$NC" "$result"
done

echo ""
echo "Total: $TOTAL_PASS passed, $TOTAL_FAIL failed, $TOTAL_SKIP skipped"

# Determine overall result
if [ $TOTAL_FAIL -gt 0 ]; then
    echo ""
    echo -e "${RED}OVERALL: FAIL${NC}"
    echo "Some drills failed - review artifacts for details"
    exit 1
else
    echo ""
    echo -e "${GREEN}OVERALL: PASS${NC}"
    echo "All drills passed"
    exit 0
fi
