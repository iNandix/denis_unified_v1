# RUNBOOK IDE CONTROL PLANE

## Arrancar Neo4j IDE graph

```bash
cd tools/ide_graph
docker compose up -d
```

## Ejecutar smokes

```bash
python3 scripts/phase11_sprint_orchestrator_smoke.py --out-json artifacts/sprint/phase11_sprint_orchestrator_smoke.json
```

## Ver artifacts

```bash
ls artifacts/
cat artifacts/sprint/phase11_sprint_orchestrator_smoke.json
```

## Recuperar/limpiar estado

```bash
rm -rf .sprint_orchestrator
rm -rf /tmp/denis*
```
