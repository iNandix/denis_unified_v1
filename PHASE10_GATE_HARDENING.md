# PHASE10 Gate Hardening

Fecha: `2026-02-11`  
Scope: hardening de gate real para Fase 4 (self-extension) con validacion fail-closed en sandbox temporal.

## Cambios

- Gate de sandbox real en `autopoiesis/self_extension_engine.py`:
  - `py_compile` real sobre modulo y test.
  - `ruff check` real.
  - `mypy` real.
  - `pytest -q` real.
  - `bandit -q -r` real.
- Politica `fail-closed`:
  - si falta tooling requerido en sandbox python -> rechazo (`missing_tool:*`).
  - si falla cualquier tool -> rechazo de sandbox y bloqueo de submit/approve/deploy.
- Refuerzo de policy:
  - bloqueo de patrones peligrosos (`eval/exec/subprocess/os.system/...`).
  - validacion de dependencias y reversibilidad.
  - aprobador humano obligatorio (rechaza `system/auto/bot/...`).
- Pentest imparcial E2E:
  - `scripts/phase4_gate_pentest.py`
  - evidencia en `phase10_gate_pentest.json`.

## Comandos De Validacion

Prereq de entorno (sandbox python dedicado):

```bash
/tmp/denis_gate_venv/bin/python -c "import importlib.util as u; mods=['ruff','mypy','pytest','bandit']; print({m: bool(u.find_spec(m)) for m in mods})"
```

Ejecucion pentest (E2E):

```bash
DENIS_SELF_EXTENSION_SANDBOX_PYTHON=/tmp/denis_gate_venv/bin/python \
PYTHONPATH=/media/jotah/SSD_denis/home_jotah \
/media/jotah/SSD_denis/.venv_oceanai/bin/python3 \
scripts/phase4_gate_pentest.py \
  --out-json /media/jotah/SSD_denis/home_jotah/denis_unified_v1/phase10_gate_pentest.json
```

Resultado esperado:
- `phase10_gate_pentest.json` con `status=ok`.
- `summary.failed = 0`.

## Evidencia Actual

- Archivo: `phase10_gate_pentest.json`
- Estado: `ok`
- Suite: `phase4_gate_pentest`
- Total checks: `5`
- Fallidos: `0`

## Riesgos

- Dependencia fuerte de tooling en sandbox python (`ruff/mypy/pytest/bandit`).
- Falsos negativos posibles si tests generados no cubren suficiente logica.
- Riesgo operativo si se cambia `DENIS_SELF_EXTENSION_SANDBOX_PYTHON` a un entorno incompleto.
- Costo de tiempo mayor por ejecutar 5 tools por propuesta.

## Rollback

Rollback recomendado por commit:

```bash
git revert <phase10_commit_sha>
```

Si hay commits posteriores de hardening, revertir en orden inverso:

```bash
git log --oneline -n 10
git revert <commit_mas_reciente_de_gate>
```

## Prerequisito De Tooling (Sandbox Python)

El interpreter configurado en `DENIS_SELF_EXTENSION_SANDBOX_PYTHON` debe tener:
- `mypy`
- `ruff`
- `pytest`
- `bandit`

Instalacion base ejemplo:

```bash
/tmp/denis_gate_venv/bin/python -m pip install mypy ruff pytest bandit
```
