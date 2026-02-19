#!/bin/bash
# =============================================================================
# CANARY TOGGLE SCRIPT
# =============================================================================
# Sets canary percentage for materializers and other features.
# Usage: ./canary_set.sh <percentage> [--dry-run]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PERCENTAGE="${1:-}"
DRY_RUN="${DRY_RUN:-false}"

# Parse args
DRY_RUN=false
if [[ "${2:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

if [[ -z "$PERCENTAGE" ]]; then
    echo "Usage: $0 <percentage> [--dry-run]"
    echo ""
    echo "Percentages: 0, 1, 10, 50, 100"
    echo ""
    echo "Environment variables to set:"
    echo "  DENIS_MATERIALIZERS_PCT   - Materializers traffic %"
    echo "  ASYNC_ENABLED             - Enable async workers (0/1)"
    echo "  RUNS_ENABLED             - Enable async runs (0/1)"
    echo "  DENIS_SECONDARY_ENGINES  - Enable secondary engines (true/false)"
    exit 1
fi

# Validate percentage
case "$PERCENTAGE" in
    0|1|10|50|100) ;;
    *)
        echo "Error: Percentage must be 0, 1, 10, 50, or 100"
        exit 1
        ;;
esac

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=============================================="
echo "  CANARY TOGGLE"
echo "=============================================="
echo ""
echo "Percentage: $PERCENTAGE%"
echo "Dry run: $DRY_RUN"
echo ""

# Define what to set based on percentage
case "$PERCENTAGE" in
    0)
        log_info "Setting: All disabled"
        ENV_VARS=(
            "DENIS_MATERIALIZERS_ENABLED=false"
            "DENIS_MATERIALIZERS_PCT=0"
            "ASYNC_ENABLED=false"
            "RUNS_ENABLED=false"
        )
        ;;
    1)
        log_info "Setting: 1% canary"
        ENV_VARS=(
            "DENIS_MATERIALIZERS_ENABLED=true"
            "DENIS_MATERIALIZERS_PCT=1"
            "ASYNC_ENABLED=true"
            "RUNS_ENABLED=false"
        )
        ;;
    10)
        log_info "Setting: 10% canary"
        ENV_VARS=(
            "DENIS_MATERIALIZERS_ENABLED=true"
            "DENIS_MATERIALIZERS_PCT=10"
            "ASYNC_ENABLED=true"
            "RUNS_ENABLED=false"
        )
        ;;
    50)
        log_info "Setting: 50% canary"
        ENV_VARS=(
            "DENIS_MATERIALIZERS_ENABLED=true"
            "DENIS_MATERIALIZERS_PCT=50"
            "ASYNC_ENABLED=true"
            "RUNS_ENABLED=true"
        )
        ;;
    100)
        log_info "Setting: 100% - Full rollout"
        ENV_VARS=(
            "DENIS_MATERIALIZERS_ENABLED=true"
            "DENIS_MATERIALIZERS_PCT=100"
            "ASYNC_ENABLED=true"
            "RUNS_ENABLED=true"
        )
        ;;
esac

echo ""
echo "Environment variables to set:"
echo ""
for var in "${ENV_VARS[@]}"; do
    echo "  export $var"
done

echo ""

if [ "$DRY_RUN" = "true" ]; then
    log_warn "Dry run - no changes made"
    exit 0
fi

# Apply changes (only showing what to do)
echo ""
echo "To apply in Kubernetes:"
echo ""
echo "  # For deployment:"
echo "  kubectl set env deployment/denis ${ENV_VARS[*]} -n denis"
echo "  kubectl rollout restart deployment/denis -n denis"
echo ""
echo "  # To verify:"
echo "  curl http://localhost:8084/metrics | grep materializer"

# Check if we're in a Kubernetes environment
if kubectl cluster-info &>/dev/null; then
    echo ""
    read -p "Apply changes now? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Applying changes..."
        kubectl set env deployment/denis ${ENV_VARS[*]} -n denis 2>/dev/null || \
            log_warn "kubectl not available or not in correct context"
        kubectl rollout restart deployment/denis -n denis 2>/dev/null || \
            log_warn "Could not restart deployment"
        log_info "Changes applied"
    fi
else
    log_info "Not in Kubernetes - showing commands only"
fi

# Verification
echo ""
echo "Verification commands:"
echo ""
echo "  # Check metrics"
echo "  curl -s http://localhost:8084/metrics | grep -E 'materializer|async'"
echo ""
echo "  # Check environment (in pod)"
echo "  kubectl exec -it deployment/denis -n denis -- env | grep -E 'MATERIALIZERS|ASYNC|RUNS'"

exit 0
