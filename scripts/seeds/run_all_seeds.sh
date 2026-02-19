#!/usr/bin/env bash
set -e
NEO4J_URI=${NEO4J_URI_CANONICAL:-bolt://127.0.0.1:7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASS=${NEO4J_PASSWORD:-Leon1234$}
DIR="$(cd "$(dirname "$0")" && pwd)"
for f in "$DIR"/*.cypher; do
  echo "Seed: $f"
  cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" --format plain --file "$f"
done
echo 'All seeds OK'
