import json
import os
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))

from code_generation import generate_and_validate

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def main():
    os.makedirs("artifacts/code_generation", exist_ok=True)
    
    start = time.time()
    prompt = "generate a simple function"
    result = generate_and_validate(prompt)
    latency = time.time() - start
    
    # Add execution summary
    execution_summary = {
        "lines": len(result["code"].splitlines()) if result["code"] else 0,
        "returncode": result["execution"].get("returncode", -1)
    }
    
    artifact = {
        "ok": result["validation"]["valid"] and result["execution"]["success"],
        "latency_ms": latency * 1000,
        "timestamp_utc": _utc_now(),
        "prompt": prompt,
        "execution_summary": execution_summary,
        "code_generation": result
    }
    
    with open("artifacts/code_generation/stream1_code_generation_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)
    
    print("Smoke passed" if artifact["ok"] else "Smoke failed")

if __name__ == "__main__":
    main()
