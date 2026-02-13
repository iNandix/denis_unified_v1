import json
import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from git_ops import simulate_infra_pipeline  # noqa: E402


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main() -> None:
    os.makedirs("artifacts/infra", exist_ok=True)

    # Caso allow: scripts/* debe pasar SafetyLimits
    diff_allow = "add logging to function\nprint('new line')\n"
    target_allow = "scripts/safe_script.py"
    res_allow = simulate_infra_pipeline(diff_allow, target_allow)

    # Caso block: api/* debe ser bloqueado por SafetyLimits
    diff_block = "print('touch protected api')\n"
    target_block = "api/metacognitive_api.py"
    res_block = simulate_infra_pipeline(diff_block, target_block)

    ok = (
        (res_allow.get("pipeline_passed") is True)
        and (res_allow.get("dry_run", {}).get("status") == "dry_run_success")
        and (res_block.get("pipeline_passed") is False)
        and (res_block.get("dry_run", {}).get("status") == "blocked")
    )

    artifact = {
        "ok": ok,
        "timestamp_utc": _utc_now(),
        "stream": "stream6_infra_pipeline",
        "cases": {
            "allowlisted_scripts": {
                "diff": diff_allow,
                "target_path": target_allow,
                "result": res_allow,
            },
            "protected_api_block": {
                "diff": diff_block,
                "target_path": target_block,
                "result": res_block,
            },
        },
    }

    out_path = "artifacts/infra/stream6_infra_smoke.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print("Smoke passed" if ok else "Smoke failed")


if __name__ == "__main__":
    main()
