# DENIS Quality Gates

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
