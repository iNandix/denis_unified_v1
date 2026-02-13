#!/usr/bin/env python3
"""Phase 8 Metacognitive Voice Smoke Test."""

import json
import os
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))

from voice.metacognitive_voice import process_voice


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main():
    os.makedirs("artifacts/voice", exist_ok=True)

    start = time.time()
    result = process_voice("Hello, I am happy to help!")
    latency = time.time() - start

    artifact = {
        "ok": True,
        "latency_ms": latency * 1000,
        "timestamp_utc": _utc_now(),
        "voice_analysis": result,
        "emotion_detected": result["modulation"]["emotion"],
        "resonance_score": result["resonance"],
        "impact_level": result["impact"]["impact"],
        "prosody_suggestions": result["prosody"]
    }

    with open("artifacts/voice/phase8_metacognitive_voice_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)

    print("Smoke passed")

if __name__ == "__main__":
    main()
