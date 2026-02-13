#!/usr/bin/env python3
"""Smoke test master: ejecuta todos los tests."""
import subprocess
import json

tests = [
    ("Streaming SSE", "smoke_streaming.py"),
    ("API Metacognitiva", "smoke_metacognitive_api.py"),
    ("Autopoiesis", "smoke_autopoiesis.py"),
]

results = {}

for name, script in tests:
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}")
    
    result = subprocess.run(["python3", f"scripts/{script}"], capture_output=True, text=True, cwd="/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
    
    try:
        lines = [l for l in result.stdout.split('\n') if l.strip()]
        for line in reversed(lines):
            if line.startswith('{'):
                output = json.loads(line)
                results[name] = {"status": output.get("status", "unknown")}
                break
    except:
        results[name] = {"status": "error"}

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")

for name, result in results.items():
    status = "✅" if result["status"] == "pass" else "❌"
    print(f"{status} {name}: {result['status']}")

all_pass = all(r["status"] == "pass" for r in results.values())
print(f"\n{'='*60}")
print(f"{'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
print(f"{'='*60}")
