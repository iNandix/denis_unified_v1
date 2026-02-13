import json
import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safety_limits import SafetyLimits  # noqa: E402


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main() -> None:
    os.makedirs("artifacts/safety", exist_ok=True)

    safety = SafetyLimits()

    # Caso 1: bloqueo determinista por path protegido
    v1 = safety.check_change(
        path="api/metacognitive_api.py",
        patch_text="print('touch protected api')",
        mode="enforce",
    )

    # Caso 2: allowlisted (scripts)
    v2 = safety.check_change(
        path="scripts/streamX_dummy.py",
        patch_text="print('safe change')",
        mode="enforce",
    )

    ok = (
        (v1.get("ok") is False and v1.get("decision") == "block" and v1.get("reason") == "protected_path")
        and (v2.get("ok") is True and v2.get("decision") in {"allow", "degraded_allow"})
    )

    artifact = {
        "ok": ok,
        "timestamp_utc": _utc_now(),
        "stream": "stream5_safety_limits",
        "results": {
            "protected_path_block": v1,
            "allowlisted_change": v2,
        },
    }

    out_path = "artifacts/safety/stream5_safety_smoke.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print("Smoke passed" if ok else "Smoke failed")


if __name__ == "__main__":
    main()
