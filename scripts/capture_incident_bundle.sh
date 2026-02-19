#!/bin/bash
# =============================================================================
# INCIDENT ARTIFACT CAPTURE
# =============================================================================
# Captures incident data for postmortem analysis.
# Usage: ./capture_incident_bundle.sh [--incident-id ID]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENIS_BASE_URL="${DENIS_BASE_URL:-http://localhost:8084}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$SCRIPT_DIR/../artifacts}"

# Parse args
INCIDENT_ID="${1:-}"
while [[ $# -gt 0 ]]; do
    case $1 in
        --incident-id)
            INCIDENT_ID="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Generate incident ID if not provided
if [[ -z "$INCIDENT_ID" ]]; then
    INCIDENT_ID="incident_$(date +%Y%m%d_%H%M%S)"
fi

# Create incident directory
INCIDENT_DIR="$ARTIFACTS_DIR/incidents/$INCIDENT_ID"
mkdir -p "$INCIDENT_DIR"

echo "=============================================="
echo "  INCIDENT ARTIFACT CAPTURE"
echo "=============================================="
echo ""
echo "Incident ID: $INCIDENT_ID"
echo "Output: $INCIDENT_DIR"
echo ""

# =============================================================================
# Capture: Timestamp
# =============================================================================
echo "Capturing timestamp..."
echo "$(date -Iseconds)" > "$INCIDENT_DIR/timestamp.txt"

# =============================================================================
# Capture: Health Status
# =============================================================================
echo "Capturing health status..."

echo "# Health Check - $(date)" > "$INCIDENT_DIR/health.txt"
echo "" >> "$INCIDENT_DIR/health.txt"

curl -s --max-time 10 "$DENIS_BASE_URL/health" >> "$INCIDENT_DIR/health.txt" 2>&1 || \
    echo "UNREACHABLE: Health endpoint not available" >> "$INCIDENT_DIR/health.txt"

# =============================================================================
# Capture: Metrics
# =============================================================================
echo "Capturing metrics..."

curl -s --max-time 15 "$DENIS_BASE_URL/metrics" > "$INCIDENT_DIR/metrics.txt" 2>&1 || \
    echo "UNREACHABLE: Metrics endpoint not available" > "$INCIDENT_DIR/metrics.txt"

# =============================================================================
# Capture: Recent Logs (if available)
# =============================================================================
echo "Capturing recent logs..."

{
    echo "# Recent Logs - $(date)"
    echo ""
    echo "Note: Logs require kubectl access"
    echo "To capture logs manually:"
    echo "  kubectl logs -l app=denis -n denis --tail=100 > $INCIDENT_DIR/logs.txt"
} > "$INCIDENT_DIR/logs.txt" 2>/dev/null || true

# =============================================================================
# Capture: Environment Info
# =============================================================================
echo "Capturing environment info..."

{
    echo "# Environment - $(date)"
    echo ""
    echo "DENIS_BASE_URL: $DENIS_BASE_URL"
    echo "Hostname: $(hostname)"
    echo "Date: $(date)"
    echo ""
    echo "Environment variables (non-sensitive):"
    env | grep -E '^(DENIS|ASYNC|RUNS|MATERIALIZER)' | head -20 || echo "None found"
} > "$INCIDENT_DIR/environment.txt" 2>/dev/null || true

# =============================================================================
# Capture: System State
# =============================================================================
echo "Capturing system state..."

{
    echo "# System State - $(date)"
    echo ""
    echo "Note: System state requires kubectl access"
    echo "To capture manually:"
    echo "  kubectl get pods -n denis > $INCIDENT_DIR/pods.txt"
    echo "  kubectl get events -n denis --sort-by='.lastTimestamp' | tail -50 > $INCIDENT_DIR/events.txt"
} > "$INCIDENT_DIR/system_state.txt" 2>/dev/null || true

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "Artifacts captured:"
ls -la "$INCIDENT_DIR/"

echo ""
echo "=============================================="
echo "  CAPTURE COMPLETE"
echo "=============================================="
echo ""
echo "Incident bundle: $INCIDENT_DIR"
echo ""
echo "Next steps:"
echo "1. Review captured artifacts"
echo "2. Fill in postmortem template"
echo "3. Share with team"

exit 0
