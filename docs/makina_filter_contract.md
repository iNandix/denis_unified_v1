# Makina Filter Contract

## Overview

The `makina_filter` is an intent router middleware for OpenCode's fallback pipeline. It transforms user input into structured intent with candidates, scores, and confidence.

## Location

```
denis_unified_v1/inference/makina_filter.py
```

## Usage

```python
from denis_unified_v1.inference.makina_filter import filter_input, filter_input_safe

# Basic usage
result = filter_input({"prompt": "crea un nuevo componente"})

# With context refs
result = filter_input({
    "prompt": "arréglame el bug",
    "context_refs": ["file:///test.py"]
})

# Safe wrapper with explicit fail-open
result = filter_input_safe({"prompt": "test"})
```

## Output Contract

```json
{
  "intent": {
    "pick": "implement_feature",
    "confidence": 0.7
  },
  "intent_candidates": [
    {"name": "implement_feature", "score": 0.7},
    {"name": "debug_repo", "score": 0.3}
  ],
  "intent_trace": {
    "version": "makina_filter@1.0.0",
    "matched_rules": ["keyword:crea"],
    "features": {...},
    "reason": "keyword match for implement_feature"
  },
  "constraints": [],
  "context_refs": [],
  "acceptance_criteria": [],
  "output_format": "text",
  "missing_inputs": []
}
```

## Intent Types

- `implement_feature`: "crea", "haz", "implementa", "añade", etc.
- `debug_repo`: "arregla", "debug", "depura", "error", "bug", etc.
- `refactor_migration`: "refactoriza", "migra", "restructura", etc.
- `run_tests_ci`: "test", "prueba", "ci", "run", etc.
- `explain_concept`: "explica", "qué es", "cómo funciona", etc.
- `write_docs`: "documenta", "docs", "readme", etc.
- `design_architecture`: "diseña", "arquitectura", "estructura", etc.
- `toolchain_task`: "reindexa", "scrapea", "build", "deploy", etc.
- `ops_health_check`: "health", "status", "salud", etc.
- `incident_triage`: "incidente", "emergency", "alerta", etc.
- `plan_rollout`: "despliegue", "rollout", "release", etc.
- `greeting`: "hola", "hi", "hey", etc.
- `unknown`: Fallback when no intent matches

## Confidence Threshold

- **Low confidence (< 0.55)**: Returns `unknown` intent
- **High confidence (>= 0.55)**: Returns matched intent

## Debug Mode

Set `MAKINA_FILTER_DEBUG=1` environment variable to enable debug logging:

```bash
export MAKINA_FILTER_DEBUG=1
```

This will log intent detection details to the debug output.

## Error Handling

- **Fail-open**: If the router crashes, it returns `unknown` with confidence 0.0
- Use `filter_input_safe()` for guaranteed fail-open behavior

## Constraints Extraction

The filter automatically detects technology constraints from prompts:

- **Languages**: python, typescript, javascript, go, c, rust, java, kotlin, swift
- **Patterns**: async, testing, performance, security, containers, ci_cd, serverless, caching, message_queue

Example:
```
Input: "crea endpoint fastapi con tests"
Output: constraints: ["python", "testing"]
```

Constraints are also inferred from context_refs (e.g., `.py` files → `python`).

## Acceptance Criteria

Based on the detected intent, the filter adds default acceptance criteria:

| Intent | Criteria |
|--------|----------|
| implement_feature | función o clase existe, tests pasan, no errores de importación |
| debug_repo | error reproducible resuelto, tests no regresionan |
| run_tests_ci | todos los tests pasan, coverage no baja |
| refactor_migration | comportamiento idéntico, tests pasan |
| write_docs | README actualizado, ejemplos de uso incluidos |

## Missing Inputs

The filter detects missing inputs that may block execution:

| Condition | Missing Input |
|----------|---------------|
| Prompt < 5 words | intent_unclear |
| implement_feature without target | target_file |
| debug_repo without error details | error_details |
| design_architecture without system description | system_description |
| plan_rollout without environment | target_environment |
| toolchain_task without tool | tool_or_command |

## Pre-Execute Hook

The `pre_execute_hook()` function can block or enrich execution before it runs:

```python
from denis_unified_v1.inference.makina_filter import pre_execute_hook

should_proceed, output, block_reason = pre_execute_hook(
    prompt="crea componente react",
    context_refs=[]
)

if not should_proceed:
    print(f"Blocked: {block_reason}")
```

### Block Conditions

- **Protected paths**: If prompt or context_refs contain `service_8084.py`, `kernel/__init__.py`, or `FrontDenisACTUAL/public/`
- **Unclear intent**: If `intent_unclear` detected AND confidence < 0.4

## Control Plane Reporting

When `MAKINA_FILTER_REPORT=1` is set, the filter sends async reports to the control plane:

```bash
export MAKINA_FILTER_REPORT=1
```

Payload sent to `POST http://localhost:8084/api/makina/intent_report`:
```json
{
  "intent": "implement_feature",
  "confidence": 0.8,
  "constraints": ["python", "testing"],
  "missing_inputs": [],
  "acceptance_criteria": ["tests pasan"],
  "prompt_hash": "a1b2c3d4e5f6",
  "timestamp": "2026-02-18T22:00:00Z",
  "filter_version": "1.0.0"
}
```

This is fire-and-forget (100ms timeout, no blocking).
