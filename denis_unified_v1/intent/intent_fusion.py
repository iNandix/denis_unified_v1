"""Intent Fusion and Gating - S3 Merge Stage.

Fuses S0 (heuristics), S1 (Rasa), S2 (Meta-LLM) into final IntentV1.
Applies confidence bands and gating rules.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

from denis_unified_v1.intent.intent_v1 import (
    IntentV1,
    IntentType,
    IntentConstraints,
    IntentEntity,
    ToneType,
    RiskLevel,
    SourceInfo,
    ConfidenceSource,
    ReasonCode,
    CONFIDENCE_THRESHOLD_HIGH,
    CONFIDENCE_THRESHOLD_MEDIUM,
    DISAMBIGUATION_TEMPLATES,
)
from denis_unified_v1.intent.entity_extractors import extract_entities
from denis_unified_v1.intent.rasa_adapter import parse_with_rasa
from denis_unified_v1.intent.meta_intent_llm import detect_meta_intent


_EXTERNAL_INTENT_MAP = {
    "tech_question": IntentType.EXPLAIN_CONCEPT,
    "code_question": IntentType.EXPLAIN_CONCEPT,
    "help": IntentType.EXPLAIN_CONCEPT,
    "question": IntentType.EXPLAIN_CONCEPT,
    "greeting": IntentType.UNKNOWN,
    "chitchat": IntentType.UNKNOWN,
    "greet": IntentType.UNKNOWN,
    "hello": IntentType.UNKNOWN,
    "hi": IntentType.UNKNOWN,
    "run_tests": IntentType.RUN_TESTS_CI,
    "test": IntentType.RUN_TESTS_CI,
    "testing": IntentType.RUN_TESTS_CI,
    "debug": IntentType.DEBUG_REPO,
    "error": IntentType.DEBUG_REPO,
    "bug": IntentType.DEBUG_REPO,
    "refactor": IntentType.REFACTOR_MIGRATION,
    "migrate": IntentType.REFACTOR_MIGRATION,
    "migration": IntentType.REFACTOR_MIGRATION,
    "implement": IntentType.IMPLEMENT_FEATURE,
    "feature": IntentType.IMPLEMENT_FEATURE,
    "health": IntentType.OPS_HEALTH_CHECK,
    "status": IntentType.OPS_HEALTH_CHECK,
    "incident": IntentType.INCIDENT_TRIAGE,
    "outage": IntentType.INCIDENT_TRIAGE,
    "design": IntentType.DESIGN_ARCHITECTURE,
    "architecture": IntentType.DESIGN_ARCHITECTURE,
    "explain": IntentType.EXPLAIN_CONCEPT,
    "rollout": IntentType.PLAN_ROLLOUT,
    "deploy": IntentType.PLAN_ROLLOUT,
    "docker": IntentType.TOOLCHAIN_TASK,
    "k8s": IntentType.TOOLCHAIN_TASK,
    "pipeline": IntentType.TOOLCHAIN_TASK,
    "docs": IntentType.WRITE_DOCS,
    "documentation": IntentType.WRITE_DOCS,
}


def _safe_intent_type(intent_str: str | None) -> IntentType | None:
    """Safely convert an intent string to IntentType."""
    if not intent_str:
        return None
    try:
        return IntentType(intent_str)
    except ValueError:
        return _EXTERNAL_INTENT_MAP.get(intent_str.lower(), None)


class IntentFusionEngine:
    """Fuses multiple intent sources and applies confidence gating."""

    def __init__(self):
        self.threshold_high = float(os.getenv("DENIS_INTENT_THRESHOLD_HIGH", "0.85"))
        self.threshold_medium = float(os.getenv("DENIS_INTENT_THRESHOLD", "0.72"))
        self.threshold_low = 0.50

    def fuse(
        self,
        prompt: str,
        rasa_result: Optional[Dict],
        heuristic_result: Optional[Dict],
        meta_result: Optional[Dict],
    ) -> IntentV1:
        """Fuse multiple sources into final IntentV1.

        Merge rules:
        1. If rasa_conf >= 0.85 and intent core -> use Rasa (unless meta strongly disagrees)
        2. If meta_conf >= 0.80 and rasa_conf < 0.85 -> use Meta
        3. If heur_conf >= 0.90 -> use Heuristics (unless conflict)
        4. If conflict between sources -> penalize confidence
        5. Entities: rasa > heuristics > meta
        6. Tone: meta if available, else neutral
        """
        sources: Dict[str, SourceInfo] = {}
        reason_codes: List[ReasonCode] = []

        rasa_info = self._extract_rasa_info(rasa_result)
        heur_info = self._extract_heuristic_info(heuristic_result)
        meta_info = self._extract_meta_info(meta_result)

        if rasa_info:
            sources["rasa"] = SourceInfo(
                source=ConfidenceSource.RASA,
                intent=rasa_info.get("intent"),
                confidence=rasa_info.get("confidence", 0.0),
                status=rasa_info.get("status", "ok"),
            )
        if heur_info:
            sources["heuristics"] = SourceInfo(
                source=ConfidenceSource.HEURISTICS,
                intent=heur_info.get("intent"),
                confidence=heur_info.get("confidence", 0.0),
                status="ok",
            )
        if meta_info:
            sources["meta_llm"] = SourceInfo(
                source=ConfidenceSource.META_LLM,
                intent=meta_info.get("intent"),
                confidence=meta_info.get("confidence", 0.0),
                status="ok",
            )

        primary_intent, confidence, merge_reason = self._apply_merge_rules(
            rasa_info, heur_info, meta_info, reason_codes
        )

        entities = self._merge_entities(rasa_info, heur_info, meta_info)
        tone = self._determine_tone(meta_info)
        secondary_intents = self._get_secondary_intents(
            meta_info, heur_info, primary_intent
        )
        implicit = meta_info.get("implicit", False) if meta_info else False
        user_goal = meta_info.get("user_goal", "") if meta_info else ""
        risk = self._assess_risk(primary_intent, prompt, tone)
        acceptance = self._generate_acceptance_criteria(primary_intent, entities)
        constraints = self._determine_constraints(prompt)

        parsed_at = datetime.now(timezone.utc).isoformat()

        intent_v1 = IntentV1(
            intent=primary_intent,
            confidence=confidence,
            confidence_band=self._get_confidence_band(confidence),
            entities=entities,
            constraints=constraints,
            acceptance_criteria=acceptance,
            risk=risk,
            tone=tone,
            secondary_intents=secondary_intents,
            implicit_request=implicit,
            user_goal=user_goal,
            sources=sources,
            reason_codes=reason_codes,
            reasoning=merge_reason,
            raw_prompt=prompt,
            parsed_at=parsed_at,
        )

        self._apply_clarification_logic(intent_v1)

        return intent_v1

    def _extract_rasa_info(self, result: Optional[Dict]) -> Optional[Dict]:
        if not result or result.get("status") == "unavailable":
            return None
        intent = result.get("intent")
        if not intent:
            return None
        converted = _safe_intent_type(intent)
        return {
            "intent": converted.value if converted else intent,
            "confidence": result.get("confidence", 0.0),
            "entities": result.get("entities", {}),
            "status": result.get("status", "ok"),
        }

    def _extract_heuristic_info(self, result: Optional[Dict]) -> Optional[Dict]:
        if not result:
            return None
        intent = result.get("intent")
        if not intent:
            return None
        return {
            "intent": intent,
            "confidence": result.get("confidence", 0.0),
            "reasoning": result.get("reasoning", ""),
        }

    def _extract_meta_info(self, result: Optional[Dict]) -> Optional[Dict]:
        if not result or result.get("status") == "skipped":
            return None
        meta = result.get("meta_intent")
        if not meta:
            return None
        return {
            "intent": meta.primary_intent.value
            if hasattr(meta.primary_intent, "value")
            else str(meta.primary_intent),
            "confidence": meta.confidence,
            "entities": meta.entities,
            "tone": meta.tone.value if hasattr(meta.tone, "value") else str(meta.tone),
            "implicit": meta.implicit_request,
            "user_goal": meta.user_goal,
            "secondary": [
                i.value if hasattr(i, "value") else str(i)
                for i in meta.secondary_intents
            ],
        }

    def _apply_merge_rules(
        self,
        rasa: Optional[Dict],
        heur: Optional[Dict],
        meta: Optional[Dict],
        reason_codes: List[ReasonCode],
    ) -> Tuple[IntentType, float, str]:
        rasa_conf = rasa.get("confidence", 0.0) if rasa else 0.0
        heur_conf = heur.get("confidence", 0.0) if heur else 0.0
        meta_conf = meta.get("confidence", 0.0) if meta else 0.0

        rasa_intent = rasa.get("intent") if rasa else None
        heur_intent = heur.get("intent") if heur else None
        meta_intent = meta.get("intent") if meta else None

        if rasa_conf >= self.threshold_high and rasa_intent:
            converted = _safe_intent_type(rasa_intent)
            if not converted:
                reason_codes.append(ReasonCode.DEFAULT_FALLBACK)
                return (
                    IntentType.UNKNOWN,
                    rasa_conf,
                    f"Rasa intent {rasa_intent} not recognized",
                )
            rasa_intent = converted.value
            if meta_conf >= 0.85 and meta_intent and meta_intent != rasa_intent:
                reason_codes.append(ReasonCode.INTENT_CONFLICT_RESOLVED)
                return (
                    IntentType(rasa_intent),
                    rasa_conf - 0.15,
                    "Rasa high conf but meta disagrees (penalized)",
                )
            reason_codes.append(ReasonCode.RASA_WINS_HIGH_CONFIDENCE)
            return IntentType(rasa_intent), rasa_conf, "Rasa high confidence"

        if meta_conf >= 0.80 and meta_intent and rasa_conf < self.threshold_high:
            meta_converted = _safe_intent_type(meta_intent)
            if meta_converted:
                reason_codes.append(ReasonCode.META_WINS_RASA_LOW)
                return meta_converted, meta_conf, "Meta high confidence, Rasa low"
            reason_codes.append(ReasonCode.DEFAULT_FALLBACK)
            return (
                IntentType.UNKNOWN,
                meta_conf,
                f"Meta intent {meta_intent} not recognized",
            )

        if heur_conf >= 0.90 and heur_intent:
            if rasa_conf >= 0.75 and rasa_intent:
                rasa_converted = _safe_intent_type(rasa_intent)
                if rasa_converted:
                    reason_codes.append(ReasonCode.INTENT_CONFLICT_RESOLVED)
                    return (
                        rasa_converted,
                        rasa_conf,
                        "Heuristics high but Rasa decent, prefer Rasa",
                    )
            reason_codes.append(ReasonCode.HEURISTICS_WINS_ALL_LOW)
            return IntentType(heur_intent), heur_conf, "Heuristics high confidence"

        candidates = []
        if rasa_intent and rasa_conf > 0:
            converted = _safe_intent_type(rasa_intent)
            if converted:
                candidates.append((converted, rasa_conf, "Rasa"))
        if meta_intent and meta_conf > 0:
            converted = _safe_intent_type(meta_intent)
            if converted:
                candidates.append((converted, meta_conf, "Meta"))
        if heur_intent and heur_conf > 0:
            converted = _safe_intent_type(heur_intent)
            if converted:
                candidates.append((converted, heur_conf, "Heuristics"))

        if candidates:
            best = max(candidates, key=lambda x: x[1])
            reason_codes.append(ReasonCode.DEFAULT_FALLBACK)
            return best[0], best[1], f"Best available: {best[2]}"

        reason_codes.append(ReasonCode.DEFAULT_FALLBACK)
        return IntentType.UNKNOWN, 0.0, "No valid sources"

    def _merge_entities(
        self, rasa: Optional[Dict], heur: Optional[Dict], meta: Optional[Dict]
    ) -> List[IntentEntity]:
        all_entities = []
        seen = set()

        if rasa and rasa.get("entities"):
            for name, values in rasa["entities"].items():
                for val in values if isinstance(values, list) else [values]:
                    key = (name, str(val).lower())
                    if key not in seen:
                        seen.add(key)
                        all_entities.append(
                            IntentEntity(
                                type=name,
                                value=str(val),
                                confidence=0.9,
                                source=ConfidenceSource.RASA,
                            )
                        )

        if meta and meta.get("entities"):
            for ent in meta["entities"]:
                key = (ent.type, ent.value.lower())
                if key not in seen:
                    seen.add(key)
                    all_entities.append(ent)

        return all_entities

    def _determine_tone(self, meta: Optional[Dict]) -> ToneType:
        if meta and meta.get("tone"):
            try:
                return ToneType(meta["tone"])
            except ValueError:
                pass
        return ToneType.NEUTRAL

    def _get_secondary_intents(
        self, meta: Optional[Dict], heur: Optional[Dict], primary: IntentType
    ) -> List[IntentType]:
        secondaries = []

        if meta and meta.get("secondary"):
            for intent_str in meta["secondary"]:
                converted = _safe_intent_type(intent_str)
                if converted and converted != primary:
                    secondaries.append(converted)

        return secondaries[:2]

    def _assess_risk(
        self, intent: IntentType, prompt: str, tone: ToneType
    ) -> RiskLevel:
        prompt_lower = prompt.lower()

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
            import re

            if re.search(pattern, prompt_lower):
                return RiskLevel.HIGH

        if intent in (
            IntentType.INCIDENT_TRIAGE,
            IntentType.PLAN_ROLLOUT,
            IntentType.REFACTOR_MIGRATION,
        ):
            return RiskLevel.MEDIUM

        if tone in (ToneType.ANGRY, ToneType.FRUSTRATED):
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def _generate_acceptance_criteria(
        self, intent: IntentType, entities: List[IntentEntity]
    ) -> List[str]:
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

    def _determine_constraints(self, prompt: str) -> IntentConstraints:
        constraints = IntentConstraints()
        prompt_lower = prompt.lower()
        if "offline" in prompt_lower or "no internet" in prompt_lower:
            constraints.offline_mode = True
        if "no booster" in prompt_lower or "local only" in prompt_lower:
            constraints.no_boosters = True
        return constraints

    def _get_confidence_band(self, confidence: float) -> str:
        if confidence >= 0.85:
            return "high"
        elif confidence >= self.threshold_medium:
            return "medium"
        return "low"

    def _apply_clarification_logic(self, intent: IntentV1) -> None:
        if intent.confidence_band == "low":
            if not intent.needs_clarification and not intent.two_plans_required:
                intent.two_plans_required = True
                intent.safe_next_step = {
                    "type": "universal_diagnostic",
                    "steps": [
                        "collect_context: error logs, commands, paths mentioned",
                        "identify_goal: fix, explain, implement, or check",
                        "propose_next: specific step based on findings",
                    ],
                }


_fusion_engine: Optional[IntentFusionEngine] = None


def get_fusion_engine() -> IntentFusionEngine:
    global _fusion_engine
    if _fusion_engine is None:
        _fusion_engine = IntentFusionEngine()
    return _fusion_engine


def fuse_intents(
    prompt: str,
    rasa_result: Optional[Dict],
    heuristic_result: Optional[Dict],
    meta_result: Optional[Dict],
) -> IntentV1:
    return get_fusion_engine().fuse(prompt, rasa_result, heuristic_result, meta_result)
