# DENIS Neo4j IDE Graph
# Globs: tools/ide_graph/**, **/*neo4j*.py

## Isolation
- IDE graph is isolated (ports 7475/7689, DB denis_ide_graph).
- Never touch production Neo4j.

## Schema
- Minimum: Workspace/Phase/Service/SmokeRun/Artifact.
- Relations: USES, VERIFIED_BY, HEALTHCHECKED_BY, PRODUCED.
