# Sprint Automation (R1)

## Objetivo

Automatizar validación de checkpoint con un comando reproducible.

## Targets

- `make preflight`
- `make autopoiesis-smoke`
- `make gate-pentest`
- `make validate-r1`
- `make review-pack`
- `make checkpoint-r1`

## Flujo recomendado

```bash
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
make checkpoint-r1
```

`checkpoint-r1` ejecuta:
1. Preflight tooling (`phase10_gate_preflight.json`)
2. Smoke autopoiesis (`phase4_autopoiesis_smoke.json`)
3. Pentest gate (`phase10_gate_pentest.json`)
4. Review pack (`sprint_review.json`, `sprint_review.md`)
5. Falla (`exit 1`) si la decisión no es `GO`.

## Variables útiles

- `PYTHON` (default: `python3`)
- `SANDBOX_PYTHON` (default: `/tmp/denis_gate_venv/bin/python`)

Ejemplo:
```bash
make SANDBOX_PYTHON=/tmp/denis_gate_venv/bin/python checkpoint-r1
```

## Notas

- `autopoiesis-smoke` y `gate-pentest` cargan automáticamente variables desde `denis_unified_v1/.env` mediante `scripts/run_with_project_env.py`.
- Nunca se hace `source` de `.env`.

