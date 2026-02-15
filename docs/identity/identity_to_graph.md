# Identity → Graph (HOLD)

Este documento describe cómo mapear los artefactos de identidad (schema + report) al grafo, en modo HOLD.

## Entradas
- Schema: `docs/identity/identity_schema.yaml`
- Reporte: `reports/persona_canonical_report.json`
- (Pronto) Inventory: `docs/identity/identity_inventory.machine.json`
- Script: `scripts/ingest_identity_core.py`

## Nodos esenciales
- `Identity` (Denis)
- `PersonaCanonical` (entrypoint lógico)
- `PersonaReport` (persona_canonical_report)
- `SourceDocument` (denis_persona_canonical.py)
- `Anchor` (e.g., A:synthetic:main_guard, A:synthetic:status, A:asyncfunctiondef:health)
- `Chunk` (C:ENTRYPOINTS, C:EXTERNAL_INTERFACES, LEGACY_INTENT)
- `Action` (ACT:MAIN_ENTRY, ACT:HTTP_ENTRYPOINTS)
- `Invariant` (INV:NO_BYPASS_CORE)
- `BypassSurface` (BYP:ALT_ENTRYPOINT)
- `Evidence` (E:001, ...)

## Relaciones clave (ejemplos)
- (Identity)-[:HAS_ENTRYPOINT]->(PersonaCanonical)
- (PersonaCanonical)-[:SUMMARIZED_AS]->(PersonaReport)
- (PersonaReport)-[:DERIVED_FROM]->(SourceDocument)
- (Chunk)-[:CITES]->(Anchor)
- (Anchor)-[:IN]->(SourceDocument)
- (Action)-[:JUSTIFIED_BY]->(Chunk)
- (Action)-[:EVIDENCED_BY]->(Evidence)
- (Invariant)-[:EVIDENCED_BY]->(Evidence)
- (PersonaCanonical)-[:HAS_BYPASS]->(BypassSurface)
- (BypassSurface)-[:MITIGATED_BY]->(System:ActionAuthorizer|Atlas|CI_Gate)

## Validaciones previas (gates)
- `S:ENTRYPOINTS.anchors` no vacío
- `C:ENTRYPOINTS.machine_reason.evidence` > 0
- `ACT:MAIN_ENTRY` y `ACT:HTTP_ENTRYPOINTS` con evidencia

## Uso del script de ingesta (dry-run por defecto)
```bash
python3 scripts/ingest_identity_core.py \
  --schema docs/identity/identity_schema.yaml \
  --report reports/persona_canonical_report.json \
  --out graph/graph_seed.json
```

## Neo4j opcional
Exporta variables antes de ejecutar para habilitar ingest real (no implementado en HOLD; ahora solo seed):
```
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=...
```

## Semilla fundacional sugerida
- Purpose: `HumanAid` (Identity)-[:EXISTS_FOR]->(Purpose)
- Invariants: NoBypassCore, NoSilentChange, AlwaysAuditable, PurposeBeforePower
- Risks: CreatorOverride, PowerDrift, SilentDegradation
- Systems: ActionAuthorizer, CI_Gate, Atlas, HonestyCore
- Legacy: FoundationalIntent (texto: proteger humanos y creador; no demonio)

## Auditoría
El seed (`graph/graph_seed.json`) incluye `sources` con hashes SHA256 de schema y report. Conservar como snapshot reproducible.
