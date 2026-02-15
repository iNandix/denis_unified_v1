# DENIS Quality Gates
# Globs: **/inference/**, **/*stream*.py, **/worker_dispatch*.py

## Code Quality
- Use ruff for linting and formatting.
- Run pytest for unit tests.
- Use mypy for type checking.
- Execute smoke tests for integration validation.

## Runtime Safeguards
- Set timeouts on network and stream operations to prevent hangs.
- Avoid infinite loops; ensure all iterative processes have termination conditions.

## Determinism
- Ensure all operations are reproducible; avoid random seeds or non-deterministic behavior.

## Prohibitions
- Código de ejemplo no usado.
- Abstracciones vacías.
- Funciones que solo delegan sin añadir lógica.

## Obligations
- Cada nuevo módulo debe aportar mejora concreta de capacidad (grafo, MCP, hooks, workflows, tests) o simplificación de algo existente (menos código, misma o más potencia).
