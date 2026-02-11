# Contracts Directory

This folder is the canonical source for Denis Unified contract layers.

## Layers
- `level0_constitution.yaml`: non-negotiable invariants.
- `level1_topology.yaml`: structural and causal constraints.
- `level2_adaptive.yaml`: tunable behavior rules.
- `level3_emergent.yaml`: proposed/emergent contracts pending promotion.

## Workflow
1. Add or edit contract in the corresponding layer file.
2. Register it in `registry.yaml`.
3. Record change intent in `changes/`.
4. Validate against runtime behavior before enabling new flags.

## Safety
- Never store secrets in contract files.
- Keep changes reversible and traceable.
- Level 0 must not be changed without explicit human approval.

