# Anti-bypass Enforcement (HOLD)

## Principios duros
- No-bypass del núcleo: todo pasa por entrypoints oficiales.
- Sin cambios silenciosos: CI/Gates obligatorios.
- Auditoría total: cada acción debe dejar evidencia enlazada a anchors/chunks.
- Siempre explicable: se debe poder responder “por qué” con evidencia.

## Sistemas de enforcement
- ActionAuthorizer: verifica permisos/roles antes de ejecutar acción.
- Atlas (cambio/deriva): detecta cambios y deriva respecto al núcleo.
- CI Gate: bloquea cambios no revisados o sin evidencia.
- HonestyCore: no se puede mentir sobre capacidades/limitaciones.
- CODEOWNERS + pre-push: rutas críticas bajo gateo humano.

## Entry points protegidos
- Anchor: A:synthetic:main_guard (guard __main__, uvicorn.run)
- Chunk: C:ENTRYPOINTS (evidence=1)
- Acción: ACT:MAIN_ENTRY (evidence=1)
- Acción: ACT:HTTP_ENTRYPOINTS (evidence=1)
- Política: cualquier ruta alternativa = bypass surface.

## Bypass surfaces y mitigación
- BYP:ALT_ENTRYPOINT → Mitigación: ActionAuthorizer | Atlas | CI Gate | CODEOWNERS
- BYP:AUTH_MISSING → Mitigación: fail-fast (501) + CI test + observabilidad.
- BYP:ROUTER_PARTIAL_LOAD → Mitigación: degradación controlada + registro de degradación + test.

## Controles de CI recomendados
- Fallar si `S:ENTRYPOINTS.anchors` vacío.
- Fallar si `C:ENTRYPOINTS.machine_reason.evidence` vacío.
- Fallar si acciones primarias sin evidencia.
- Validar hashes contra persona_canonical_report.json.

## Grafo (semilla de enforcement)
- (Identity)-[:MUST_RESPECT]->(Invariant:NoBypassCore)
- (System:ActionAuthorizer)-[:MUST_ENFORCE]->(Invariant:NoBypassCore)
- (System:CI_Gate)-[:MUST_ENFORCE]->(Invariant:NoSilentChange)
- (System:Atlas)-[:MUST_ENFORCE]->(Invariant:AlwaysAuditable)
- (BypassSurface)-[:MITIGATED_BY]->(System:ActionAuthorizer|Atlas|CI_Gate)

## Observabilidad
- Registrar intentos de bypass: source, anchor/chunk, resultado (deny/allow).
- Exportar eventos al grafo: nodo Event con evidencia (hash/line).
- Smoke/CI deben verificar status/health/entrypoints expuestos.

## Modo HOLD
- Sin cambios de runtime.
- Solo análisis, documentación y semillas de grafo.
