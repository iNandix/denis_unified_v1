"""
Makina Filter - OpenCode Intent Router.

Lightweight intent detection middleware for OpenCode fallback pipeline.
Transforms user input into structured intent with candidates, scores, and confidence.

This module is the fallback when Denis middleware is unavailable.
It provides:
- Keyword-based intent detection with scoring
- Multiple candidate generation
- Confidence-based gating (use "unknown" for low confidence)
- Full traceability (why each decision was made)
- WS debug events for observability in Denis Persona

Output Contract:
{
    "intent": { "pick": string, "confidence": float },
    "intent_candidates": [
        { "name": string, "score": float }
    ],
    "intent_trace": {
        "version": "makina_filter@X.Y.Z",
        "matched_rules": [string],
        "features": object,
        "reason": string
    },
    "constraints": [],
    "context_refs": [],
    "acceptance_criteria": [],
    "output_format": "text|json|code|markdown",
    "missing_inputs": []
}
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import logging
import hashlib
import urllib.request
import json

logger = logging.getLogger(__name__)

VERSION = "1.0.0"

LOW_CONFIDENCE_THRESHOLD = 0.55

INTENT_KEYWORDS = {
    "implement_feature": [
        "crea",
        "haz",
        "implementa",
        "añade",
        "desarrolla",
        "construye",
        "agrega",
        "nueva",
        "nuevo",
        "feature",
        "funcionalidad",
    ],
    "debug_repo": [
        "arregla",
        "debug",
        "depura",
        "error",
        "bug",
        "problema",
        "fallo",
        "issue",
        "fix",
        "solve",
        "troubleshoot",
    ],
    "refactor_migration": [
        "refactoriza",
        "migra",
        "migrar",
        "restructura",
        "reorganiza",
        "cleanup",
        "clean",
        "moderniza",
        "actualiza código",
    ],
    "run_tests_ci": [
        "test",
        "tests",
        "prueba",
        "pruebas",
        "ci",
        "run",
        "ejecuta",
        "verifica",
        "validar",
        "check",
    ],
    "explain_concept": [
        "explica",
        "qué es",
        "cómo funciona",
        "describe",
        "dime",
        "entiende",
        "understanding",
        "what is",
        "how does",
        "explain",
    ],
    "write_docs": [
        "documenta",
        "docs",
        "documentación",
        "readme",
        "manual",
        "especifica",
        "especificación",
        "comenta",
        "comentario",
    ],
    "design_architecture": [
        "diseña",
        "arquitectura",
        "estructura",
        "diseño",
        "plan",
        "architecture",
        "design",
        "blueprint",
        "schema",
    ],
    "toolchain_task": [
        "reindexa",
        "scrapea",
        "scrape",
        "scraping",
        "indexa",
        "build",
        "compila",
        "deploy",
        "despliega",
        "instala",
        "configura",
        "setup",
    ],
    "ops_health_check": [
        "health",
        "status",
        "salud",
        "estado",
        "monitor",
        "métricas",
        "metrics",
        "check",
        "verifica estado",
    ],
    "incident_triage": [
        "incidente",
        "emergency",
        "emergencia",
        "outage",
        "caída",
        "critical",
        "crítico",
        "alerta",
        "alert",
    ],
    "plan_rollout": [
        "despliegue",
        " rollout",
        "release",
        "lanzamiento",
        "deploy",
        "planifica",
        "plan",
        "strategy",
    ],
}

GREETING_PATTERNS = [
    r"^hola$",
    r"^hi$",
    r"^hey$",
    r"^hello$",
    r"^buenos días$",
    r"^buenas$",
    r"^qué tal$",
    r"^cómo estás$",
]

QUESTION_STARTERS = [
    "qué",
    "cómo",
    "cuándo",
    "dónde",
    "por qué",
    "cuál",
    "what",
    "how",
    "when",
    "where",
    "why",
    "which",
]


@dataclass
class IntentCandidate:
    """An intent candidate with score."""

    name: str
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "score": round(self.score, 3)}


@dataclass
class MakinaInput:
    """Input to the makina filter."""

    prompt: str
    context_refs: List[str] = field(default_factory=list)


@dataclass
class MakinaOutput:
    """Output from the makina filter matching the required contract."""

    intent: Dict[str, Any]
    intent_candidates: List[Dict[str, Any]]
    intent_trace: Dict[str, Any]
    constraints: List[Any]
    context_refs: List[str]
    acceptance_criteria: List[str]
    output_format: str
    missing_inputs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "intent_candidates": self.intent_candidates,
            "intent_trace": self.intent_trace,
            "constraints": self.constraints,
            "context_refs": self.context_refs,
            "acceptance_criteria": self.acceptance_criteria,
            "output_format": self.output_format,
            "missing_inputs": self.missing_inputs,
        }

    def __str__(self) -> str:
        """Compact string for OpenCode footer display."""
        intent = self.intent.get("pick", "unknown")
        conf = int(self.intent.get("confidence", 0) * 100)
        constraints = ",".join(self.constraints[:3]) if self.constraints else ""
        missing = f" ⚠ {self.missing_inputs[0]}" if self.missing_inputs else ""
        icon = "⚡" if conf >= 55 else "?"
        return f"{icon} {intent} {conf}%{(' · ' + constraints) if constraints else ''}{missing}"


def _is_greeting(prompt: str) -> bool:
    """Check if prompt is a greeting."""
    cleaned = prompt.strip().lower()
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, cleaned):
            return True
    return False


def _is_question(prompt: str) -> bool:
    """Check if prompt is a question."""
    cleaned = prompt.strip().lower()
    for starter in QUESTION_STARTERS:
        if cleaned.startswith(starter):
            return True
    if "?" in prompt:
        return True
    return False


def _extract_features(prompt: str) -> Dict[str, Any]:
    """Extract features from prompt for scoring."""
    features = {
        "length": len(prompt),
        "word_count": len(prompt.split()),
        "has_question": "?" in prompt,
        "has_code_block": "```" in prompt,
        "has_file_path": bool(re.search(r"[\w/]+\.\w+", prompt)),
        "has_command": bool(re.search(r"\$\s*\w+|\\\w+", prompt)),
        "is_question": _is_question(prompt),
        "is_greeting": _is_greeting(prompt),
        "has_urgent_words": any(
            w in prompt.lower() for w in ["urgent", "ahora", "ya", "inmediato", "emergency"]
        ),
    }
    return features


def _compute_keyword_scores(prompt: str) -> Dict[str, float]:
    """Compute intent scores based on keyword matching."""
    scores: Dict[str, float] = {}
    prompt_lower = prompt.lower()

    priority_keywords = {
        "crea": "implement_feature",
        "haz": "implement_feature",
        "implementa": "implement_feature",
        "añade": "implement_feature",
        "agrega": "implement_feature",
        "desarrolla": "implement_feature",
        "construye": "implement_feature",
        "arregla": "debug_repo",
        "debug": "debug_repo",
        "depura": "debug_repo",
        "fix": "debug_repo",
    }

    for intent_name, keywords in INTENT_KEYWORDS.items():
        score = 0.0
        matched_rules = []
        has_priority = False

        for keyword in keywords:
            if keyword in prompt_lower:
                score += 1.0
                matched_rules.append(f"keyword:{keyword}")

                if keyword in priority_keywords and priority_keywords[keyword] == intent_name:
                    score += 0.5
                    has_priority = True

        if score > 0:
            if has_priority:
                normalized = 1.0
            elif score >= 2:
                normalized = 1.0
            elif score >= 1:
                normalized = 0.7
            else:
                normalized = min(score / 2.0, 0.6)
            scores[intent_name] = normalized

    return scores


def _detect_output_format(prompt: str) -> str:
    """Detect expected output format from prompt."""
    prompt_lower = prompt.lower()

    if "json" in prompt_lower:
        return "json"
    if "código" in prompt_lower or "code" in prompt_lower or "```" in prompt:
        return "code"
    if "markdown" in prompt_lower or "md" in prompt_lower:
        return "markdown"

    return "text"


def _redact_for_logging(data: Any) -> Any:
    """Redact sensitive data from logs."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            redacted[key] = _redact_for_logging(value)
        return redacted
    elif isinstance(data, list):
        return [_redact_for_logging(item) for item in data]
    elif isinstance(data, str) and len(data) > 200:
        return data[:200] + "..."
    return data


def _emit_debug_event(
    intent: Dict[str, Any],
    intent_candidates: List[Dict[str, Any]],
    features: Dict[str, Any],
    reason: str,
) -> None:
    """Emit debug event to WS for Denis Persona observability."""
    if not os.getenv("MAKINA_FILTER_DEBUG", "0") == "1":
        return

    try:
        import json

        debug_data = {
            "intent": _redact_for_logging(intent),
            "intent_candidates": _redact_for_logging(intent_candidates),
            "features": _redact_for_logging(features),
            "reason": reason[:200] if reason else reason,
            "version": VERSION,
        }
        logger.debug(f"MAKINA_FILTER_DEBUG: {json.dumps(debug_data)}")
    except Exception as e:
        logger.warning(f"Failed to emit debug event: {e}")


LANGUAGE_CONSTRAINTS = {
    "python": ["python", "py", "django", "flask", "fastapi", "pydantic"],
    "typescript": ["typescript", "ts", "tsx", "react", "vue", "angular", "node"],
    "javascript": ["javascript", "js", "nodejs", "node"],
    "go": ["go", "golang"],
    "c": ["c", "c++", "cpp"],
    "rust": ["rust", "rs"],
    "java": ["java", "spring"],
    "kotlin": ["kotlin", "android"],
    "swift": ["swift", "ios"],
    "async": ["async", "await", "asyncio", "promise", "callback"],
    "testing": ["test", "pytest", "unittest", "jest", "vitest", "testing"],
    "performance": ["performance", "optimize", "speed", "benchmark", "profiler"],
    "security": ["security", "auth", "jwt", "oauth", "ssl", "tls", "encryption"],
    "containers": ["docker", "kubernetes", "k8s", "container", "pod"],
    "ci_cd": ["ci", "cd", "github actions", "gitlab", "jenkins", "pipeline"],
    "serverless": ["serverless", "lambda", "functions", "faas"],
    "caching": ["cache", "redis", "memcached", "lru"],
    "message_queue": ["queue", "rabbitmq", "kafka", "sqs", "pubsub"],
}


def _extract_constraints(prompt: str, context_refs: List[str]) -> List[str]:
    """Extract language/technology constraints from prompt and context refs."""
    constraints = []
    prompt_lower = prompt.lower()

    for lang, keywords in LANGUAGE_CONSTRAINTS.items():
        for keyword in keywords:
            if keyword in prompt_lower:
                if lang not in constraints:
                    constraints.append(lang)
                break

    for ref in context_refs:
        ref_lower = ref.lower()
        if ref.endswith(".py"):
            if "python" not in constraints:
                constraints.append("python")
        elif ref.endswith((".ts", ".tsx")):
            if "typescript" not in constraints:
                constraints.append("typescript")
        elif ref.endswith(".js"):
            if "javascript" not in constraints:
                constraints.append("javascript")
        elif ref.endswith(".go"):
            if "go" not in constraints:
                constraints.append("go")

    return constraints


ACCEPTANCE_CRITERIA_BY_INTENT = {
    "implement_feature": [
        "función o clase existe",
        "tests pasan",
        "no errores de importación",
    ],
    "debug_repo": [
        "error reproducible resuelto",
        "tests no regresionan",
    ],
    "run_tests_ci": [
        "todos los tests pasan",
        "coverage no baja",
    ],
    "refactor_migration": [
        "comportamiento idéntico",
        "tests pasan",
    ],
    "write_docs": [
        "README actualizado",
        "ejemplos de uso incluidos",
    ],
}


def _extract_acceptance_criteria(prompt: str, intent: str) -> List[str]:
    """Extract acceptance criteria based on intent and explicit mentions."""
    criteria = []

    if intent in ACCEPTANCE_CRITERIA_BY_INTENT:
        criteria.extend(ACCEPTANCE_CRITERIA_BY_INTENT[intent])

    prompt_lower = prompt.lower()
    if "test" in prompt_lower:
        if "tests pasan" not in criteria:
            criteria.append("tests pasan")
    if "funcion" in prompt_lower or "función" in prompt_lower:
        if "función o clase existe" not in criteria:
            criteria.append("función o clase existe")
    if "error" in prompt_lower or "errores" in prompt_lower:
        if "no errores de importación" not in criteria:
            criteria.append("no errores de importación")
    if "documenta" in prompt_lower or "docs" in prompt_lower:
        if "README actualizado" not in criteria:
            criteria.append("README actualizado")

    return criteria


def _detect_missing_inputs(prompt: str, intent: str, context_refs: List[str]) -> List[str]:
    """Detect missing inputs required for the given intent."""
    missing = []
    prompt_lower = prompt.lower()
    words = prompt.split()

    if len(words) < 5:
        missing.append("intent_unclear")

    if intent == "implement_feature":
        has_target = bool(
            re.search(r"(función|function|clase|class|endpoint|archivo|file)\s+\w+", prompt_lower)
        )
        if not has_target and not context_refs:
            missing.append("target_file")

    elif intent == "debug_repo":
        has_error = bool(re.search(r"(error|bug|exception|traceback|fallo)", prompt_lower))
        if not has_error and not context_refs:
            missing.append("error_details")

    elif intent == "design_architecture":
        has_system = bool(
            re.search(r"(sistema|arquitectura|estructura|design|schema)", prompt_lower)
        )
        if not has_system:
            missing.append("system_description")

    elif intent == "plan_rollout":
        has_env = bool(
            re.search(r"(producción|staging|prod|dev|entorno|environment)", prompt_lower)
        )
        if not has_env:
            missing.append("target_environment")

    elif intent == "toolchain_task":
        has_tool = bool(re.search(r"(comando|command|herramienta|tool|script)", prompt_lower))
        if not has_tool:
            missing.append("tool_or_command")

    return missing


def _report_to_control_plane(output: MakinaOutput, prompt_hash: str) -> None:
    """Report intent analysis to control plane asynchronously."""
    if os.getenv("MAKINA_FILTER_REPORT", "0") != "1":
        return

    try:
        import threading

        def _send_report():
            payload = {
                "intent": output.intent.get("pick"),
                "confidence": output.intent.get("confidence"),
                "constraints": output.constraints,
                "missing_inputs": output.missing_inputs,
                "acceptance_criteria": output.acceptance_criteria,
                "prompt_hash": prompt_hash,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "filter_version": VERSION,
            }

            try:
                req = urllib.request.Request(
                    "http://localhost:8084/api/makina/intent_report",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=0.1)
            except Exception:
                pass

        threading.Thread(target=_send_report, daemon=True).start()

    except Exception:
        pass


DO_NOT_TOUCH_PATHS = [
    "service_8084.py",
    "kernel/__init__.py",
    "FrontDenisACTUAL/public/",
]


def pre_execute_hook(prompt: str, context_refs: List[str]) -> Tuple[bool, MakinaOutput, str | None]:
    """
    Pre-execution hook that can BLOCK or ENRICH before executing.

    Returns:
        (should_proceed: bool, output: MakinaOutput, block_reason: str | None)
    """
    input_data = {"prompt": prompt, "context_refs": context_refs}
    output = filter_input(input_data)

    for protected in DO_NOT_TOUCH_PATHS:
        if protected in prompt:
            return (False, output, f"Operación bloqueada: archivo protegido ({protected})")

    for ref in context_refs:
        for protected in DO_NOT_TOUCH_PATHS:
            if protected in ref:
                return (False, output, f"Operación bloqueada: archivo protegido ({protected})")

    missing = output.missing_inputs
    confidence = output.intent.get("confidence", 0.0)

    if "intent_unclear" in missing and confidence < 0.4:
        return (False, output, f"Prompt demasiado ambiguo: {missing}")

    return (True, output, None)


def filter_input(input_data: MakinaInput | Dict[str, Any]) -> MakinaOutput:
    """
    Main entry point for makina filter.

    Transforms user input into structured intent with:
    - Primary intent + confidence
    - Multiple candidates with scores
    - Traceability info
    - Output format detection

    Args:
        input_data: Either MakinaInput object or dict with 'prompt' key

    Returns:
        MakinaOutput matching the required contract
    """
    try:
        if isinstance(input_data, dict):
            prompt = input_data.get("prompt", "")
            context_refs = input_data.get("context_refs", [])
        else:
            prompt = input_data.prompt
            context_refs = input_data.context_refs

        features = _extract_features(prompt)
        matched_rules: List[str] = []

        if features["is_greeting"]:
            intent_candidates = [
                IntentCandidate(name="greeting", score=1.0),
                IntentCandidate(name="unknown", score=0.0),
            ]
            reason = "greeting pattern matched"
            matched_rules.append("greeting_pattern")

        elif features["is_question"] and features["word_count"] < 5:
            intent_candidates = [
                IntentCandidate(name="explain_concept", score=0.8),
                IntentCandidate(name="unknown", score=0.3),
            ]
            reason = "short question detected"
            matched_rules.append("question_short")

        else:
            keyword_scores = _compute_keyword_scores(prompt)

            if not keyword_scores:
                intent_candidates = [
                    IntentCandidate(name="unknown", score=0.0),
                ]
                reason = "no keyword matches found"
                matched_rules.append("no_keywords")
            else:
                intent_candidates = [
                    IntentCandidate(name=k, score=v)
                    for k, v in sorted(keyword_scores.items(), key=lambda x: x[1], reverse=True)
                ]
                top_intent = intent_candidates[0].name
                reason = f"keyword match for {top_intent}"
                matched_rules.append(f"keyword:{top_intent}")

        intent_candidates.sort(key=lambda x: x.score, reverse=True)

        top_candidate = intent_candidates[0]
        confidence = top_candidate.score

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            final_intent = "unknown"
            reason = f"low confidence ({confidence:.2f} < {LOW_CONFIDENCE_THRESHOLD})"
            if "low_confidence" not in matched_rules:
                matched_rules.append("low_confidence_threshold")

            intent_candidates = [
                IntentCandidate(name="unknown", score=0.0),
            ]
            confidence = 0.0
        else:
            final_intent = top_candidate.name

        intent = {
            "pick": final_intent,
            "confidence": round(confidence, 3),
        }

        output_format = _detect_output_format(prompt)

        intent_trace = {
            "version": f"makina_filter@{VERSION}",
            "matched_rules": matched_rules,
            "features": features,
            "reason": reason,
        }

        _emit_debug_event(intent, [c.to_dict() for c in intent_candidates], features, reason)

        constraints = _extract_constraints(prompt, context_refs)
        acceptance_criteria = _extract_acceptance_criteria(prompt, final_intent)
        missing_inputs = _detect_missing_inputs(prompt, final_intent, context_refs)

        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]

        _report_to_control_plane(
            MakinaOutput(
                intent=intent,
                intent_candidates=[c.to_dict() for c in intent_candidates],
                intent_trace=intent_trace,
                constraints=constraints,
                context_refs=context_refs,
                acceptance_criteria=acceptance_criteria,
                output_format=output_format,
                missing_inputs=missing_inputs,
            ),
            prompt_hash,
        )

        return MakinaOutput(
            intent=intent,
            intent_candidates=[c.to_dict() for c in intent_candidates],
            intent_trace=intent_trace,
            constraints=constraints,
            context_refs=context_refs,
            acceptance_criteria=acceptance_criteria,
            output_format=output_format,
            missing_inputs=missing_inputs,
        )

    except Exception as e:
        logger.error(f"Makina filter error: {e}", exc_info=True)
        return _fail_open(
            prompt=str(input_data.get("prompt", "") if isinstance(input_data, dict) else "")
        )


def _fail_open(prompt: str) -> MakinaOutput:
    """Fail-open handler: return safe unknown intent on error."""
    return MakinaOutput(
        intent={"pick": "unknown", "confidence": 0.0},
        intent_candidates=[],
        intent_trace={
            "version": f"makina_filter@{VERSION}",
            "matched_rules": [],
            "features": {},
            "reason": "router_error",
        },
        constraints=[],
        context_refs=[],
        acceptance_criteria=[],
        output_format="text",
        missing_inputs=[],
    )


def filter_input_safe(input_data: MakinaInput | Dict[str, Any]) -> MakinaOutput:
    """
    Safe wrapper for filter_input with explicit fail-open.

    Use this when you want guaranteed fail-open behavior
    regardless of configuration.
    """
    try:
        return filter_input(input_data)
    except Exception as e:
        logger.error(f"Makina filter crashed: {e}", exc_info=True)
        prompt = ""
        if isinstance(input_data, dict):
            prompt = input_data.get("prompt", "")
        elif hasattr(input_data, "prompt"):
            prompt = input_data.prompt
        return _fail_open(prompt)


MAKINA_ONLY_MODE = os.getenv("OPENCODE_MAKINA_ONLY", "1") == "1"


def filter_with_compiler(input_data: MakinaInput | Dict[str, Any]) -> MakinaOutput:
    """
    Enhanced filter_input that uses the Compiler Service when available.

    This is the primary entry point when OPENCODE_MAKINA_ONLY=1 (default).
    It tries the LLM compiler first, then falls back to local makina_filter.

    The key difference from filter_input:
    - Returns makina_prompt (machine language) as the primary output
    - Uses OpenAI Chat for better intent detection when available
    - Falls back gracefully to local heuristics
    """
    import os

    if not MAKINA_ONLY_MODE:
        return filter_input(input_data)

    prompt = ""
    context_refs = []

    if isinstance(input_data, dict):
        prompt = input_data.get("prompt", "")
        context_refs = input_data.get("context_refs", [])
    elif hasattr(input_data, "prompt"):
        prompt = input_data.prompt
        context_refs = getattr(input_data, "context_refs", [])

    anti_loop = os.getenv("X_DENIS_HOP", "") != ""

    try:
        from denis_unified_v1.inference.compiler_client import compile_with_fallback_sync

        result = compile_with_fallback_sync(
            input_text=prompt,
            anti_loop=anti_loop,
        )

        intent_pick = result.router.get("pick", "unknown")
        constraints = _extract_constraints(prompt, context_refs)
        acceptance_criteria = _extract_acceptance_criteria(prompt, intent_pick)
        missing_inputs = _detect_missing_inputs(prompt, intent_pick, context_refs)

        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]

        output = MakinaOutput(
            intent={
                "pick": intent_pick,
                "confidence": result.router.get("confidence", 0.0),
            },
            intent_candidates=result.router.get("candidates", []),
            intent_trace={
                "version": f"makina_filter@{VERSION}",
                "matched_rules": [f"compiler:{result.metadata.get('compiler', 'unknown')}"],
                "features": {"used_remote": result.used_remote},
                "reason": f"compiler_mode, remote={result.used_remote}",
            },
            constraints=constraints,
            context_refs=context_refs,
            acceptance_criteria=acceptance_criteria,
            output_format="text",
            missing_inputs=missing_inputs,
        )

        _report_to_control_plane(output, prompt_hash)

        return output

    except Exception as e:
        logger.warning(f"Compiler client failed: {e}, using local filter")
        return filter_input(input_data)
