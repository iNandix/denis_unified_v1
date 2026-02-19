"""DENIS Middleware API for OpenCode integration."""

import logging
import os
import re
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/middleware", tags=["middleware"])

MIDDLEWARE_TIMEOUT_MS = int(os.getenv("OPENCODE_DENIS_TIMEOUT_MS", "800"))
LOW_IMPACT_MODE = True


class ProSearchPrepareRequest(BaseModel):
    session_id: str
    user_text: str
    intent: Optional[str] = None
    constraints: list[str] = []
    env: dict[str, str] = {}


class ToolPlanItem(BaseModel):
    tool: str
    command: str
    purpose: str
    safety: str = "read_only"


class PostProcessConfig(BaseModel):
    extract: list[str] = []
    summarize: bool = True
    format: str = "bullet"


class ExecutionBudget(BaseModel):
    tool_timeout_ms: int = 1500
    max_output_chars: int = 8000
    artifact_threshold_chars: int = 6000


class ExecutionBrief(BaseModel):
    intent: str
    phase: str
    confidence: str
    budgets: ExecutionBudget
    tool_plan: list[ToolPlanItem]
    postprocess: PostProcessConfig
    notes_for_model: list[str]


class ProSearchPrepareResponse(BaseModel):
    execution_brief: ExecutionBrief
    warnings: list[str] = []


class PrepareRequest(BaseModel):
    session_id: str
    user_text: str
    target_provider: str
    target_model: str
    budget: dict[str, int]
    artifacts: list[dict[str, Any]] = []
    repo_context: Optional[dict[str, Any]] = None
    mode: str = "low_impact"
    output_preference: str = "json"
    risk_level: str = "low"


class PrepareResponse(BaseModel):
    prepared_prompt: str
    contextpack: dict[str, Any]
    recommended: dict[str, Any]
    trace_ref: dict[str, str | list[str]]
    warnings: list[str] = []
    missing_inputs: list[str] = []


class PostProcessRequest(BaseModel):
    session_id: str
    target_model: str
    raw_output: str
    output_mode: str
    schema: Optional[dict[str, Any]] = None
    artifacts: list[dict[str, Any]] = []


class PostProcessResponse(BaseModel):
    final_output: str | dict[str, Any]
    parse_ok: bool
    repairs_applied: list[str]
    trace_ref: dict[str, str | list[str]]


def _classify_intent(text: str) -> str:
    """Simple intent classification."""
    lower = text.lower()
    if (
        "write test" in lower
        or "write_spec" in lower
        or "add test" in lower
        or "create test" in lower
        or "implement test" in lower
    ):
        return "write_tests"
    if any(kw in lower for kw in ["fix", "bug", "error", "exception", "repair"]):
        return "fix_bug"
    if any(kw in lower for kw in ["refactor", "improve", "optimize", "clean"]):
        return "refactor"
    if any(kw in lower for kw in ["explain", "what", "how", "describe"]):
        return "explain"
    if any(kw in lower for kw in ["write", "create", "generate", "implement", "add"]):
        return "write_code"
    return "general"


def _extract_constraints(text: str) -> list[str]:
    """Extract constraints from user text."""
    constraints = []
    lower = text.lower()
    if "python" in lower or ".py" in text:
        constraints.append("python")
    if "typescript" in lower or ".ts" in text:
        constraints.append("typescript")
    if "javascript" in lower or ".js" in text:
        constraints.append("javascript")
    if "react" in lower:
        constraints.append("react")
    if "async" in lower:
        constraints.append("async")
    if "test" in lower:
        constraints.append("testing")
    return constraints


def _choose_output_mode(target_model: str) -> str:
    """Choose output mode based on model capabilities."""
    lower = target_model.lower()
    if any(kw in lower for kw in ["gpt-4", "gpt-4o", "claude", "sonnet"]):
        return "strict_json_schema"
    if any(kw in lower for kw in ["qwen", "mistral", "solar"]):
        return "tagged_json_block"
    return "human"


@router.post("/prepare")
async def prepare_request(req: PrepareRequest) -> PrepareResponse:
    """
    Prepare prompt/context for cloud LLM.

    Low-impact mode: Only classify, extract constraints, and build minimal contextpack.
    Never runs long research or generates code patches.
    """
    start_time = time.time()
    elapsed_ms = (time.time() - start_time) * 1000

    if elapsed_ms > MIDDLEWARE_TIMEOUT_MS:
        logger.warning(f"Middleware prepare exceeded timeout: {elapsed_ms}ms")

    intent = _classify_intent(req.user_text)
    constraints = _extract_constraints(req.user_text)
    output_mode = _choose_output_mode(req.target_model)

    prepared_prompt = f"""You are a coding assistant.

Task: {req.user_text}
Intent: {intent}
Constraints: {", ".join(constraints) if constraints else "none"}

Provide your response in {output_mode} format.
"""

    contextpack = {
        "session_id": req.session_id,
        "intent": intent,
        "constraints": constraints,
        "output_format": output_mode,
        "artifacts": req.artifacts,
        "repo_context": req.repo_context or {},
    }

    recommended = {
        "output_mode": output_mode,
        "stop": ["<end>", "Done."],
        "max_output_tokens": req.budget.get("max_output_tokens", 1500),
    }

    turn_id = str(uuid.uuid4())
    trace_ref = {
        "session_id": req.session_id,
        "turn_id": turn_id,
        "trace_ids": [],
    }

    warnings = []
    missing_inputs = []

    if not intent or intent == "general":
        missing_inputs.append("intent_unclear")
    if not constraints and "code" in intent:
        missing_inputs.append("no_constraints")

    return PrepareResponse(
        prepared_prompt=prepared_prompt,
        contextpack=contextpack,
        recommended=recommended,
        trace_ref=trace_ref,
        warnings=warnings,
        missing_inputs=missing_inputs,
    )


@router.post("/postprocess")
async def postprocess_response(req: PostProcessRequest) -> PostProcessResponse:
    """
    Validate/repair cloud output and store artifacts.

    Optional: Only processes if explicitly called.
    """
    repairs_applied = []
    parse_ok = True
    final_output = req.raw_output

    if req.output_mode in ["json", "strict_json_schema", "json_no_schema"]:
        try:
            import json

            json.loads(req.raw_output)
        except json.JSONDecodeError as e:
            parse_ok = False
            repairs_applied.append(f"json_parse_failed: {e}")

            repaired = req.raw_output
            repaired = repaired.replace("'", '"')
            try:
                json.loads(repaired)
                final_output = repaired
                repairs_applied.append("quote_fixes")
                parse_ok = True
            except:
                repairs_applied.append("repair_failed")

    session_id = req.session_id
    turn_id = str(uuid.uuid4())
    trace_ref = {
        "session_id": session_id,
        "turn_id": turn_id,
        "trace_ids": [],
    }

    return PostProcessResponse(
        final_output=final_output,
        parse_ok=parse_ok,
        repairs_applied=repairs_applied,
        trace_ref=trace_ref,
    )


def _detect_os_intent(text: str) -> Optional[str]:
    """Force-detect OS/system intents that should override other classifications."""
    lower = text.lower()

    process_keywords = [
        "procesos",
        "processes",
        "ps ",
        "pgrep",
        "pidof",
        "corren",
        "running",
        "pid",
        "qué está corriendo",
        "qué corre",
    ]
    if any(kw in lower for kw in process_keywords):
        return "system_process_query"

    port_keywords = [
        "puertos",
        "ports",
        "netstat",
        "lsof",
        "ss -",
        "qué puerto",
        "which port",
        "listening",
        "escuchando",
    ]
    if any(kw in lower for kw in port_keywords):
        return "system_port_check"

    resource_keywords = [
        "cpu",
        "ram",
        "memory",
        "disco",
        "disk",
        "espacio",
        "usage",
        "recursos",
        "system resources",
        "top",
        "htop",
        "free",
        "df ",
        "du ",
    ]
    if any(kw in lower for kw in resource_keywords):
        return "system_resource_check"

    service_keywords = [
        "systemctl",
        "systemd",
        "service",
        "daemon",
        "status",
        "docker ps",
        "contenedor",
    ]
    if any(kw in lower for kw in service_keywords):
        return "service_status_check"

    log_keywords = ["logs", "log ", "journalctl", "tail ", "ver logs", "últimas líneas"]
    if any(kw in lower for kw in log_keywords) and not any(
        w in lower for w in ["error", "fix", "bug"]
    ):
        return "log_inspect"

    return None


def _generate_tool_plan(
    intent: str, user_text: str, constraints: list[str]
) -> list[dict]:
    """Generate specific shell commands based on intent."""
    lower = user_text.lower()
    plan = []

    # Extract target - be smarter about context
    # For process queries: "procesos de X" -> X is target
    # For port queries: "puertos de X" / "puertos están usando X" -> X is target
    target = None
    if intent == "system_process_query":
        # Match "procesos de <target>" or "processes of <target>"
        target_match = re.search(
            r"(?:procesos|processes?|corren|running).*?(?:de |of )([a-zA-Z0-9_\-\.]+)",
            lower,
        )
        target = target_match.group(1) if target_match else None
    elif intent == "system_port_check":
        # Match "puertos de X", "usando los X-server", "X is using ports"
        # Look for patterns like "llama-server", "nginx", "python", etc.
        target_match = re.search(
            r"(?:usando los |usando |de )([a-zA-Z][a-zA-Z0-9_\-]+)", lower
        )
        target = (
            target_match.group(1)
            if target_match and len(target_match.group(1)) > 2
            else None
        )
    else:
        # Generic fallback
        target_match = re.search(
            r"(?:de |del |of )?([a-zA-Z0-9_\-\.]+)(?:\s|$)", user_text
        )
        target = target_match.group(1) if target_match else None

    if intent == "system_process_query":
        cmd = f"ps aux | grep -i {target or 'python'}"
        plan.append(
            {
                "tool": "shell",
                "command": cmd,
                "purpose": f"listar procesos de {target or 'python'}",
                "safety": "read_only",
            }
        )
        plan.append(
            {
                "tool": "shell",
                "command": "pgrep -af " + (target or "python"),
                "purpose": "buscar PIDs relacionados",
                "safety": "read_only",
            }
        )

    elif intent == "system_port_check":
        if target:
            plan.append(
                {
                    "tool": "shell",
                    "command": f"ss -lntp | grep -i {target}",
                    "purpose": f"ver puertos de {target}",
                    "safety": "read_only",
                }
            )
            plan.append(
                {
                    "tool": "shell",
                    "command": f"lsof -i | grep -i {target}",
                    "purpose": f"archivos abiertos por {target}",
                    "safety": "read_only",
                }
            )
        else:
            plan.append(
                {
                    "tool": "shell",
                    "command": "ss -lntp",
                    "purpose": "listar todos los puertos en escucha",
                    "safety": "read_only",
                }
            )

    elif intent == "system_resource_check":
        plan.append(
            {
                "tool": "shell",
                "command": "free -h",
                "purpose": "ver uso de RAM",
                "safety": "read_only",
            }
        )
        plan.append(
            {
                "tool": "shell",
                "command": "df -h",
                "purpose": "ver uso de disco",
                "safety": "read_only",
            }
        )
        plan.append(
            {
                "tool": "shell",
                "command": "top -bn1 | head -20",
                "purpose": "ver procesos con mayor uso CPU/RAM",
                "safety": "read_only",
            }
        )

    elif intent == "service_status_check":
        svc = target or "nginx"
        plan.append(
            {
                "tool": "shell",
                "command": f"systemctl status {svc} --no-pager",
                "purpose": f"ver estado del servicio {svc}",
                "safety": "read_only",
            }
        )
        plan.append(
            {
                "tool": "shell",
                "command": f"systemctl is-active {svc}",
                "purpose": f"ver si {svc} está activo",
                "safety": "read_only",
            }
        )

    elif intent == "log_inspect":
        plan.append(
            {
                "tool": "shell",
                "command": "journalctl -n 50 --no-pager",
                "purpose": "ver últimos 50 líneas del journal",
                "safety": "read_only",
            }
        )
        plan.append(
            {
                "tool": "shell",
                "command": "sudo journalctl -n 100 --no-pager -p err",
                "purpose": "ver últimos errores",
                "safety": "read_only",
            }
        )

    elif intent == "fix_bug":
        if target:
            plan.append(
                {
                    "tool": "shell",
                    "command": f"grep -r 'error\\|exception' --include='*.log' -n . 2>/dev/null | tail -20",
                    "purpose": "buscar errores en archivos",
                    "safety": "read_only",
                }
            )

    elif intent == "build":
        plan.append(
            {
                "tool": "shell",
                "command": "ls -la",
                "purpose": "listar archivos del proyecto",
                "safety": "read_only",
            }
        )
        if target:
            plan.append(
                {
                    "tool": "shell",
                    "command": f"ls -la {target}/",
                    "purpose": f"explorar estructura de {target}",
                    "safety": "read_only",
                }
            )

    return plan


@router.post("/prosearch/prepare")
async def prosearch_prepare(req: ProSearchPrepareRequest) -> ProSearchPrepareResponse:
    """
    PRO_SEARCH Prepare: Generate ExecutionBrief for efficient execution.

    This endpoint transforms natural language into a concrete execution plan
    with specific commands, budgets, and tool policies.
    """
    warnings = []

    # Force-detect OS intents (override classification if detected)
    os_intent = _detect_os_intent(req.user_text)
    intent = os_intent or req.intent or "general"

    if os_intent and req.intent and os_intent != req.intent:
        warnings.append(
            f"Intent overridden from {req.intent} to {os_intent} (OS pattern detected)"
        )

    # Determine phase and confidence
    phase = "local"
    confidence = "medium"

    if intent.startswith("system_"):
        phase = "local"
        confidence = "high"
    elif intent in ["fix_bug", "write_code", "write_tests"]:
        phase = "shallow_scan"
        confidence = "medium"
    elif intent in ["refactor", "code_review", "code_migration"]:
        phase = "escalate"
        confidence = "low"

    # Generate tool plan
    tool_plan = _generate_tool_plan(intent, req.user_text, req.constraints)

    # Default budgets
    budgets = {
        "tool_timeout_ms": 1500,
        "max_output_chars": 8000,
        "artifact_threshold_chars": 6000,
    }

    # Post-process config
    postprocess = {
        "extract": [],
        "summarize": True,
        "format": "bullet_table" if intent.startswith("system_") else "bullet",
    }

    # Notes for model
    notes = []
    if intent.startswith("system_"):
        notes = [
            "No abrir repo ni leer archivos fuente",
            "Solo ejecutar commands de tool_plan",
            "No inventar procesos: basarse solo en stdout",
            "Artifactizar si stdout > 6000 chars",
        ]
    elif intent == "fix_bug":
        notes = [
            "Primero entender el error",
            "No modificar código sin confirmar",
            "Si hay stack trace, extraer línea relevante",
        ]

    execution_brief = {
        "intent": intent,
        "phase": phase,
        "confidence": confidence,
        "budgets": budgets,
        "tool_plan": tool_plan,
        "postprocess": postprocess,
        "notes_for_model": notes,
    }

    return ProSearchPrepareResponse(execution_brief=execution_brief, warnings=warnings)


@router.get("/status")
async def middleware_status():
    """Middleware health check."""
    return {
        "status": "healthy",
        "mode": "low_impact",
        "timeout_ms": MIDDLEWARE_TIMEOUT_MS,
    }


# =============================================================================
# M3: SHADOW MODE - Intent Resolution from Graph (SSoT)
# =============================================================================


class IntentResolveRequest(BaseModel):
    prompt: str
    bot_profile: str = "builder"
    journey_state: str = "BUILDING"
    session_id: str


class IntentResolveResponse(BaseModel):
    intent_legacy: str
    phase_legacy: str
    intent_graph: Optional[str]
    phase_graph: Optional[str]
    task_profile_id: str
    tool_policy_id: str
    discrepancy: bool
    discrepancy_reason: Optional[str]
    latency_ms: int
    confidence: str


# In-memory keyword map for fast resolution (synced from graph)
_INTENT_KEYWORDS = {
    "system_process_query": [
        "proceso",
        "processes",
        "ps ",
        "pgrep",
        "pidof",
        "corren",
        "running",
        "pid",
        "qué está corr",
    ],
    "system_port_check": [
        "puertos",
        "ports",
        "ss ",
        "lsof",
        "netstat",
        "qué puerto",
        "qué están us",
    ],
    "system_resource_check": [
        "cpu",
        "ram",
        "memory",
        "disco",
        "disk",
        "espacio",
        "free -",
        "df -",
    ],
    "service_status_check": [
        "systemctl",
        "systemd",
        "service",
        "daemon",
        "docker ps",
        "docker images",
    ],
    "log_inspect": ["log", "logs", "journalctl", "tail -", "ver los"],
    "repo_summary": [
        "resumen",
        "summary",
        "resumen del",
        "describe the project",
        "descripción del",
    ],
    "repo_explore": [
        "estructura",
        "explorar",
        "explora",
        "scan",
        "analizar",
        "mapear",
        "architecture",
    ],
    "fix_bug": ["fix", "bug", "error", "arreglar", "corregir", "reparar", "soluciona"],
    "refactor": ["refactor", "mejorar", "optimizar", "clean code", "reestructurar"],
    "write_code": [
        "write",
        "create",
        "genera",
        "implementa",
        "add ",
        "nueva función",
        "nuevo archivo",
    ],
    "write_tests": ["test", "tests", "prueba", "unit test", "escribe tests"],
    "code_review": ["audit", "auditoría", "security", "vulnerability", "seguridad"],
    "deploy": ["deploy", "desplegar", "release", "publish"],
    "build": ["build", "compilar", "compile", "construir", "bundle"],
    "git_work": ["git", "commit", "push", "pull", "branch", "merge", "pr"],
    "help": ["help", "ayuda", "ayúdame", "can you", "me ayudas"],
    "greeting": ["hello", "hola", "hey", "buenas", "qué tal"],
    "project_health_check": [
        "analiza el directorio",
        "audita el proyecto",
        "audita el repo",
        "audita el repositorio",
        "revisa el proyecto",
        "revisa el repositorio",
        "estado del proyecto",
        "estado del repo",
        "estado del repositorio",
        "estado del código",
        "próximos pasos",
        "dime el estado",
        "revisar el repositorio",
        "analyze the directory",
        "audit the project",
        "audit the repo",
        "review the project",
        "project status",
        "repo health",
        "code health",
        "next steps",
        "health check del repositorio",
        "health check del proyecto",
    ],
    # Intent hermano: system_health_check (servicios, procesos, puertos)
    "system_health_check": [
        "estado de los servicios",
        "estado de procesos",
        "estado de puertos",
        "servicios activos",
        "procesos activos",
        "puertos activos",
        "qué servicios están corriendo",
        "system status",
        "services status",
        "processes status",
        "salud del sistema",
        "system health",
        "estado del sistema",
        "health check",
        "verificar el sistema",
        "verificar sistema",
        "revisar el sistema",
    ],
    # Intent hermano: repo_structure_explore (explorar sin cambiar)
    "repo_structure_explore": [
        "explora la estructura",
        "dime la estructura",
        "qué archivos hay",
        "cómo está organizado",
        "explore structure",
        "folder structure",
        "file structure",
        "repo structure",
        "estructura del repositorio",
        "estructura del proyecto",
        "explora el repositorio",
    ],
}

# Intent → TaskProfile mapping
_INTENT_TO_TASK_PROFILE = {
    "system_process_query": "incident_response",
    "system_port_check": "incident_response",
    "system_resource_check": "incident_response",
    "service_status_check": "incident_response",
    "log_inspect": "incident_response",
    "fix_bug": "tool_runner_read_only",
    "write_code": "codecraft_generate",
    "write_tests": "codecraft_generate",
    "refactor": "deep_audit",
    "code_review": "deep_audit",
    "code_migration": "deep_audit",
    "repo_summary": "premium_search",
    "repo_explore": "premium_search",
    "search_code": "premium_search",
    "explain_code": "premium_search",
    "build": "tool_runner_read_only",
    "deploy": "deep_audit",
    "git_work": "tool_runner_read_only",
    "help": "intent_detection_fast",
    "greeting": "intent_detection_fast",
    "project_health_check": "incident_triage",
    "system_health_check": "incident_response",
    "repo_structure_explore": "premium_search",
}

# Intent → ToolPolicy mapping
_INTENT_TO_TOOL_POLICY = {
    "system_process_query": "system_readonly",
    "system_port_check": "system_readonly",
    "system_resource_check": "system_readonly",
    "service_status_check": "system_readonly",
    "log_inspect": "system_readonly",
    "fix_bug": "code_analysis",
    "write_code": "code_write",
    "write_tests": "code_write",
    "refactor": "code_write",
    "code_review": "code_analysis",
    "code_migration": "code_write",
    "repo_summary": "code_analysis",
    "repo_explore": "code_analysis",
    "search_code": "code_analysis",
    "explain_code": "code_analysis",
    "build": "tool_runner_read_only",
    "deploy": "code_write",
    "git_work": "tool_runner_read_only",
    "help": "tool_runner_read_only",
    "greeting": "tool_runner_read_only",
    "project_health_check": "code_analysis",
    "system_health_check": "system_readonly",
    "repo_structure_explore": "code_analysis",
}

# Priority order for matching (more specific intents first)
# NOTE: project_health_check must come BEFORE system_health_check for "health check del repositorio"
_INTENT_PRIORITY = [
    "system_process_query",
    "system_port_check",
    "git_work",  # Check before system_resource_check to avoid "rama" -> "ram" false positive
    "system_resource_check",
    "service_status_check",
    "project_health_check",  # Before system_health_check to catch "health check del repositorio"
    "system_health_check",
    "log_inspect",
    "fix_bug",
    "refactor",
    "write_code",
    "write_tests",
    "code_review",
    "code_migration",
    "repo_summary",
    "repo_structure_explore",  # More specific than repo_explore
    "repo_explore",
    "build",
    "deploy",
    "help",
    "greeting",
]


def _resolve_intent_from_graph(
    prompt: str, bot_profile: str, journey_state: str
) -> dict:
    """Resolve intent using in-memory keywords with anti-trigger rules."""
    prompt_lower = prompt.lower()

    # G1: Git work anti-trigger - require actual git tokens
    # These are the REAL git tokens that should allow git_work
    git_tokens = [
        "git ",
        "git,",
        "git.",  # git command
        "commit",
        "commits",  # commit action
        "branch",
        "branches",  # branch action
        "merge",
        "merges",  # merge action
        "pull",
        "pulls",  # pull action
        "push",
        "pushes",  # push action
        "diff",
        "diffs",  # diff action
        "stash",
        "stashes",  # stash action
        "rebase",  # rebase action
        "pr ",
        " pr ",
        "pr,",  # PR (pull request) - space before to avoid "pro"
        "pull request",  # full phrase
    ]

    # Check for git tokens more carefully - need word boundaries
    import re

    has_git_token = bool(
        re.search(
            r"\b(git|commit|branch|merge|pull|push|diff|stash|rebase|pr)\b",
            prompt_lower,
        )
    )
    has_pull_request = "pull request" in prompt_lower

    # G2: Health boost - boost project_health_check when health keywords present
    # AND there's repo context (repositorio/proyecto) OR explicit project health phrases
    health_keywords = [
        "estado",
        "status",
        "salud",
        "health",
        "estado en que se encuentra",
        "proximos pasos",
        "next steps",
        "dime el estado",
        "analiza",
        "audita",
        "review",
    ]
    has_health_keyword = any(kw in prompt_lower for kw in health_keywords)

    # Additional check: if health keyword + repo context, prefer project_health_check
    has_repo_context = any(
        kw in prompt_lower for kw in ["repositorio", "proyecto", "repo ", "project "]
    )

    # G3: Track candidates for tiebreaker
    candidates = []

    for intent_name in _INTENT_PRIORITY:
        keywords = _INTENT_KEYWORDS.get(intent_name, [])
        matched_kw = None
        for kw in keywords:
            if kw in prompt_lower:
                matched_kw = kw
                break

        if matched_kw:
            # G1: Anti-trigger for git_work - require actual git tokens
            if intent_name == "git_work":
                # Allow git_work if: has real git token OR matched keyword is PR-related
                allow_git = (
                    has_git_token
                    or has_pull_request
                    or matched_kw in ["pr", "pull request"]
                )
                if not allow_git:
                    continue  # Skip git_work if no real git tokens

            # G2: Boost project_health_check when health keyword + repo context
            if (
                intent_name == "project_health_check"
                and has_health_keyword
                and has_repo_context
            ):
                phase = _get_default_phase(intent_name)
                task_profile = _INTENT_TO_TASK_PROFILE.get(
                    intent_name, "intent_detection_fast"
                )
                tool_policy = _INTENT_TO_TOOL_POLICY.get(
                    intent_name, "tool_runner_read_only"
                )
                return {
                    "intent": intent_name,
                    "phase": phase,
                    "task_profile_id": task_profile,
                    "tool_policy_id": tool_policy,
                    "_boosted": True,
                }

            candidates.append((intent_name, matched_kw))

    # G3: Tiebreaker - if git_work and project_health_check both matched but no git tokens
    if len(candidates) >= 2:
        intent_names = [c[0] for c in candidates]
        if (
            "git_work" in intent_names
            and "project_health_check" in intent_names
            and not has_git_token
        ):
            for intent_name in [
                "project_health_check",
                "repo_structure_explore",
                "repo_explore",
            ]:
                if intent_name in intent_names:
                    phase = _get_default_phase(intent_name)
                    task_profile = _INTENT_TO_TASK_PROFILE.get(
                        intent_name, "intent_detection_fast"
                    )
                    tool_policy = _INTENT_TO_TOOL_POLICY.get(
                        intent_name, "tool_runner_read_only"
                    )
                    return {
                        "intent": intent_name,
                        "phase": phase,
                        "task_profile_id": task_profile,
                        "tool_policy_id": tool_policy,
                    }

    if candidates:
        intent_name = candidates[0][0]
        phase = _get_default_phase(intent_name)
        task_profile = _INTENT_TO_TASK_PROFILE.get(intent_name, "intent_detection_fast")
        tool_policy = _INTENT_TO_TOOL_POLICY.get(intent_name, "tool_runner_read_only")
        return {
            "intent": intent_name,
            "phase": phase,
            "task_profile_id": task_profile,
            "tool_policy_id": tool_policy,
        }

    return {
        "intent": None,
        "phase": None,
        "task_profile_id": "intent_detection_fast",
        "tool_policy_id": "tool_runner_read_only",
        "error": "no_match",
    }


def _get_default_phase(intent: str) -> str:
    """Get default phase for intent based on cost."""
    high_cost_intents = [
        "refactor",
        "code_review",
        "code_migration",
        "deploy",
        "db_migration",
        "ml_work",
    ]
    medium_cost_intents = [
        "fix_bug",
        "write_code",
        "write_tests",
        "repo_summary",
        "repo_explore",
        "repo_structure_explore",
        "project_health_check",
        "performance_optim",
        "container_work",
        "ci_cd",
        "security_work",
        "api_work",
    ]
    # system_health_check is a system-level check, doesn't need repo access
    system_intents = [
        "system_health_check",
        "system_process_query",
        "system_port_check",
        "system_resource_check",
        "service_status_check",
        "log_inspect",
        "git_work",
        "build",
    ]

    if intent in high_cost_intents:
        return "escalate"
    elif intent in medium_cost_intents:
        return "shallow_scan"
    elif intent in system_intents:
        return "local"
    else:
        return "local"


def _get_intent_keywords(intent: str) -> list[str]:
    """Map intent to keywords for pattern matching (ES + EN)."""
    keyword_map = {
        "system_process_query": [
            "proceso",
            "processes",
            "ps ",
            "pgrep",
            "pidof",
            "corren",
            "running",
            "pid",
            "qué está corr",
        ],
        "system_port_check": [
            "puertos",
            "ports",
            "ss ",
            "lsof",
            "netstat",
            "qué puerto",
            "qué están us",
        ],
        "system_resource_check": [
            "cpu",
            "ram",
            "memory",
            "disco",
            "disk",
            "espacio",
            "free -",
            "df -",
        ],
        "service_status_check": [
            "systemctl",
            "systemd",
            "service",
            "daemon",
            "docker ps",
            "docker images",
        ],
        "log_inspect": ["log", "logs", "journalctl", "tail -", "ver los"],
        "repo_summary": [
            "resumen",
            "summary",
            "resumen del",
            "describe the project",
            "descripción del",
        ],
        "repo_explore": [
            "estructura",
            "explorar",
            "explora",
            "scan",
            "analizar",
            "mapear",
            "architecture",
        ],
        "suggest_next_steps": [
            "próximos pasos",
            "siguientes pasos",
            "next steps",
            "sugerencias",
        ],
        "fix_bug": [
            "fix",
            "bug",
            "error",
            "arreglar",
            "corregir",
            "reparar",
            "soluciona",
        ],
        "refactor": ["refactor", "mejorar", "optimizar", "clean code", "reestructurar"],
        "write_code": [
            "write",
            "create",
            "genera",
            "implementa",
            "add ",
            "nueva función",
            "nuevo archivo",
        ],
        "write_tests": ["test", "tests", "prueba", "unit test", "escribe tests"],
        "code_review": ["audit", "auditoría", "security", "vulnerability", "seguridad"],
        "code_migration": ["migrate", "migration", "migrar", "convert", "transformar"],
        "performance_optim": [
            "performance",
            "optim",
            "rendimiento",
            "profiling",
            "benchmark",
        ],
        "generate_docs": ["document", "docs", "documentación", "readme"],
        "configure": ["config", "configure", "configurar", "setup"],
        "install_deps": [
            "install",
            "dependencies",
            "deps",
            "paquetes",
            "npm install",
            "pip install",
        ],
        "run_code": ["run", "ejecutar", "execute", "start", "launch"],
        "build": ["build", "compilar", "compile", "construir", "bundle"],
        "deploy": ["deploy", "desplegar", "release", "publish"],
        "container_work": ["docker", "container", "kubernetes", "k8s", "pod"],
        "db_migration": ["database", "db", "migration", "sql", "schema"],
        "git_work": [
            "git",
            "commit",
            "push",
            "pull",
            "branch",
            "merge",
            "pr",
            "merge request",
        ],
        "ci_cd": ["ci", "cd", "pipeline", "github actions", "jenkins"],
        "security_work": ["security", "auth", "oauth", "jwt", "token", "encryption"],
        "search_code": ["search", "buscar", "find", "grep", "locate"],
        "explain_code": ["qué hace", "what does", "explain", "explica", "explicame"],
        "compare": ["compare", "diff", "versus", "vs"],
        "evaluate": ["evaluate", "eval", "assess", "measure", "check quality"],
        "api_work": ["api", "endpoint", "rest", "graphql", "route", "controller"],
        "ml_work": ["model", "train", "ml", "machine learning", "ai", "neural"],
        "help": ["help", "ayuda", "ayúdame", "can you", "me ayudas"],
        "greeting": ["hello", "hola", "hey", "buenas", "qué tal"],
        "farewell": ["bye", "adios", "chao", "goodbye", "nos vemos"],
    }
    return keyword_map.get(intent, [])


def _resolve_intent_legacy(prompt: str) -> tuple[str, str]:
    """Legacy intent resolution (Client Runtime pattern matching)."""
    # This mimics the Client Runtime behavior
    # In production, this would call the actual Client Runtime

    prompt_lower = prompt.lower()

    # Project health check (check BEFORE git_work to avoid "pr" false positive)
    if any(
        kw in prompt_lower
        for kw in [
            "analiza el directorio",
            "audita el proyecto",
            "revisa el proyecto",
            "revisa el repositorio",
            "estado del proyecto",
            "estado del repo",
            "estado del repositorio",
            "estado del código",
            "próximos pasos",
            "dime el estado",
            "revisar el repositorio",
            "analyze the directory",
            "audit the project",
            "review the project",
            "project status",
            "repo health",
            "code health",
            "next steps",
            "health check",
            "audit the repo",
        ]
    ):
        return "project_health_check", "shallow_scan"

    # Git work (check early to avoid false positives like "rama" matching "ram")
    if any(
        kw in prompt_lower
        for kw in [
            "git",
            "commit",
            "push",
            "pull",
            "pr",
            "pull request",
            "merge",
            "branch",
            "haz un commit",
            "haz commit",
            "hacer commit",
        ]
    ):
        return "git_work", "local"

    # System intents (high priority)
    if any(
        kw in prompt_lower
        for kw in ["proceso", "process", "ps ", "pgrep", "corren", "running"]
    ):
        return "system_process_query", "local"
    if any(kw in prompt_lower for kw in ["puerto", "port", "ss ", "lsof"]):
        return "system_port_check", "local"
    if any(kw in prompt_lower for kw in ["cpu", "ram", "memory", "disco"]):
        return "system_resource_check", "local"
    if any(kw in prompt_lower for kw in ["systemctl", "service", "docker"]):
        return "service_status_check", "local"
    if any(kw in prompt_lower for kw in ["log", "journalctl"]) and not any(
        w in prompt_lower for w in ["fix", "bug", "error"]
    ):
        return "log_inspect", "local"

    # Code intents
    if any(kw in prompt_lower for kw in ["fix", "bug", "error", "arreglar"]):
        return "fix_bug", "shallow_scan"
    if any(kw in prompt_lower for kw in ["refactor", "mejorar", "optimizar"]):
        return "refactor", "escalate"
    if any(kw in prompt_lower for kw in ["write", "create", "genera", "implementa"]):
        return "write_code", "shallow_scan"
    if any(kw in prompt_lower for kw in ["test", "prueba"]):
        return "write_tests", "shallow_scan"

    # Repo intents
    if any(kw in prompt_lower for kw in ["resumen", "summary", "describe"]):
        return "repo_summary", "shallow_scan"

    # Repo structure explore (A1 - more specific, check BEFORE project_health_check)
    # ES: "explora el repositorio", "revisa el repositorio", "estructura del repositorio"
    # EN: "repo structure", "file structure", "project structure"
    if any(
        kw in prompt_lower
        for kw in [
            "explora la estructura",
            "dime la estructura",
            "qué archivos hay",
            "cómo está organizado",
            "explore structure",
            "folder structure",
            "file structure",
            "repo structure",
            "project structure",
            "what is in the project",
            "estructura del repositorio",
            "estructura del proyecto",
            "estructura del repo",
            "explora el repositorio",
            "explorar el repositorio",
            "revisa el repositorio",
            "analiza el repositorio",
            "muestra la estructura",
            "ver estructura",
        ]
    ):
        return "repo_structure_explore", "shallow_scan"

    # Generic repo explore
    if any(kw in prompt_lower for kw in ["estructura", "explorar", "scan"]):
        return "repo_explore", "shallow_scan"

    # Project health check (A2 - specific phrases only, NO generic "revisa"/"check")
    # Must contain: "estado" OR "próximos pasos" OR "audita" OR "analiza" + proyecto/repo
    has_health_keyword = any(
        kw in prompt_lower
        for kw in [
            "estado del proyecto",
            "estado del repo",
            "estado del repositorio",
            "próximos pasos",
            "dime el estado",
            "analiza el directorio",
            "audita el proyecto",
            "audita el repo",
            "audita el repositorio",
            "analyze the directory",
            "audit the project",
            "audit the repo",
            "project status",
            "repo health",
            "code health",
            "next steps",
            "health check del repositorio",
            "revisar el repositorio",
            "review the project",
        ]
    )
    if has_health_keyword:
        return "project_health_check", "shallow_scan"

    # A3: Git work - add anti-triggers
    # Anti-trigger: if prompt has repo context (repositorio/estructura/carpetas), NOT git_work
    has_repo_context = any(
        kw in prompt_lower
        for kw in ["repositorio", "estructura", "carpetas", "directorios"]
    )
    has_git_keyword = any(
        kw in prompt_lower
        for kw in [
            "git",
            "commit",
            "push",
            "pull",
            "pr",
            "pull request",
            "merge",
            "branch",
            "haz un commit",
            "haz commit",
            "hacer commit",
        ]
    )
    if has_git_keyword and not has_repo_context:
        return "git_work", "local"

    # System health check (servicios, procesos, puertos)
    if any(
        kw in prompt_lower
        for kw in [
            "estado de los servicios",
            "estado de procesos",
            "estado de puertos",
            "servicios activos",
            "procesos activos",
            "puertos activos",
            "qué servicios están corriendo",
            "system status",
            "services status",
            "processes status",
            "salud del sistema",
            "system health",
            "estado del sistema",
            "health check del sistema",
            "check system health",
            "verificar el sistema",
            "verificar sistema",
            "revisar el sistema",
        ]
    ):
        return "system_health_check", "local"

    # Repo structure explore
    if any(
        kw in prompt_lower
        for kw in [
            "explora la estructura",
            "dime la estructura",
            "qué archivos hay",
            "cómo está organizado",
            "explore structure",
            "folder structure",
            "file structure",
            "repo structure",
            "estructura del repositorio",
            "estructura del proyecto",
            "explora el repositorio",
        ]
    ):
        return "repo_structure_explore", "shallow_scan"

    # DevOps
    if any(kw in prompt_lower for kw in ["deploy", "desplegar", "release"]):
        return "deploy", "escalate"

    if any(kw in prompt_lower for kw in ["build", "compilar", "compile"]):
        return "build", "local"

    # Help/Greeting
    if any(kw in prompt_lower for kw in ["help", "ayuda"]):
        return "help", "local"
    if any(kw in prompt_lower for kw in ["hello", "hola", "hi", "hey"]):
        return "greeting", "local"

    return "unknown", "local"


@router.post("/intent/resolve")
async def resolve_intent(req: IntentResolveRequest) -> IntentResolveResponse:
    """
    M3 Shadow Mode: Compare legacy vs graph intent resolution.

    This endpoint compares:
    - Legacy: Client Runtime intent detection (pattern matching)
    - Graph: SSoT intent from Neo4j

    Logs discrepancies for analysis but always returns legacy result.
    """
    start_time = time.time()

    # 1. Legacy resolution (current behavior)
    intent_legacy, phase_legacy = _resolve_intent_legacy(req.prompt)

    # 2. Graph resolution (new SSoT)
    graph_result = _resolve_intent_from_graph(
        req.prompt, req.bot_profile, req.journey_state
    )
    intent_graph = graph_result.get("intent")
    phase_graph = graph_result.get("phase")

    # 3. Compare
    discrepancy = False
    discrepancy_reason = None

    if intent_graph and intent_graph != intent_legacy:
        discrepancy = True
        discrepancy_reason = (
            f"intent_mismatch: legacy={intent_legacy} vs graph={intent_graph}"
        )

    # 4. Get task_profile_id and tool_policy_id from graph result
    task_profile_id = graph_result.get("task_profile_id", "intent_detection_fast")
    tool_policy_id = _INTENT_TO_TOOL_POLICY.get(intent_legacy, "tool_runner_read_only")

    # 5. Calculate confidence
    confidence = "high"
    if intent_graph is None or intent_legacy == "unknown":
        confidence = "low"
    elif discrepancy:
        confidence = "medium"

    latency_ms = int((time.time() - start_time) * 1000)

    # 6. Log for telemetry (in production, write to DecisionTrace/Neo4j)
    logger.info(
        f"[SHADOW] prompt={req.prompt[:50]}... legacy={intent_legacy} graph={intent_graph} task={task_profile_id} discrepancy={discrepancy} latency={latency_ms}ms"
    )

    return IntentResolveResponse(
        intent_legacy=intent_legacy,
        phase_legacy=phase_legacy,
        intent_graph=intent_graph,
        phase_graph=phase_graph,
        task_profile_id=task_profile_id,
        tool_policy_id=tool_policy_id,
        discrepancy=discrepancy,
        discrepancy_reason=discrepancy_reason,
        latency_ms=latency_ms,
        confidence=confidence,
    )
