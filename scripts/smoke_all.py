#!/usr/bin/env python3
"""Smoke test master: ejecuta todos los tests."""
import subprocess
import json
import sys
from typing import Dict, Any, Tuple

tests = [
    ("Streaming SSE", "smoke_streaming.py"),
    ("API Metacognitiva", "smoke_metacognitive_api.py"),
    ("Autopoiesis", "smoke_autopoiesis.py"),
]

def parse_json_output(stdout: str, stderr: str) -> Tuple[Dict[str, Any], str]:
    """
    Parsea el output de un test buscando JSON válido.
    Retorna (parsed_json, status).
    """
    # Buscar el JSON completo (puede ser multilínea con objetos anidados)
    json_str = ""
    brace_count = 0
    started = False
    
    for line in stdout.split('\n'):
        if not started and line.strip().startswith('{'):
            started = True
        
        if started:
            json_str += line + '\n'
            brace_count += line.count('{') - line.count('}')
            
            # JSON completo cuando las llaves se balancean
            if brace_count == 0:
                break
    
    if not json_str.strip():
        return {}, "error"
    
    try:
        output = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        print(f"   Raw output: {json_str[:200]}...")
        return {}, "error"
    
    # Detectar status según estructura del JSON
    status = detect_status(output)
    return output, status

def detect_status(output: Dict[str, Any]) -> str:
    """
    Detecta el status de un test según la estructura del JSON.
    
    Casos:
    1. {"status": "pass", ...} → directo
    2. {"/endpoint": {"status": "pass"}, ...} → todos los sub-tests pass
    3. {"cycle": {...}, "proposals": {...}} → verificar campos específicos
    """
    # Caso 1: status directo
    if "status" in output:
        return output["status"]
    
    # Caso 2: múltiples endpoints (API Metacognitiva)
    if all(isinstance(v, dict) for v in output.values()):
        sub_statuses = [v.get("status") for v in output.values() if "status" in v]
        if sub_statuses and all(s == "pass" for s in sub_statuses):
            return "pass"
        if any(s == "error" for s in sub_statuses):
            return "error"
    
    # Caso 3: estructura específica (Autopoiesis)
    if "cycle" in output and "proposals" in output:
        cycle_status = output.get("cycle", {}).get("status")
        if cycle_status in ["awaiting_approval", "pass"]:
            return "pass"
    
    return "unknown"

results = {}

for name, script in tests:
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}")
    
    result = subprocess.run(
        ["python3", f"scripts/{script}"],
        capture_output=True,
        text=True,
        cwd="/media/jotah/SSD_denis/home_jotah/denis_unified_v1"
    )
    
    output, status = parse_json_output(result.stdout, result.stderr)
    
    results[name] = {
        "status": status,
        "output": output,
        "stderr": result.stderr if result.stderr else None
    }
    
    # Mostrar errores inmediatamente
    if status == "error" and result.stderr:
        print(f"⚠️  stderr: {result.stderr[:200]}")

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")

for name, result in results.items():
    status_icon = "✅" if result["status"] == "pass" else "❌"
    print(f"{status_icon} {name}: {result['status']}")
    
    # Mostrar detalles adicionales si hay error
    if result["status"] == "error":
        if result["stderr"]:
            print(f"   Error: {result['stderr'][:100]}")
        if not result["output"]:
            print(f"   No JSON output detected")

all_pass = all(r["status"] == "pass" for r in results.values())
print(f"\n{'='*60}")
print(f"{'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
print(f"{'='*60}")

# Exit code para CI/CD
sys.exit(0 if all_pass else 1)
