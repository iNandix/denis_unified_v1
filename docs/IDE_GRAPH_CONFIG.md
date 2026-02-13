# IDE GRAPH CONFIG

## Objetivo

Grafo aislado para control-plane IDE, no producción. Usa Neo4j para track fases, servicios, smokes, artifacts, MCP servers.

## Esquema

- **Workspace**: nombre, path
- **Phase**: nombre, descripción
- **Service**: nombre, url, tipo
- **SmokeRun**: phase, ok, duration_ms, artifact_path, ts
- **Artifact**: path, content_hash, size
- **MCPServer**: nombre, tipo

## Relaciones

- Workspace USES Phase
- Phase VERIFIED_BY SmokeRun
- Service HEALTHCHECKED_BY SmokeRun
- SmokeRun PRODUCED Artifact
- Workspace USES MCPServer

## Example Queries

MATCH (p:Phase)-[:VERIFIED_BY]->(t:SmokeRun) RETURN p.name, t.name, t.ok LIMIT 10

MATCH (s:Service)-[:HEALTHCHECKED_BY]->(t:SmokeRun) RETURN s.name, t.name, t.ok LIMIT 10

MATCH (w:Workspace)-[:USES]->(m:MCPServer) RETURN w.name, m.name LIMIT 5
