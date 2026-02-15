#!/usr/bin/env python3
"""
Control Panel Web Interface - Dashboard for DENIS Agent System.
Accessible for non-technical users.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


app = FastAPI(
    title="DENIS Control Panel",
    description="User-friendly control panel for DENIS Agent",
)
templates = Jinja2Templates(directory="templates")


PROJECT_INFO = {
    "name": "DENIS Unified v1",
    "version": "1.0.0",
    "description": "AI Agent Control Plane with Auto-Fix Loop",
    "owner": "iNandix",
    "repo": "denis_unified_v1",
    "github_url": "https://github.com/iNandix/denis_unified_v1",
}

STRATEGIC_HORIZON = {
    "vision": "Sistema de agente autónomo con control de calidad infalible",
    "phases": [
        {
            "id": 1,
            "name": "Control Plane Foundation",
            "description": "Sistema base de registry, policy y gates",
            "status": "completed",
            "progress": 100,
        },
        {
            "id": 2,
            "name": "Supervisor & Auto-Fix",
            "description": "Gate enforcement y loop de auto-corrección",
            "status": "completed",
            "progress": 100,
        },
        {
            "id": 3,
            "name": "GitHub Integration",
            "description": "CI/CD y branch protection",
            "status": "completed",
            "progress": 100,
        },
        {
            "id": 4,
            "name": "User Interface",
            "description": "Panel de control web",
            "status": "completed",
            "progress": 100,
        },
        {
            "id": 5,
            "name": "AI Analysis",
            "description": "Análisis de fallos con IA",
            "status": "completed",
            "progress": 100,
        },
    ],
}

COMPLETION_CRITERIA = [
    {"id": 1, "name": "Control Plane Registry", "weight": 15, "completed": True},
    {"id": 2, "name": "Policy Engine", "weight": 15, "completed": True},
    {"id": 3, "name": "Supervisor Gate", "weight": 15, "completed": True},
    {"id": 4, "name": "Auto-Fix Loop", "weight": 15, "completed": True},
    {"id": 5, "name": "GitHub CI Integration", "weight": 10, "completed": True},
    {"id": 6, "name": "Branch Protection", "weight": 10, "completed": True},
    {"id": 7, "name": "Web Dashboard", "weight": 10, "completed": True},
    {"id": 8, "name": "AI Analysis", "weight": 10, "completed": True},
]


def load_json_file(path: str, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default


def run_command(cmd: list, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_gate_status() -> dict:
    artifact = load_json_file(
        "artifacts/control_plane/supervisor_gate.json",
        {"ok": False, "overall_status": "unknown"},
    )
    return artifact


def get_smoke_summary() -> dict:
    smoke_all = load_json_file("artifacts/smoke_all.json", {"summary": {}})
    return smoke_all.get("summary", {})


def get_sprint_status() -> dict:
    sprint = load_json_file(
        "artifacts/agent/denis_agent_sprint_run.json", {"overall_status": "none"}
    )
    return sprint


def calculate_completion() -> dict:
    total_weight = sum(c["weight"] for c in COMPLETION_CRITERIA)
    completed_weight = sum(c["weight"] for c in COMPLETION_CRITERIA if c["completed"])
    percentage = (completed_weight / total_weight * 100) if total_weight > 0 else 0
    return {
        "percentage": round(percentage, 1),
        "completed": sum(1 for c in COMPLETION_CRITERIA if c["completed"]),
        "total": len(COMPLETION_CRITERIA),
        "criteria": COMPLETION_CRITERIA,
    }


def get_recent_activity() -> list:
    activities = []
    artifacts_dir = Path("artifacts/control_plane")
    if artifacts_dir.exists():
        for f in artifacts_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if "timestamp_utc" in data:
                        activities.append(
                            {
                                "file": f.name,
                                "timestamp": data["timestamp_utc"],
                                "status": data.get(
                                    "overall_status", data.get("ok", "unknown")
                                ),
                            }
                        )
            except:
                pass
    return sorted(activities, key=lambda x: x.get("timestamp", ""), reverse=True)[:10]


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    gate = get_gate_status()
    smoke = get_smoke_summary()
    sprint = get_sprint_status()
    completion = calculate_completion()
    recent = get_recent_activity()

    context = {
        "request": request,
        "project": PROJECT_INFO,
        "strategic": STRATEGIC_HORIZON,
        "gate": gate,
        "smoke": smoke,
        "sprint": sprint,
        "completion": completion,
        "recent_activity": recent,
        "now": datetime.now(timezone.utc).isoformat(),
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/api/status")
async def api_status():
    return {
        "project": PROJECT_INFO,
        "gate": get_gate_status(),
        "smoke": get_smoke_summary(),
        "sprint": get_sprint_status(),
        "completion": calculate_completion(),
    }


@app.get("/api/gate/run")
async def run_gate():
    result = run_command(
        [sys.executable, "scripts/supervisor_gate.py", "--mode=dev"], timeout=180
    )
    return {"success": result["success"], "gate": get_gate_status()}


@app.get("/api/fix/run")
async def run_fix():
    result = run_command(
        [sys.executable, "scripts/auto_fix_loop.py", "--max-iterations=3"], timeout=600
    )
    return {"success": result["success"], "gate": get_gate_status()}


@app.get("/api/enforce-push/run")
async def run_enforce():
    result = run_command(
        [sys.executable, "scripts/enforce_push.py", "--auto-fix", "--max-iterations=3"],
        timeout=600,
    )
    return {"success": result["success"], "gate": get_gate_status()}


@app.get("/api/smoke/run/{smoke_name}")
async def run_smoke(smoke_name: str):
    smoke_scripts = {
        "boot": "scripts/boot_import_smoke.py",
        "controlplane": "scripts/controlplane_status_smoke.py",
        "meta": "scripts/meta_smoke_all.py",
        "work": "scripts/work_compiler_smoke.py",
    }
    if smoke_name not in smoke_scripts:
        return {"success": False, "error": "Unknown smoke"}

    result = run_command([sys.executable, smoke_scripts[smoke_name]], timeout=120)
    return {"success": result["success"], "returncode": result.get("returncode", -1)}


@app.get("/api/completion")
async def api_completion():
    return calculate_completion()


@app.get("/api/strategic")
async def api_strategic():
    return STRATEGIC_HORIZON


@app.get("/api/smokes")
async def api_smokes():
    """Get all smoke tests with details."""
    smoke_all = load_json_file("artifacts/smoke_all.json", {"tests": []})
    return {
        "summary": smoke_all.get("summary", {}),
        "tests": smoke_all.get("tests", []),
        "overall_success": smoke_all.get("overall_success", False),
        "status": smoke_all.get("status", "unknown"),
    }


@app.get("/api/smoke/{smoke_name}")
async def api_smoke_detail(smoke_name: str):
    """Get detailed info for a specific smoke."""
    smoke_map = {
        "boot_import": "artifacts/boot_import_smoke.json",
        "legacy_imports": "artifacts/legacy_imports_smoke.json",
        "openai_router": "artifacts/openai_router_smoke.json",
        "observability": "artifacts/observability_smoke.json",
        "work_compiler": "artifacts/work_compiler_smoke.json",
        "gate_smoke": "artifacts/phase10_gate_smoke.json",
        "capabilities_registry": "artifacts/api/phase6_capabilities_registry_smoke.json",
    }
    if smoke_name not in smoke_map:
        return {"error": "Unknown smoke"}

    artifact = load_json_file(smoke_map[smoke_name], {"ok": False})
    return artifact


@app.get("/api/ai-status")
async def api_ai_status():
    """Get AI analysis configuration and status."""
    import os

    return {
        "enabled": os.getenv("AI_ANALYSIS_ENABLED", "true").lower() == "true",
        "provider": os.getenv("AI_ANALYSIS_PROVIDER", "openai"),
        "openai_model": os.getenv("AI_OPENAI_MODEL", "gpt-4o-mini"),
        "perplexity_model": os.getenv("AI_PERPLEXITY_MODEL", "sonar-small"),
        "max_iterations": int(os.getenv("AI_MAX_ITERATIONS", "5")),
    }


@app.get("/api/system-info")
async def api_system_info():
    """Get system information."""
    import os

    return {
        "pre_push_hook": os.path.exists(".git/hooks/pre-push"),
        "ci_workflow": os.path.exists(".github/workflows/smoke_strict.yml"),
        "control_plane_gateway": os.path.exists("scripts/supervisor_gate.py"),
        "denis_cli": os.path.exists("scripts/denis.py"),
        "ai_analysis": os.path.exists("scripts/denis_ai_analysis.py"),
    }


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🚀 DENIS Control Panel")
    print("=" * 60)
    print("📍 URL: http://localhost:8085")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8085)
