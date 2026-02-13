import json
import os
import time
from pathlib import Path
import sys

# Root del repo: .../denis_unified_v1
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auto_evaluation import process_evaluation  # noqa: E402

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def main():
    os.makedirs("artifacts/evaluation", exist_ok=True)

    changes = [{"success": True}, {"success": False}]
    variant_a = {"score": 0.7}
    variant_b = {"score": 0.8}

    start = time.time()
    result = process_evaluation(changes, variant_a, variant_b)
    latency_ms = (time.time() - start) * 1000.0

    evaluation = result.get("evaluation", {})
    ab_test = result.get("ab_test", {})
    loop_close = result.get("loop_close", {})

    ok = (
        loop_close.get("loop_closed") is True
        and evaluation.get("evaluated_changes") == len(changes)
        and ab_test.get("winner") in {"A", "B"}
    )

    artifact = {
        "ok": ok,
        "latency_ms": latency_ms,
        "timestamp_utc": _utc_now(),
        "evaluation_processing": result,
    }

    out_path = "artifacts/evaluation/stream3_evaluation_smoke.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print("Smoke passed" if ok else "Smoke failed")

if __name__ == "__main__":
    main()
