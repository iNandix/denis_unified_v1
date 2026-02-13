import json
import os
import time
from pathlib import Path
import sys

# Root del repo: .../denis_unified_v1
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from version_control import VersionControl
from evolution_memory import EvolutionMemory

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def main():
    os.makedirs("artifacts/evolution", exist_ok=True)

    vc = VersionControl()
    em = EvolutionMemory()

    payload = {"test": "data", "version": 1}
    snapshot_result = vc.snapshot("test_snapshot", payload)

    decision = {"action": "test_decision", "reason": "validation"}
    decision_result = em.record_decision(decision)

    snapshots = vc.list_snapshots()
    if snapshots:
        loaded = vc.load(snapshots[0])
    else:
        loaded = {}

    recent = em.get_recent(10)

    ok = (
        snapshot_result.get("ok") and
        decision_result.get("recorded") and
        loaded.get("payload") == payload and
        len(recent) == 1
    )

    artifact = {
        "ok": ok,
        "timestamp_utc": _utc_now(),
        "snapshot_result": snapshot_result,
        "decision_result": decision_result,
        "loaded_payload": loaded.get("payload"),
        "recent_decisions_count": len(recent)
    }

    out_path = "artifacts/evolution/stream4_versioning_smoke.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print("Smoke passed" if ok else "Smoke failed")

if __name__ == "__main__":
    main()
