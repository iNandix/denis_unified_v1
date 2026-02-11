# DENIS Unified V1 (Incremental) - Phase 0

This scaffold initializes a safe Phase-0 baseline without touching legacy runtime paths.

## Master tracking
- Refactor phased plan + TODO board:
  - `/home/jotah/denis_unified_v1/REFRACTOR_PHASED_TODO.md`
- Daily operational checklist:
  - `/home/jotah/denis_unified_v1/DAILY_TODO.md`

## What is included
- `feature_flags.py`: single source of defaults for Phase-0 flags.
- `scripts/unified_v1_baseline_check.py`: captures ports, `/health` endpoints, and writes:
  - `denis_unified_v1/DENIS_BASELINE.md`
  - `denis_unified_v1/baseline_report.json`
- `.env.phase0.example`: reference values for incremental rollout.

## Run
```bash
cd /media/jotah/SSD_denis/home_jotah
python3 -m denis_unified_v1.feature_flags
python3 denis_unified_v1/scripts/unified_v1_baseline_check.py
```

## Phase-1 (Neo4j Quantum Augmentation)
Dry-run (safe):
```bash
python3 denis_unified_v1/scripts/phase1_quantum_augment.py \
  --out-json denis_unified_v1/phase1_augment_dry_run.json
```

Execute writes (requires `NEO4J_PASSWORD`):
```bash
export NEO4J_URI=bolt://10.10.10.1:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD='***'
python3 denis_unified_v1/scripts/phase1_quantum_augment.py \
  --execute \
  --out-json denis_unified_v1/phase1_augment_execute.json
```

Rollback dry-run:
```bash
python3 denis_unified_v1/scripts/phase1_quantum_rollback.py \
  --out-json denis_unified_v1/phase1_rollback_dry_run.json
```

Rollback execute:
```bash
python3 denis_unified_v1/scripts/phase1_quantum_rollback.py \
  --execute \
  --out-json denis_unified_v1/phase1_rollback_execute.json
```

## Phase-2 (Cortex Wrappers)
Dry-run smoke:
```bash
python3 denis_unified_v1/scripts/phase2_cortex_smoke.py \
  --out-json denis_unified_v1/phase2_cortex_smoke.json
```

Execute smoke (real perceive calls):
```bash
python3 denis_unified_v1/scripts/phase2_cortex_smoke.py \
  --execute \
  --out-json denis_unified_v1/phase2_cortex_smoke_execute.json
```

Phase-2 rollback:
```bash
rm -rf denis_unified_v1/cortex
rm -f denis_unified_v1/scripts/phase2_cortex_smoke.py
```

## Rollback
```bash
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1
```

## Risk assessment
- Runtime impact: low (no production imports changed yet).
- Data impact:
  - Phase-0: none (read-only checks).
  - Phase-1 execute: medium-low (idempotent property/index additions).
  - Phase-1 rollback: removes only phase-1 quantum properties.
  - Phase-2 execute smoke: low-medium (network calls only, no core mutation).
