#!/usr/bin/env python3
"""Phase 5 Cognitive Router Smoke Test."""

import json
import os
import sys
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
sys.path.insert(0, str(Path(__file__).parents[2]))

from orchestration.cognitive_router import CognitiveRouter

def main():
    os.makedirs("artifacts/orchestration", exist_ok=True)
    
    router = CognitiveRouter()
    start = time.time()
    decision = router.route_decision("debug this code error")
    latency = (time.time() - start) * 1000
    
    result = {
        "success": True,
        "latency_ms": latency,
        "tool_selected": decision.tool_name,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning
    }
    
    with open("artifacts/orchestration/phase5_cognitive_router_smoke.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print("Smoke passed")

if __name__ == "__main__":
    main()
