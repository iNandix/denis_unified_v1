# MakinaFilter Compiler Contract

## Overview

El `makina_filter` en `compiler/` es el filtro de fallback que genera programas Makina cuando el LLM falla. Transforma texto NL en pasos ejecutables deterministas.

## Location

```
denis_unified_v1/compiler/makina_filter.py
```

## Usage

```python
from denis_unified_v1.compiler.schemas import CompilerRequest
from denis_unified_v1.compiler.makina_filter import MakinaFilter

req = CompilerRequest(
    trace_id="abc123",
    run_id="run001",
    text="crea un test para auth"
)
mf = MakinaFilter()
result = mf.compile(req)
```

## Output Contract

```json
{
  "trace_id": "abc123",
  "run_id": "run001",
  "makina": {
    "task": {
      "id": "2d801ea2",
      "title": "crea un test para auth"
    },
    "steps": [
      {
        "id": "step_1",
        "kind": "read",
        "inputs": {"files": ["auth.py"]},
        "outputs": {},
        "guards": {}
      }
    ],
    "observability": {
      "emit_events": true,
      "log_tags": ["fallback", "makina_filter"],
      "graph_materialize": true
    }
  },
  "compiler": "fallback_local",
  "degraded": true,
  "confidence": 0.3,
  "plan": "Fallback plan:\n1. read: {...}"
}
```

## Destinatario: ¿quién consume esto?

| Campo | Destinatario | Para qué |
|-------|--------------|----------|
| `makina.steps` | **MakinaExecutor** | Ejecución de pasos |
| `confidence` | **ControlPlane** | Decidir si reintentar con LLM |
| `degraded` | **ControlPlane** | Flag para saber que es fallback |
| `plan` | **UX/Logger** | Mostrar al usuario qué se ejecutará |

## Step Kinds

| Kind | Descripción | Inputs requeridos |
|------|-------------|-------------------|
| `read` | Leer archivos | `files: List[str]` |
| `write` | Escribir archivo | `content: str`, `path: str` |
| `exec` | Ejecutar comando | `command: str` |
| `http_fallback` | Llamada HTTP | `url: str`, `method: str` |
| `ws_emit` | Emitir evento WS | `event: str`, `payload: dict` |
| `guard` | Validar condición | `condition: str` |

## Constraints Extraction

**Implementado:** El filter infiere constraints desde keywords.

| Keyword | Constraint |
|---------|------------|
| `python`, `py` | `python` |
| `npm`, `node`, `js` | `javascript` |
| `test`, `pytest`, `prueba` | `testing` |
| `async`, `await` | `async` |
| `fast`, `perf`, `rápido` | `performance` |

**No implementado aún:** Se debe extraer constraints del workspace y pasarlos al filter.

## Acceptance Criteria

**No implementado aún.** El filter debe inferir acceptance criteria según el intent:

| Intent | Acceptance Criteria |
|--------|---------------------|
| `implement_feature` | `["función existe", "tests pasan", "no errores"]` |
| `debug_repo` | `["error resuelto", "tests no regresionan"]` |
| `run_tests_ci` | `["todos los tests pasan"]` |

## Missing Inputs

**No implementado aún.** El filter debe detectar inputs faltantes:

| Condición | Missing Input |
|-----------|---------------|
| `read` sin archivos | `target_file` |
| `exec` sin comando | `command` |
| Prompt < 3 palabras | `intent_unclear` |

## Confidence Score

| Fuente | Score |
|--------|-------|
| LLM disponible | 0.9+ |
| Fallback (makina_filter) | 0.3 |
| Fallback total | 0.1 |

## Fallback Behavior

- **Fail-open**: Si el filtro falla, retorna un Makina básico con un paso `read`
- **Degraded flag**: Siempre `true` para outputs de fallback
- **Plan legible**: Siempre incluir `plan` para UX

## Errores Comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `Missing 'task' field` | Output no es JSON válido | Usar `MakinaValidator.repair()` |
| `Step missing 'kind'` | Step sin tipo | Default a `read` |
| Invalid JSON | LLM retornó markdown | Extraer de ````json` blocks |

## Tests

```bash
pytest tests/test_makina_filter.py -v
```

## Related

- **Inference filter**: `denis_unified_v1/inference/makina_filter.py` - Detecta intents
- **Contract inference**: `docs/makina_filter_contract.md` - Contrato para intents
- **Executor**: Makina program execution engine
