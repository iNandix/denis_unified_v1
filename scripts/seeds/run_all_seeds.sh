#!/usr/bin/env bash
# Production-ready seed runner with Neo4j health check

set -e
set -o pipefail

NEO4J_URI=${NEO4J_URI:-bolt://127.0.0.1:7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASS=${NEO4J_PASSWORD:-Leon1234$}
SEEDS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/tmp/denis/seeds_run.log"

mkdir -p /tmp/denis
echo "=== Seed run started at $(date) ===" | tee -a "$LOG_FILE"

# Check Neo4j health
check_neo4j() {
    echo "Checking Neo4j at $NEO4J_URI..." | tee -a "$LOG_FILE"
    
    # Try cypher-shell first
    if command -v cypher-shell &> /dev/null; then
        if cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" "RETURN 1" &> /dev/null; then
            echo "✓ Neo4j is healthy" | tee -a "$LOG_FILE"
            return 0
        fi
    fi
    
    # Fallback: try with python neo4j driver
    if python3 -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('$NEO4J_URI', auth=('$NEO4J_USER', '$NEO4J_PASS')); d.verify_connectivity(); d.close()" 2>/dev/null; then
        echo "✓ Neo4j is healthy (via Python)" | tee -a "$LOG_FILE"
        return 0
    fi
    
    echo "✗ Neo4j is not reachable" | tee -a "$LOG_FILE"
    return 1
}

if ! check_neo4j; then
    echo "ERROR: Neo4j not available. Exiting." | tee -a "$LOG_FILE"
    exit 1
fi

# Run seeds in order
SEEDS=(
    "graph_bootstrap.cypher"
    "graph_seeds.cypher"
    "intent_schema_constraints.cypher"
    "intent_system_seeds.cypher"
    "system_state_v1.cypher"
    "system_state_v2.cypher"
    "system_state_v3.cypher"
    "codecraft_chunks_core_v1.cypher"
    "codecraft_constraints_v1.cypher"
    "codecraft_policies_v1.cypher"
    "codecraft_skill_v1.cypher"
    "constitution_seed.cypher"
    "identity_seed.cypher"
    "persona_seed.cypher"
    "learning_patterns_seed.cypher"
)

FAILED=0
for seed in "${SEEDS[@]}"; do
    seed_path="$SEEDS_DIR/$seed"
    if [ -f "$seed_path" ]; then
        echo "Running: $seed" | tee -a "$LOG_FILE"
        if cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" --format plain --file "$seed_path" >> "$LOG_FILE" 2>&1; then
            echo "✓ $seed OK" | tee -a "$LOG_FILE"
        else
            echo "✗ $seed FAILED" | tee -a "$LOG_FILE"
            FAILED=$((FAILED + 1))
        fi
    else
        echo "⚠ $seed not found, skipping" | tee -a "$LOG_FILE"
    fi
done

if [ $FAILED -eq 0 ]; then
    echo "=== All seeds completed successfully at $(date) ===" | tee -a "$LOG_FILE"
    exit 0
else
    echo "=== $FAILED seed(s) failed at $(date) ===" | tee -a "$LOG_FILE"
    exit 1
fi
