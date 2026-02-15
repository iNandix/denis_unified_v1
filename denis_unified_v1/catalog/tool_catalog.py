"""Dynamic Tool Catalog for Persona: exists vs create decision.

Módulo central que responde a la pregunta:
"¿Tengo capacidad para resolver esto? ¿existe, se compone, o falta?"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from denis_unified_v1.catalog.schemas_v1 import (
    ToolCapabilityV1,
    LookupResultV1,
    MatchV1,
    ModeEnum,
    ExistsVsCreate,
    CapabilityType,
    CapabilitySafety,
    CapabilityAvailability,
)


CORE_CODE_INTENTS = {
    "run_tests_ci",
    "debug_repo",
    "ops_health_check",
    "implement_feature",
}


@dataclass
class CatalogContext:
    """Context for catalog lookup."""

    request_id: str
    allow_boosters: bool
    internet_gate: bool
    booster_health: bool
    confidence_band: str
    meta: Dict[str, Any]


class ToolCatalog:
    """Dynamic catalog of available capabilities - deterministic, local-first."""

    _instance: Optional["ToolCatalog"] = None

    def __init__(self, capabilities: Optional[List[ToolCapabilityV1]] = None):
        if capabilities is None:
            capabilities = _DEFAULT_CAPABILITIES
        self._caps: Dict[str, ToolCapabilityV1] = {c.name: c for c in capabilities}

    @classmethod
    def get_instance(cls) -> "ToolCatalog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list(self) -> List[ToolCapabilityV1]:
        return list(self._caps.values())

    def get(self, name: str) -> Optional[ToolCapabilityV1]:
        return self._caps.get(name)

    def lookup(
        self,
        intent: str,
        entities: Dict[str, Any],
        ctx: CatalogContext,
    ) -> LookupResultV1:
        caps = self.list()

        matches: List[MatchV1] = []
        for cap in caps:
            score, reasons, matched_tags = self._score(cap, intent, entities, ctx)
            if score > 0:
                matches.append(
                    MatchV1(
                        name=cap.name,
                        score=float(score),
                        reason_codes=reasons,
                        matched_intent=intent if intent in cap.intents else None,
                        matched_tags=matched_tags,
                    )
                )

        matches.sort(key=lambda m: m.score, reverse=True)

        exists_vs_create, recommended_mode, extra_rc, missing = self._decide(
            matches, intent, entities, ctx
        )

        features = {
            "catalog_size": len(caps),
            "num_matches": len(matches),
            "top_score": matches[0].score if matches else 0.0,
            "confidence_band": ctx.confidence_band,
            "internet_gate": ctx.internet_gate,
            "allow_boosters": ctx.allow_boosters,
            "booster_health": ctx.booster_health,
        }

        return LookupResultV1(
            request_id=ctx.request_id,
            intent=intent,
            entities=entities,
            matched_tools=matches[:5],
            missing_capabilities=missing,
            recommended_mode=recommended_mode,
            exists_vs_create=exists_vs_create,
            reason_codes=extra_rc,
            features=features,
            meta=ctx.meta,
        )

    def _score(
        self,
        cap: ToolCapabilityV1,
        intent: str,
        entities: Dict[str, Any],
        ctx: CatalogContext,
    ) -> Tuple[float, List[str], List[str]]:
        score = 0.0
        rc: List[str] = []
        matched_tags: List[str] = []

        if intent in cap.intents:
            score += 0.75
            rc.append("intent_match")

        ent_keys = set(entities.keys())
        for tag in cap.tags:
            if tag in ent_keys:
                score += 0.05
                matched_tags.append(tag)
        if matched_tags:
            rc.append("entity_tag_match")

        if cap.requires_internet and not ctx.internet_gate:
            score *= 0.2
            rc.append("blocked_by_internet_gate")

        if cap.requires_boosters and (not ctx.allow_boosters or not ctx.booster_health):
            score *= 0.2
            rc.append("blocked_by_boosters")

        if ctx.confidence_band == "medium" and cap.safety in ("mutating", "mixed"):
            score *= 0.35
            rc.append("confidence_medium_readonly")

        return max(0.0, min(1.0, score)), rc, matched_tags

    def _decide(
        self,
        matches: List[MatchV1],
        intent: str,
        entities: Dict[str, Any],
        ctx: CatalogContext,
    ) -> Tuple[ExistsVsCreate, ModeEnum, List[str], List[str]]:
        rc: List[str] = []
        missing: List[str] = []

        if ctx.confidence_band == "low":
            rc.extend(["confidence_low_no_tools", "needs_clarification"])
            return "clarify", "clarify", rc, missing

        top_score = matches[0].score if matches else 0.0

        if top_score >= 0.72:
            rc.append("capability_exists")
            return (
                "exists",
                self._recommended_mode_from_intent(intent, ctx),
                rc,
                missing,
            )

        if 0.45 <= top_score < 0.72:
            rc.append("capability_partial_compose")
            return (
                "compose",
                self._recommended_mode_from_intent(intent, ctx),
                rc,
                missing,
            )

        rc.append("capability_missing")
        missing = [f"capability_for_intent:{intent}"]

        if not ctx.internet_gate or not ctx.allow_boosters or not ctx.booster_health:
            rc.append("offline_mode")
            return "create", "direct_local", rc, missing

        return "create", "direct_boosted", rc, missing

    def _recommended_mode_from_intent(
        self, intent: str, ctx: CatalogContext
    ) -> ModeEnum:
        if intent in CORE_CODE_INTENTS:
            return "actions_plan"

        if not ctx.internet_gate or not ctx.allow_boosters or not ctx.booster_health:
            return "direct_local"

        return "direct_boosted"


def _create_default_capabilities() -> List[ToolCapabilityV1]:
    return [
        ToolCapabilityV1(
            name="run_tests_ci",
            type="action_tool",
            description="Run test suite (pytest, unittest, etc.)",
            intents=["run_tests_ci"],
            tags=["repo", "testing"],
            safety="read_only",
            availability="local",
            requires_internet=False,
            typical_evidence=["pytest_output", "test_results"],
        ),
        ToolCapabilityV1(
            name="debug_repo",
            type="action_tool",
            description="Debug repository issues, errors, stack traces",
            intents=["debug_repo"],
            tags=["repo", "debugging"],
            safety="read_only",
            availability="local",
            requires_internet=False,
            typical_evidence=["error_trace", "git_status"],
        ),
        ToolCapabilityV1(
            name="ops_health_check",
            type="action_tool",
            description="System health and monitoring checks",
            intents=["ops_health_check"],
            tags=["ops", "monitoring"],
            safety="read_only",
            availability="local",
            requires_internet=False,
            typical_evidence=["health_metrics", "service_status"],
        ),
        ToolCapabilityV1(
            name="implement_feature",
            type="action_tool",
            description="Implement new feature in codebase",
            intents=["implement_feature"],
            tags=["repo", "development"],
            safety="mutating",
            availability="local",
            requires_internet=False,
            typical_evidence=["git_diff", "file_changes"],
        ),
        ToolCapabilityV1(
            name="list_files",
            type="action_tool",
            description="List files in directory",
            intents=["list_files", "ls"],
            tags=["filesystem"],
            safety="read_only",
            availability="local",
            requires_internet=False,
        ),
        ToolCapabilityV1(
            name="grep_search",
            type="action_tool",
            description="Search for patterns in files",
            intents=["grep_search", "search"],
            tags=["filesystem", "search"],
            safety="read_only",
            availability="local",
            requires_internet=False,
        ),
        ToolCapabilityV1(
            name="run_command",
            type="action_tool",
            description="Run shell command",
            intents=["run_command", "execute"],
            tags=["shell"],
            safety="mutating",
            availability="local",
            requires_internet=False,
        ),
        ToolCapabilityV1(
            name="read_file",
            type="action_tool",
            description="Read file contents",
            intents=["read_file", "cat"],
            tags=["filesystem"],
            safety="read_only",
            availability="local",
            requires_internet=False,
        ),
        ToolCapabilityV1(
            name="local_direct_answer",
            type="local_responder",
            description="Direct answer from local templates/rules",
            intents=["chat", "help", "explain", "what", "how", "why"],
            tags=["chat"],
            safety="read_only",
            availability="local",
            requires_internet=False,
            requires_boosters=False,
        ),
    ]


_DEFAULT_CAPABILITIES = _create_default_capabilities()


def get_tool_catalog() -> ToolCatalog:
    return ToolCatalog.get_instance()
