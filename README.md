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

## Phase-7 (Inference Router)
Run inference router smoke (provider scoring + fallback + metrics):
```bash
python3 denis_unified_v1/scripts/phase7_inference_smoke.py \
  --out-json denis_unified_v1/phase7_inference_smoke.json
```

Enable inference router in API:
```bash
DENIS_USE_INFERENCE_ROUTER=true \
uvicorn denis_unified_v1.api.fastapi_server:app --host 0.0.0.0 --port 8001 --workers 1
```

Phase-7 rollback:
```bash
rm -rf denis_unified_v1/inference
rm -f denis_unified_v1/scripts/phase7_inference_smoke.py
```

## Phase-8 (Voice Pipeline Incremental)
Run voice pipeline smoke (STT -> chat -> TTS + websocket streaming):
```bash
python3 denis_unified_v1/scripts/phase8_voice_smoke.py \
  --out-json denis_unified_v1/phase8_voice_smoke.json
```

Enable voice pipeline routes in unified API:
```bash
DENIS_USE_VOICE_PIPELINE=true \
uvicorn denis_unified_v1.api.fastapi_server:app --host 0.0.0.0 --port 8001 --workers 1
```

Voice routes added (flagged):
- `GET /v1/voice/health`
- `POST /v1/voice/process`
- `WS /v1/voice/stream`

Phase-8 rollback:
```bash
rm -rf denis_unified_v1/voice
rm -f denis_unified_v1/api/voice_handler.py
rm -f denis_unified_v1/scripts/phase8_voice_smoke.py
```

## Phase-9 (Unified Memory + Neuroplastic Contracts)
Run memory smoke (episodic/semantic/procedural/working + neuro/atlas bridge):
```bash
python3 denis_unified_v1/scripts/phase9_memory_smoke.py \
  --out-json denis_unified_v1/phase9_memory_smoke.json
```

Enable memory unified routes:
```bash
DENIS_USE_MEMORY_UNIFIED=true DENIS_USE_ATLAS=true \
uvicorn denis_unified_v1.api.fastapi_server:app --host 0.0.0.0 --port 8001 --workers 1
```

Memory routes added (flagged):
- `GET /v1/memory/health`
- `POST /v1/memory/episodic`
- `POST /v1/memory/semantic`
- `POST /v1/memory/procedural`
- `POST /v1/memory/working`
- `GET /v1/memory/neuro/layers`
- `GET /v1/memory/neuro/synergies`
- `GET /v1/memory/mental-loop/levels`
- `POST /v1/memory/cot/adaptive`
- `GET /v1/memory/atlas/projects`

Contracts:
- `contracts/level3_memory_neuroplastic.yaml`
  - 12 capas neuroplásticas (L1-L12)
  - 1 contrato global de continuidad
  - 4 niveles de mental loop
  - CoT adaptativa
  - Puente ATLAS + persistencia long-term

Phase-9 rollback:
```bash
rm -rf denis_unified_v1/memory
rm -f denis_unified_v1/api/memory_handler.py
rm -f denis_unified_v1/scripts/phase9_memory_smoke.py
```

## Phase-10 (Gate Hardening Real Tooling)
Run gate pentest against real sandbox tooling (`py_compile`, `ruff`, `mypy`, `pytest`, `bandit`):
```bash
python3 denis_unified_v1/scripts/phase4_gate_pentest.py \
  --out-json denis_unified_v1/phase10_gate_pentest.json
```

Optional explicit sandbox interpreter:
```bash
DENIS_SELF_EXTENSION_SANDBOX_PYTHON=/tmp/denis_gate_venv/bin/python \
python3 denis_unified_v1/scripts/phase4_gate_pentest.py \
  --out-json denis_unified_v1/phase10_gate_pentest.json
```

Gate behavior:
- fail-closed if any required tool is missing in strict mode.
- sandbox validation requires all checks to pass:
  - compile
  - typecheck
  - lint
  - tests
  - security scan

Phase-10 rollback:
```bash
git revert <phase10_commit_sha>
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
