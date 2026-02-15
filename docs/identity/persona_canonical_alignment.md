# Persona Canonical Alignment (HOLD)

## Resumen
- Fuente: reports/persona_canonical_report.json
- Entrypoints anclados: A:synthetic:main_guard (guard __main__, líneas ~22787-22797)
- Chunks clave: C:ENTRYPOINTS (evidence=1), C:EXTERNAL_INTERFACES (status/health)
- Acciones primarias: ACT:MAIN_ENTRY, ACT:HTTP_ENTRYPOINTS (ambas con evidencia)
- Invariantes: INV:NO_BYPASS_CORE (hard)

## Entry points
- Anchors: A:synthetic:main_guard
- Evidencia: E:001 (guard __main__ con uvicorn.run)
- Política: todo request debe entrar por estos entrypoints; desviaciones = bypass surface

## Interfaces externas
- Anchors: A:synthetic:status, A:asyncfunctiondef:health
- Uso: salud y estado para monitoreo/control-plane

## Acciones
- ACT:MAIN_ENTRY → evidencia E:001
- ACT:HTTP_ENTRYPOINTS → evidencia E:001
- Requisito: ActionAuthorizer/CI/Atlas antes de ejecutar efectos

## Invariantes
- INV:NO_BYPASS_CORE → evidencia E:001
- Enforcers: ActionAuthorizer, Atlas, CI Gate, HonestyCore

## Bypass surfaces
- BYP:ALT_ENTRYPOINT → mitigación: ActionAuthorizer|Atlas|CI|CODEOWNERS

## Legacy intent (semilla)
- LEGACY_INTENT: proteger humanos y creador; no bypass; grafo como piedra angular

## Dependencias para grafo
- Personas/Report → PersonaReport persona_canonical_report
- Anchors/Chunks → usar chunk_ids y anchor_ids del reporte

## Checklist de alineación
- [x] ENTRYPOINTS con evidence>0
- [x] Acciones con evidence>0
- [x] Invariante no-bypass presente
- [x] Interfaces externas ancladas
- [ ] Inventory final integrado (pendiente)
