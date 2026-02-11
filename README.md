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

Run polling daemon (5s, HASS + infra + tailscale refresh):
```bash
python3 denis_unified_v1/scripts/cortex_polling_daemon.py \
  --poll-interval 5 \
  --redis-url redis://localhost:6379/0
```

Phase-2 rollback:
```bash
rm -rf denis_unified_v1/cortex
rm -f denis_unified_v1/scripts/phase2_cortex_smoke.py
rm -f denis_unified_v1/scripts/cortex_polling_daemon.py
```

## Phase-3 (Metagraph Passive)
Snapshot (read-only graph analysis):
```bash
python3 denis_unified_v1/scripts/phase3_metagraph_snapshot.py \
  --out-json denis_unified_v1/phase3_metagraph_snapshot.json
```

Snapshot + Redis persistence:
```bash
python3 denis_unified_v1/scripts/phase3_metagraph_snapshot.py \
  --persist-redis \
  --out-json denis_unified_v1/phase3_metagraph_snapshot.json
```

If auto Neo4j config cannot resolve credentials, run with explicit env:
```bash
NEO4J_URI='bolt://10.10.10.1:7687' NEO4J_USER='neo4j' NEO4J_PASSWORD='***' \
python3 denis_unified_v1/scripts/phase3_metagraph_snapshot.py \
  --persist-redis \
  --out-json denis_unified_v1/phase3_metagraph_snapshot.json
```

Phase-3 rollback:
```bash
rm -rf denis_unified_v1/metagraph
rm -f denis_unified_v1/scripts/phase3_metagraph_snapshot.py
```

## Phase-4 (Autopoiesis Supervised)
Generate proposals + Redis persistence:
```bash
python3 denis_unified_v1/scripts/phase4_autopoiesis_smoke.py \
  --out-json denis_unified_v1/phase4_autopoiesis_smoke.json
```

Generate + approve first proposal (sandbox rollback, no auto-apply):
```bash
NEO4J_URI='bolt://10.10.10.1:7687' NEO4J_USER='neo4j' NEO4J_PASSWORD='***' \
python3 denis_unified_v1/scripts/phase4_autopoiesis_smoke.py \
  --approve-first \
  --out-json denis_unified_v1/phase4_autopoiesis_smoke.json
```

Phase-4 rollback:
```bash
rm -rf denis_unified_v1/autopoiesis
rm -f denis_unified_v1/scripts/phase4_autopoiesis_smoke.py
```

## Phase-5 (Orchestration Augmentation)
Run orchestration smoke (cortex + legacy fallback + circuit breaker):
```bash
NEO4J_URI='bolt://10.10.10.1:7687' NEO4J_USER='neo4j' NEO4J_PASSWORD='***' \
python3 denis_unified_v1/scripts/phase5_orchestration_smoke.py \
  --out-json denis_unified_v1/phase5_orchestration_smoke.json
```

Phase-5 rollback:
```bash
rm -rf denis_unified_v1/orchestration
rm -f denis_unified_v1/scripts/phase5_orchestration_smoke.py
```

## Phase-6 (API Unified Incremental)
Run API smoke (health + models + chat + tools + stream + websocket route):
```bash
python3 denis_unified_v1/scripts/phase6_api_smoke.py \
  --out-json denis_unified_v1/phase6_api_smoke.json
```

Optional run server:
```bash
DENIS_USE_API_UNIFIED=true \
uvicorn denis_unified_v1.api.fastapi_server:app --host 0.0.0.0 --port 8001 --workers 1
```

Phase-6 rollback:
```bash
rm -rf denis_unified_v1/api
rm -f denis_unified_v1/scripts/phase6_api_smoke.py
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
