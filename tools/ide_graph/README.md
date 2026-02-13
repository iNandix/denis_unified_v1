# IDE Graph

Local Neo4j instance for DENIS IDE control-plane graph.

## Run

```bash
docker compose up -d
```

## Stop

```bash
docker compose down
```

## Access

Open http://127.0.0.1:7475 in browser.

User: neo4j

Password: denis-ide-graph

## Clean data

```bash
docker compose down -v
```
