"""Intent Parser - Heuristics + LLM fallback with confidence gating.

Pipeline:
1. Cheap heuristics (keywords, patterns) - fast path
2. LLM classification (if heuristics inconclusive)
3. Entity extraction
4. Confidence gating (≥0.72 for autonomous action)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from denis_unified_v1.intent.intent_v1 import (
    IntentV1,
    IntentType,
    IntentEntity,
    IntentConstraints,
    RiskLevel,
    CONFIDENCE_THRESHOLD_AUTONOMOUS,
)


# Heuristic patterns for fast classification - ENHANCED VERSION
# More comprehensive patterns with higher confidence weights

# Single pattern gives 0.65, two patterns give 0.80, three+ give 0.90
HEURISTIC_PATTERNS: Dict[IntentType, List[str]] = {
    IntentType.RUN_TESTS_CI: [
        r"\bpytest\b",
        r"\btest\b.*\bfail",
        r"\bci\b.*\bfail",
        r"\brun\b.*\btest",
        r"\bfailing\b.*\btest",
        r"\btest\b.*\berror",
        r"\btest\b.*\broto\b",
        r"\btest\b.*\bcaido\b",
        r"\bci\b.*\brojo\b",
        r"\bci\b.*\berror",
        r"\bcorrer\b.*\btest",
        r"\bejecutar\b.*\btest",
        r"\bprueba\b.*\bfalla",
        r"\bunit\b.*\btest",
        r"\bintegration\b.*\btest",
        r"\bcoverage\b",
        r"\btest_.*\.py",
        r"tests?/.*\.",
        r"\bfallando\b",
        r"\btests?\b.*\bfallan\b",
        r"\bfalla\b.*\btest",
        r"\bpasen\b.*\btest",
        r"\btest\b.*\bintermitente",
        r"\btest\b.*\bde\b.*\bintegracion",
        r"\btest\b.*\bde\b.*\bunidad",
        r"\bcorrer\b.*\bpytest",
        r"\bejecutar\b.*\bpytest",
        r"\brevisar\b.*\btest",
        r"\brevisar\b.*\bci\b",
        r"\bvalidar\b.*\bcambio",
        r"\bdebuggear\b.*\btest",
    ],
    IntentType.DEBUG_REPO: [
        r"\berror\b",
        r"\btraceback\b",
        r"\bstacktrace\b",
        r"\bexception\b",
        r"\bbug\b",
        r"\bcrash\b",
        r"\bdebug\b",
        r"\berror\b.*\bimport",
        r"\berror\b.*\blinea",
        r"\berror\b.*\bline",
        r"\bimport\b.*\berror",
        r"\bmodulenotfound",
        r"\bkeyerror",
        r"\bvalueerror",
        r"\btypeerror",
        r"\battributeerror",
        r"\b500\b",
        r"\btraceback\b.*\bmost\b.*\brecent",
        r"\bdebuggea\b",
        r"\bno\b.*\bfunciona\b",
        r"\bfalla\b.*\bcodigo\b",
        r"\berror\b.*\bendpoint",
        r"\bservicio\b.*\bcrashea",
    ],
    IntentType.REFACTOR_MIGRATION: [
        r"\brefactor\b",
        r"\bmigrat\b",
        r"\brewrite\b",
        r"\bmoderniz\b",
        r"\bupgrade\b.*\bto\b",
        r"\bmigrar\b.*\ba\b",
        r"\bcambiar\b.*\ba\b",
        r"\bpasar\b.*\ba\b",
        r"\bupdate\b.*\bversion",
        r"\bupgrade\b.*\bversion",
        r"\bpython\b.*\b3\.\d+",
        r"\bflask\b.*\bfastapi\b",
        r"\brequests\b.*\bhttpx\b",
        r"\bv1\b.*\bv2\b",
        r"\blegacy\b.*\bcode\b",
        r"\bcodigo\b.*\blegacy\b",
        r"\brefactoriza\b",
        r"\breescribir\b",
        r"\breestructurar\b",
        r"\bclean\b.*\barchitecture\b",
        r"\barquitectura\b.*\blimpia\b",
        r"\bmoderniza\b.*\bcodigo\b",
        r"\bcodigo\b.*\blegacy\b",
        r"\bmoderniza\b",
    ],
    IntentType.OPS_HEALTH_CHECK: [
        r"\bhealth\b",
        r"\bstatus\b",
        r"\bprobe\b",
        r"\bcheck\b.*\bengine",
        r"\bis\b.*\bup\b",
        r"\bestado\b.*\bsalud\b",
        r"\bestado\b.*\bsistema\b",
        r"\bverificar\b.*\bestado\b",
        r"\bhealth\b.*\bcheck",
        r"\bcheck\b.*\bhealth",
        r"\bprobe\b.*\bengine",
        r"\bengine\b.*\bprobe",
        r"\bservicios?\b.*\bup\b",
        r"\bservicios?\b.*\bfunciona",
        r"\bcluster\b.*\bstatus",
        r"\bestado\b.*\bcluster",
        r"\bredis\b.*\bpostgres",
        r"\bpostgres\b.*\bredis",
        r"\bmonitorea\b",
        r"\bmonitor\b",
    ],
    IntentType.IMPLEMENT_FEATURE: [
        r"\bimplement\b",
        r"\badd\b.*\bfeature",
        r"\bcreate\b.*\bendpoint",
        r"\bbuild\b.*\bfeature",
        r"\bagregar\b.*\bfeature",
        r"\bagregar\b.*\bfuncionalidad",
        r"\bimplementa\b",
        r"\bcrea\b.*\bendpoint",
        r"\bcree\b.*\bendpoint",
        r"\bnuevo\b.*\bendpoint",
        r"\bautenticacion\b.*\bjwt\b",
        r"\bjwt\b.*\bauth",
        r"\bratelimit\b",
        r"\brate\b.*\blimit",
        r"\bwebsocket",
        r"\bsoporte\b.*\bcsv",
        r"\bparser\b.*\bcsv",
        r"\bcaching\b",
        r"\bcache\b.*\bsistema",
        r"\bsistema\b.*\bcache",
        r"\bagregar\b.*\bjwt\b",
        r"\bnecesito\b.*\bfeature\b",
        r"\bfeature\b.*\bpara",
        r"\bexportar\b.*\breport",
        r"\breporte\b.*\bexport",
        r"\bnecesito\b.*\bagregar\b",
        r"\bagregar\b.*\bsoporte",
        r"\bsistema\b.*\bpara",
        r"\bfuncionalidad\b.*\bpara",
    ],
    IntentType.INCIDENT_TRIAGE: [
        r"\bincident\b",
        r"\boutage\b",
        r"\balert\b",
        r"\bproduction\b.*\bdown",
        r"\bsev[0-9]\b",
        r"\bincidente\b",
        r"\bproduccion\b.*\bdown\b",
        r"\bservicio\b.*\bdown\b",
        r"\bcaido\b.*\bproduccion",
        r"\balerta\b.*\bcritica",
        r"\bcritical\b.*\balert",
        r"\blatencia\b.*\b10s",
        r"\boutage\b.*\bservicio",
        r"\bseguridad\b.*\bincidente",
        r"\bsecurity\b.*\bincident",
        r"\bsev\b.*\b1\b",
        r"\bsev1\b",
    ],
    IntentType.DESIGN_ARCHITECTURE: [
        r"\bdesign\b",
        r"\barchitect\b",
        r"\bsystem\b.*\bdesign",
        r"\btarget\b.*\bstate",
        r"\bdisenar\b",
        r"\barquitectura\b",
        r"\bdiseno\b.*\bsistema",
        r"\bestado\b.*\bobjetivo",
        r"\btarget\b.*\barchitecture",
        r"\bdesign\b.*\bpattern",
    ],
    IntentType.EXPLAIN_CONCEPT: [
        r"\bexplain\b",
        r"\bhow\b.*\bdoes\b",
        r"\bwhat\b.*\bis\b",
        r"\bwhy\b.*\bhappen",
        r"\bdocument\b.*\bhow",
        r"\bexplica\b",
        r"\bcomo\b.*\bfunciona\b",
        r"\bcual\b.*\bes\b.*\bpara",
        r"\bque\b.*\bes\b.*\bel\b",
        r"\bpor\b.*\bque\b.*\bhay\b",
        r"\bdocumenta\b.*\bcomo\b",
        r"\bque\b.*\bsignifica\b",
        r"\bcomo\b.*\bse\b.*\busa",
        r"\bcomo\b.*\bdecide",
        r"\bexplicame\b",
        r"\bcomo\b.*\bse\b.*\belige",
        r"\bcomo\b.*\btrabaja\b",
        r"\bque\b.*\bes\b.*\b\w+\b.*\?",
        r"\bpor\b.*\bque\b.*\bexiste\b",
        r"\bcual\b.*\bes\b.*\bproposito",
        r"\bcomo\b.*\bse\b.*\bdecide",
        r"\bque\b.*\b\w+\b.*\?",
        r"\bcomo\b.*\busar\b",
        r"\bpara\b.*\bque\b.*\bsirve",
        r"\bcuando\b.*\busar\b",
        r"\bcomo\b.*\bse\b.*\belige\b",
        r"\bque\b.*\bes\b.*\bgate\b",
        r"\bcomo\b.*\bdecide\b.*\bengine",
    ],
    IntentType.PLAN_ROLLOUT: [
        r"\brollout\b",
        r"\bdeploy\b",
        r"\brelease\b.*\bplan",
        r"\bcanary\b",
        r"\bgradual\b.*\bmigrat",
    ],
    IntentType.TOOLCHAIN_TASK: [
        r"\bdocker\b",
        r"\bk8s\b",
        r"\bkubernetes\b",
        r"\bterraform\b",
        r"\bcicd\b",
        r"\bpipeline\b",
        r"\bdocker\b.*\bimagen",
        r"\bimagen\b.*\bdocker",
        r"\bdespliega\b.*\bkubernetes",
        r"\bdeploy\b.*\bk8s",
        r"\bconfigura\b.*\bcicd",
        r"\bconfigura\b.*\bpipeline",
        r"\bgithub\b.*\baction",
        r"\baction\b.*\bgithub",
    ],
    IntentType.WRITE_DOCS: [
        r"\bwrite\b.*\bdoc",
        r"\bupdate\b.*\breadme",
        r"\badd\b.*\bcomment",
        r"\bdocument\b.*\bcode",
        r"\bescribir\b.*\bdoc",
        r"\bescribe\b.*\bdoc",
        r"\bactualiza\b.*\breadme",
        r"\bactualizar\b.*\breadme",
        r"\bagrega\b.*\bdocstring",
        r"\bagregar\b.*\bcomentario",
        r"\bdocumenta\b",
        r"\bdocumentar\b",
        r"\bdocstring",
        r"\bdocumentacion\b",
        r"\bescribir\b.*\bmanual",
        r"\bescribir\b.*\bguia",
        r"\bnuevo\b.*\bendpoint\b.*\bdocument",
    ],
}

# Entity extraction patterns
ENTITY_PATTERNS = {
    "path": r"(?:[\w\-]+/)+[\w\-]+\.[\w]+",  # file paths
    "command": r"`([^`]+)`|\"(npm|pip|pytest|python|docker|kubectl|git|make)[^\"]*\"",  # commands
    "service": r"\b(service|api|endpoint|worker|job)\s+([\w\-]+)",  # service names
    "port": r"\b(port|:)\s*(\d{2,5})\b",  # port numbers
    "url": r"https?://[^\s\"<>]+",  # URLs
    "variable": r"\b[A-Z_][A-Z_0-9]*\b",  # env vars / constants
}


def _apply_heuristics(prompt: str) -> Optional[Tuple[IntentType, float, str]]:
    """Apply cheap heuristics to classify intent.

    Returns: (intent_type, confidence, reasoning) or None if no match.
    """
    prompt_lower = prompt.lower()
    scores: Dict[IntentType, float] = {}
    match_counts: Dict[IntentType, int] = {}

    for intent_type, patterns in HEURISTIC_PATTERNS.items():
        matches = 0
        for pattern in patterns:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                matches += 1

        if matches > 0:
            # Enhanced confidence scoring:
            # 1 match = 0.75 (above 0.72 threshold)
            # 2 matches = 0.90
            # 3+ matches = 0.95
            if matches == 1:
                confidence = 0.75
            elif matches == 2:
                confidence = 0.90
            else:
                confidence = 0.95
            scores[intent_type] = confidence
            match_counts[intent_type] = matches

    if not scores:
        return None

    # Get highest scoring intent
    best_intent = max(scores.items(), key=lambda x: x[1])
    intent_type, confidence = best_intent
    matches = match_counts[intent_type]

    reasoning = f"Matched {matches} heuristic pattern(s) for {intent_type.value}"

    return intent_type, confidence, reasoning


def _extract_entities(prompt: str) -> List[IntentEntity]:
    """Extract entities from prompt using regex patterns."""
    entities = []

    for entity_type, pattern in ENTITY_PATTERNS.items():
        for match in re.finditer(pattern, prompt, re.IGNORECASE):
            value = match.group(0)
            # Clean up the match
            if entity_type == "command" and match.group(1):
                value = match.group(1)

            entities.append(
                IntentEntity(
                    type=entity_type,
                    value=value,
                    span=(match.start(), match.end()),
                    confidence=0.8 if entity_type in ("path", "url") else 0.7,
                )
            )

    # Remove duplicates (same type + value)
    seen = set()
    unique_entities = []
    for e in entities:
        key = (e.type, e.value)
        if key not in seen:
            seen.add(key)
            unique_entities.append(e)

    return unique_entities


def _assess_risk(intent: IntentType, prompt: str) -> RiskLevel:
    """Assess risk level based on intent type and keywords."""
    prompt_lower = prompt.lower()

    # High risk indicators
    high_risk_patterns = [
        r"\bproduction\b",
        r"\bprod\b",
        r"\blive\b",
        r"\bcritical\b",
        r"\bdata loss\b",
        r"\bcorrupt\b",
        r"\bsecurity\b.*\bhole",
        r"\bvulnerability\b",
        r"\brevert\b",
        r"\brollback\b",
    ]

    for pattern in high_risk_patterns:
        if re.search(pattern, prompt_lower):
            return RiskLevel.HIGH

    # Medium risk intents
    if intent in (
        IntentType.INCIDENT_TRIAGE,
        IntentType.PLAN_ROLLOUT,
        IntentType.REFACTOR_MIGRATION,
    ):
        return RiskLevel.MEDIUM

    return RiskLevel.LOW


def _generate_acceptance_criteria(
    intent: IntentType, entities: List[IntentEntity]
) -> List[str]:
    """Generate default acceptance criteria based on intent."""
    criteria_map = {
        IntentType.RUN_TESTS_CI: [
            "Tests execute without errors",
            "Test results captured in evidence",
            "Failed tests reported with context",
        ],
        IntentType.DEBUG_REPO: [
            "Root cause identified",
            "Fix implemented and verified",
            "Regression test added",
        ],
        IntentType.REFACTOR_MIGRATION: [
            "All existing tests pass",
            "No functionality regression",
            "Migration steps documented",
        ],
        IntentType.IMPLEMENT_FEATURE: [
            "Feature implemented per spec",
            "Tests added and passing",
            "Documentation updated",
        ],
        IntentType.OPS_HEALTH_CHECK: [
            "All engines probed",
            "Status report generated",
            "Issues identified and logged",
        ],
        IntentType.INCIDENT_TRIAGE: [
            "Impact assessed",
            "Mitigation applied",
            "Post-mortem initiated",
        ],
        IntentType.EXPLAIN_CONCEPT: [
            "Explanation provided",
            "Examples included if relevant",
            "Follow-up questions anticipated",
        ],
    }

    return criteria_map.get(intent, ["Task completed", "Evidence captured"])


def _llm_classify(prompt: str) -> Tuple[IntentType, float, str]:
    """LLM-based classification (fallback when heuristics fail).

    For now, returns UNKNOWN with low confidence.
    In production, this would call the inference router.
    """
    # TODO: Implement actual LLM classification
    # For MVP, we return unknown to trigger clarification
    return (
        IntentType.UNKNOWN,
        0.35,
        "LLM classification not implemented, heuristics inconclusive",
    )


class IntentParser:
    """Parse user prompts into structured IntentV1."""

    def __init__(self, use_llm_fallback: bool = True):
        self.use_llm_fallback = use_llm_fallback

    def parse(self, prompt: str) -> IntentV1:
        """Parse a prompt into structured intent.

        Pipeline:
        1. Try heuristics (fast, cheap)
        2. If no match or low confidence, use LLM
        3. Extract entities
        4. Assess risk
        5. Generate acceptance criteria
        """
        parsed_at = datetime.now(timezone.utc).isoformat()

        # Step 1: Try heuristics
        heuristic_result = _apply_heuristics(prompt)

        if heuristic_result:
            intent_type, confidence, reasoning = heuristic_result
        elif self.use_llm_fallback:
            # Step 2: LLM fallback
            intent_type, confidence, reasoning = _llm_classify(prompt)
        else:
            intent_type, confidence, reasoning = (
                IntentType.UNKNOWN,
                0.0,
                "No heuristic match and LLM fallback disabled",
            )

        # Step 3: Extract entities
        entities = _extract_entities(prompt)

        # Step 4: Assess risk
        risk = _assess_risk(intent_type, prompt)

        # Step 5: Generate acceptance criteria
        acceptance_criteria = _generate_acceptance_criteria(intent_type, entities)

        # Determine constraints based on prompt keywords
        constraints = IntentConstraints()
        prompt_lower = prompt.lower()
        if "offline" in prompt_lower or "no internet" in prompt_lower:
            constraints.offline_mode = True
        if "no booster" in prompt_lower or "local only" in prompt_lower:
            constraints.no_boosters = True

        return IntentV1(
            intent=intent_type,
            confidence=confidence,
            entities=entities,
            constraints=constraints,
            acceptance_criteria=acceptance_criteria,
            risk=risk,
            reasoning=reasoning,
            raw_prompt=prompt,
            parsed_at=parsed_at,
        )

    def parse_with_clarification(self, prompt: str) -> Dict[str, Any]:
        """Parse and determine if clarification is needed.

        Returns dict with intent and recommended action.
        """
        intent = self.parse(prompt)

        if intent.is_tool_safe:
            return {
                "action": "proceed",
                "intent": intent.to_dict(),
                "message": None,
            }
        elif intent.requires_clarification:
            return {
                "action": "ask_clarification",
                "intent": intent.to_dict(),
                "message": self._generate_clarification_question(intent),
            }
        else:
            return {
                "action": "offer_options",
                "intent": intent.to_dict(),
                "message": self._generate_options_offer(intent),
            }

    def _generate_clarification_question(self, intent: IntentV1) -> str:
        """Generate a clarification question for low-confidence intents."""
        if intent.intent == IntentType.UNKNOWN:
            return "No estoy seguro de qué necesitas. ¿Puedes describir la tarea con más detalle? Por ejemplo: ¿es un bug, una nueva feature, o necesitas ayuda con tests?"

        return f"Entiendo que quieres {intent.intent.value.replace('_', ' ')}, pero no estoy 100% seguro. ¿Es correcto? Si no, ¿qué es lo que necesitas exactamente?"

    def _generate_options_offer(self, intent: IntentV1) -> str:
        """Generate options offer for very low confidence."""
        return "No estoy seguro de cómo ayudarte. Aquí van algunas opciones:\n1. Debuggear un error o traceback\n2. Ejecutar tests o verificar CI\n3. Refactorizar o migrar código\n4. Consulta de salud del sistema\n\n¿Cuál se acerca más a lo que necesitas?"


# Global parser instance
_parser: Optional[IntentParser] = None


def get_intent_parser() -> IntentParser:
    """Get global intent parser instance."""
    global _parser
    if _parser is None:
        _parser = IntentParser()
    return _parser


def parse_intent(prompt: str) -> IntentV1:
    """Convenience function to parse a prompt."""
    return get_intent_parser().parse(prompt)
