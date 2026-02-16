"""
PRO_SEARCH Executor - Graph-centric research execution.

Executes the PRO_SEARCH skill toolchain by reading configuration from Neo4j.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from denis_unified_v1.actions.decision_trace import emit_decision_trace
from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)


@dataclass
class SearchRequest:
    """A research request."""

    query: str
    mode: str = "user_pure"
    depth: str = "standard"
    category: str = "general"
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    request_id: Optional[str] = None


@dataclass
class SearchResult:
    """Result of a research operation."""

    status: str
    answer: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    reliability_score: Optional[float] = None
    bias_flags: List[str] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0
    decision_trace_id: Optional[str] = None


@dataclass
class ToolchainStepResult:
    """Result of executing a single toolchain step."""

    step_id: str
    step_name: str
    status: str
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int = 0
    tool_used: Optional[str] = None


class ProSearchExecutor:
    """Executor for PRO_SEARCH skill - reads config from Neo4j, executes toolchain."""

    def __init__(self, driver=None):
        self.driver = driver

    def _get_driver(self):
        if self.driver:
            return self.driver
        return _get_neo4j_driver()

    def load_skill_config(
        self, skill_id: str = "pro_search"
    ) -> Optional[Dict[str, Any]]:
        """Load full skill configuration from Neo4j."""
        driver = self._get_driver()
        if not driver:
            logger.error("No Neo4j driver available")
            return None

        with driver.session() as session:
            result = session.run(
                """
                MATCH (s:Skill {skill_id: $skill_id})
                RETURN s.name, s.version, s.policy, s.risk_level
            """,
                skill_id=skill_id,
            )
            skill = result.single()
            if not skill:
                return None

            config = {
                "skill_id": skill_id,
                "name": skill["s.name"],
                "version": skill["s.version"],
                "policy": skill["s.policy"],
                "risk_level": skill["s.risk_level"],
                "modes": {},
                "depths": {},
                "categories": {},
                "policies": {},
                "toolchain_steps": [],
                "intents": [],
            }

            modes = session.run(
                """
                MATCH (s:Skill {skill_id: $skill_id})-[:HAS_MODE]->(m:SearchMode)
                RETURN m.mode_id, m.name, m.language, m.synthesis_style, m.citations, m.output_format
            """,
                skill_id=skill_id,
            )
            for m in modes:
                config["modes"][m["m.mode_id"]] = {
                    "name": m["m.name"],
                    "language": m["m.language"],
                    "synthesis_style": m["m.synthesis_style"],
                    "citations": m["m.citations"],
                    "output_format": m.get("m.output_format"),
                }

            depths = session.run(
                """
                MATCH (s:Skill {skill_id: $skill_id})-[:HAS_DEPTH]->(d:SearchDepth)
                RETURN d.depth_id, d.name, d.time_limit_ms, d.max_sources, d.cross_verify_min
            """,
                skill_id=skill_id,
            )
            for d in depths:
                config["depths"][d["d.depth_id"]] = {
                    "name": d["d.name"],
                    "time_limit_ms": d["d.time_limit_ms"],
                    "max_sources": d["d.max_sources"],
                    "cross_verify_min": d.get("d.cross_verify_min"),
                }

            categories = session.run(
                """
                MATCH (s:Skill {skill_id: $skill_id})-[:HAS_CATEGORY]->(c:SearchCategory)
                RETURN c.category_id, c.name, c.engines
            """,
                skill_id=skill_id,
            )
            for c in categories:
                config["categories"][c["c.category_id"]] = {
                    "name": c["c.name"],
                    "engines": c.get("c.engines", []),
                }

            policies = session.run(
                """
                MATCH (s:Skill {skill_id: $skill_id})-[:HAS_POLICY]->(p:Policy)
                RETURN p.policy_id, p.name, p.rule, p.blocks_execution
            """,
                skill_id=skill_id,
            )
            for p in policies:
                config["policies"][p["p.policy_id"]] = {
                    "name": p["p.name"],
                    "rule": p["p.rule"],
                    "blocks_execution": p["p.blocks_execution"],
                }

            toolchain = session.run(
                """
                MATCH (s:Skill {skill_id: $skill_id})-[:HAS_STEP]->(step:ToolchainStep)
                OPTIONAL MATCH (step)-[:USES_TOOL]->(tool:Tool)
                RETURN step.step_id, step.name, step.order, step.required, 
                       step.timeout_ms, tool.name as tool_name, tool.tool_id as tool_id
                ORDER BY step.order
            """,
                skill_id=skill_id,
            )
            for t in toolchain:
                config["toolchain_steps"].append(
                    {
                        "step_id": t["step.step_id"],
                        "name": t["step.name"],
                        "order": t["step.order"],
                        "required": t["step.required"],
                        "timeout_ms": t["step.timeout_ms"],
                        "tool_name": t.get("tool_name"),
                        "tool_id": t.get("tool_id"),
                    }
                )

            intents = session.run(
                """
                MATCH (i:Intent)-[:ACTIVATES]->(s:Skill {skill_id: $skill_id})
                RETURN i.intent_id, i.name
            """,
                skill_id=skill_id,
            )
            for i in intents:
                config["intents"].append(
                    {
                        "intent_id": i["i.intent_id"],
                        "name": i["i.name"],
                    }
                )

            return config

    def resolve_mode_and_depth(
        self, request: SearchRequest, config: Dict
    ) -> tuple[str, str]:
        """Resolve mode and depth - can be overridden by request or inferred."""
        mode = request.mode if request.mode in config["modes"] else "user_pure"
        depth = request.depth if request.depth in config["depths"] else "standard"
        return mode, depth

    def evaluate_policies(
        self, request: SearchRequest, config: Dict, mode: str, depth: str
    ) -> tuple[bool, List[str]]:
        """Evaluate policies and return (passes, violations)."""
        violations = []
        depth_config = config["depths"].get(depth, {})

        if depth == "deep":
            cross_verify_min = depth_config.get("cross_verify_min", 0)
            if cross_verify_min < 3:
                violations.append("deep_mode_policy: cross_verify_min < 3")

        return len(violations) == 0, violations

    def _execute_classify(
        self, request: SearchRequest, config: Dict
    ) -> ToolchainStepResult:
        """Execute classify query step."""
        start = time.time()
        query = request.query

        inferred_intent = "research"
        if "find" in query.lower() or "what is" in query.lower():
            inferred_intent = "find_information"
        elif "learn" in query.lower():
            inferred_intent = "learn_topic"
        elif "verify" in query.lower() or "fact" in query.lower():
            inferred_intent = "verify_fact"

        duration = int((time.time() - start) * 1000)

        return ToolchainStepResult(
            step_id="ps_01_classify",
            step_name="classify_query",
            status="success",
            output={"inferred_intent": inferred_intent},
            duration_ms=duration,
            tool_used="intent_classifier",
        )

    def _execute_search(
        self, request: SearchRequest, config: Dict, step_info: Dict
    ) -> ToolchainStepResult:
        """Execute multi-engine search step."""
        start = time.time()

        search_results = []
        sources = []

        category = config["categories"].get(request.category, {})
        engines = category.get("engines", ["google"])

        for engine in engines[:3]:
            sources.append(f"{engine}:{request.query[:50]}")
            search_results.append(
                {
                    "engine": engine,
                    "query": request.query,
                    "url": f"https://example.com/{engine}/{uuid.uuid4().hex[:8]}",
                    "title": f"Result from {engine}",
                    "snippet": f"Mock result for: {request.query[:100]}",
                }
            )

        duration = int((time.time() - start) * 1000)

        return ToolchainStepResult(
            step_id=step_info["step_id"],
            step_name=step_info["name"],
            status="success",
            output={"results": search_results, "sources": sources},
            duration_ms=duration,
            tool_used="searxng_search",
        )

    def _execute_verify(
        self, request: SearchRequest, config: Dict, step_info: Dict, search_output: Dict
    ) -> ToolchainStepResult:
        """Execute evaluate sources step."""
        start = time.time()

        results = search_output.get("results", [])
        verified_results = []

        for r in results:
            verified_results.append(
                {
                    **r,
                    "reliability_score": 0.7 + (hash(r.get("url", "")) % 30) / 100,
                    "verified": True,
                }
            )

        avg_score = (
            sum(r["reliability_score"] for r in verified_results)
            / len(verified_results)
            if verified_results
            else 0
        )

        duration = int((time.time() - start) * 1000)

        return ToolchainStepResult(
            step_id=step_info["step_id"],
            step_name=step_info["name"],
            status="success",
            output={"verified_results": verified_results, "avg_reliability": avg_score},
            duration_ms=duration,
            tool_used="reliability_scorer",
        )

    def _execute_synthesize(
        self,
        request: SearchRequest,
        config: Dict,
        step_info: Dict,
        verify_output: Dict,
        mode: str,
    ) -> ToolchainStepResult:
        """Execute synthesize results step."""
        start = time.time()

        verified = verify_output.get("verified_results", [])
        citations = [
            {"url": r.get("url"), "title": r.get("title")} for r in verified[:5]
        ]

        if mode == "machine_only":
            answer = json.dumps(
                {
                    "query": request.query,
                    "answer": f"Synthesized answer for: {request.query}",
                    "sources": citations,
                    "reliability_score": verify_output.get("avg_reliability", 0),
                },
                indent=2,
            )
        else:
            answer = f"Based on my research: {request.query}\n\n"
            answer += "Key findings:\n"
            for i, r in enumerate(verified[:3], 1):
                answer += f"{i}. {r.get('title', 'Source')}\n"
            answer += f"\nSources: {', '.join(c.get('url', 'N/A')[:30] for c in citations[:3])}"

        duration = int((time.time() - start) * 1000)

        return ToolchainStepResult(
            step_id=step_info["step_id"],
            step_name=step_info["name"],
            status="success",
            output={"answer": answer, "citations": citations},
            duration_ms=duration,
            tool_used="llm_synthesizer",
        )

    async def execute(self, request: SearchRequest) -> SearchResult:
        """Execute full PRO_SEARCH toolchain."""
        start_time = time.time()
        session_id = request.session_id or os.getenv("DENIS_SESSION_ID", "unknown")
        turn_id = request.turn_id or str(uuid.uuid4())
        request_id = request.request_id or str(uuid.uuid4())

        config = self.load_skill_config()
        if not config:
            return SearchResult(
                status="error",
                error="Failed to load skill config from Neo4j",
            )

        mode, depth = self.resolve_mode_and_depth(request, config)

        passes, violations = self.evaluate_policies(request, config, mode, depth)

        emit_decision_trace(
            kind="policy_eval",
            mode="PASSED" if passes else "BLOCKED",
            reason=f"Mode={mode}, Depth={depth}, Violations={violations}",
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            intent="research",
            policies=list(config.get("policies", {}).keys()),
        )

        if not passes:
            return SearchResult(
                status="blocked",
                error=f"Policy violations: {violations}",
            )

        step_results: List[ToolchainStepResult] = []

        classify_result = self._execute_classify(request, config)
        step_results.append(classify_result)

        search_step = next(
            (
                s
                for s in config["toolchain_steps"]
                if s["name"] == "multi_engine_search"
            ),
            None,
        )
        if search_step:
            search_result = self._execute_search(request, config, search_step)
            step_results.append(search_result)
        else:
            search_result = None

        verify_step = next(
            (s for s in config["toolchain_steps"] if s["name"] == "evaluate_sources"),
            None,
        )
        if verify_step and search_result:
            verify_result = self._execute_verify(
                request, config, verify_step, search_result.output
            )
            step_results.append(verify_result)
        else:
            verify_result = None

        synthesize_step = next(
            (s for s in config["toolchain_steps"] if s["name"] == "synthesize_results"),
            None,
        )
        if synthesize_step and verify_result:
            synthesize_result = self._execute_synthesize(
                request, config, synthesize_step, verify_result.output, mode
            )
            step_results.append(synthesize_result)
        else:
            synthesize_result = None

        duration_ms = int((time.time() - start_time) * 1000)

        answer = (
            synthesize_result.output.get("answer") if synthesize_result else "No result"
        )
        citations = (
            synthesize_result.output.get("citations", []) if synthesize_result else []
        )
        reliability = (
            verify_result.output.get("avg_reliability") if verify_result else None
        )

        trace_id = emit_decision_trace(
            kind="research",
            mode=depth.upper(),
            reason=f"Completed {len(step_results)} steps",
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            intent="research",
            engine="qwen3b_local",
            tool="pro_search",
            extra={
                "mode": mode,
                "depth": depth,
                "steps": [s.step_id for s in step_results],
            },
        )

        return SearchResult(
            status="success",
            answer=answer,
            citations=citations,
            sources=[c.get("url") for c in citations],
            reliability_score=reliability,
            duration_ms=duration_ms,
            decision_trace_id=trace_id,
        )


async def run_pro_search(
    query: str,
    mode: str = "user_pure",
    depth: str = "standard",
    category: str = "general",
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> SearchResult:
    """Convenience function to run a research query."""
    executor = ProSearchExecutor()
    request = SearchRequest(
        query=query,
        mode=mode,
        depth=depth,
        category=category,
        session_id=session_id,
        turn_id=turn_id,
    )
    return await executor.execute(request)
