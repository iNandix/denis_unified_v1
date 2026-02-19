"""IntentToolChainLoop - Production-ready chain executor with graph-centric learning."""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IntentToolChainLoop:
    """Production chain executor with full integration to graph and providers."""

    def __init__(self, session_id: str = None):
        self.session_id = session_id or self._get_session_id()
        self._provider_registry = None
        self._graph = None

    def _get_session_id(self) -> str:
        try:
            with open("/tmp/denis/session_id.txt") as f:
                return f.read().strip().split("|")[0]
        except Exception:
            return "default"

    @property
    def provider_registry(self):
        """Lazy load provider registry."""
        if self._provider_registry is None:
            from denis_unified_v1.agent_fabric.providers import ProviderRegistry

            self._provider_registry = ProviderRegistry()
        return self._provider_registry

    @property
    def graph(self):
        """Lazy load symbol graph."""
        if self._graph is None:
            try:
                from denis_unified_v1.kernel.ghost_ide.symbol_graph import get_symbol_graph

                self._graph = get_symbol_graph()
            except Exception as e:
                logger.warning(f"Graph not available: {e}")
        return self._graph

    def run(
        self,
        intent: str,
        context: Dict[str, Any],
        implicit_tasks: List[str] = None,
        constraints: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute complete tool chain for intent.

        Returns:
            dict with: status, output, cp_id, provider_used, latency_ms
        """
        start_time = time.time()

        implicit_tasks = implicit_tasks or []
        constraints = constraints or []
        context = context or {}

        # Step 1: Route and select provider
        provider = self.provider_registry.select_provider(
            intent=intent,
            model=context.get("model"),
            session_context=context,
        )

        # Step 2: Generate context pack if needed
        cp_id = None
        if self._requires_approval(intent, constraints):
            cp_id = self._generate_cp(intent, context, implicit_tasks, constraints)
            # In production, this would wait for approval

        # Step 3: Execute implicit tasks if any
        task_results = []
        if implicit_tasks:
            task_results = self._execute_implicit_tasks(implicit_tasks, provider, context)

        # Step 4: Execute main prompt
        prompt = context.get("prompt", "")
        system_prompt = context.get(
            "system_prompt", f"You are Denis, an AI coding assistant. Intent: {intent}"
        )

        result = self.provider_registry.execute(
            provider=provider,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=context.get("max_tokens", 1024),
        )

        # Step 5: Record to graph for learning
        self._record_to_graph(
            intent=intent,
            constraints=constraints,
            tasks=implicit_tasks,
            success=result.get("success", False),
            provider=provider.name,
        )

        latency_ms = (time.time() - start_time) * 1000

        return {
            "status": "success" if result.get("success") else "failed",
            "output": result.get("text", ""),
            "cp_id": cp_id,
            "provider_used": provider.name,
            "latency_ms": latency_ms,
            "tokens_used": result.get("tokens", 0),
            "intent": intent,
            "task_results": task_results,
        }

    def _requires_approval(self, intent: str, constraints: List[str]) -> bool:
        """Check if intent requires human approval."""
        high_risk_intents = ["delete", "remove", "drop", "destroy", "rm_rf"]
        return any(i in intent.lower() for i in high_risk_intents) or "HIGH" in constraints

    def _generate_cp(
        self,
        intent: str,
        context: Dict,
        implicit_tasks: List[str],
        constraints: List[str],
    ) -> str:
        """Generate ContextPack for approval."""
        from control_plane.models import ContextPack
        import uuid

        cp_id = f"CP-{uuid.uuid4().hex[:8]}"

        cp = ContextPack(
            cp_id=cp_id,
            mission=context.get("prompt", "")[:200],
            intent=intent,
            implicit_tasks=implicit_tasks,
            constraints=constraints,
            risk_level="HIGH" if self._requires_approval(intent, constraints) else "MEDIUM",
        )

        # Record to graph
        try:
            from denis_unified_v1.kernel.ghost_ide.symbol_graph import record_execution

            record_execution(intent, constraints, implicit_tasks, self.session_id)
        except Exception as e:
            logger.debug(f"Graph record failed: {e}")

        return cp_id

    def _execute_implicit_tasks(
        self,
        tasks: List[str],
        provider,
        context: Dict,
    ) -> List[Dict[str, Any]]:
        """Execute implicit hygiene tasks."""
        results = []
        for task in tasks:
            try:
                result = self.provider_registry.execute(
                    provider=provider,
                    prompt=task,
                    system_prompt="Execute this hygiene task concisely.",
                    max_tokens=256,
                )
                results.append(
                    {
                        "task": task,
                        "success": result.get("success", False),
                        "output": result.get("text", "")[:100],
                    }
                )
            except Exception as e:
                results.append({"task": task, "success": False, "error": str(e)})
        return results

    def _record_to_graph(
        self,
        intent: str,
        constraints: List[str],
        tasks: List[str],
        success: bool,
        provider: str,
    ) -> None:
        """Record execution to graph for learning."""
        try:
            from denis_unified_v1.kernel.ghost_ide.symbol_graph import record_execution

            record_execution(
                intent=intent,
                constraints=constraints,
                tasks=tasks,
                session_id=self.session_id,
            )

            # Also record provider stats
            logger.info(f"Executed {intent} via {provider}: {'success' if success else 'failed'}")

        except Exception as e:
            logger.debug(f"Graph record failed: {e}")


def write_agent_result(
    intent: str,
    constraints: list,
    mission_completed: str,
    success: bool,
    session_id: str,
    repo_id: str,
    repo_name: str,
    branch: str,
    model: str,
    tokens_used: int,
) -> None:
    """Write agent result to file and graph."""
    os.makedirs("/tmp/denis", exist_ok=True)

    agent_result = {
        "intent": intent,
        "constraints": constraints,
        "mission_completed": mission_completed[:200],
        "success": success,
        "session_id": session_id,
        "repo_id": repo_id,
        "repo_name": repo_name,
        "branch": branch,
        "model": model,
        "tokens_used": tokens_used,
    }

    try:
        raw = open("/tmp/denis/session_id.txt").read().strip()
        parts = (raw + "||||").split("|")
        agent_result["repo_id"] = parts[1] or repo_id
        agent_result["repo_name"] = parts[2] or repo_name
        agent_result["branch"] = parts[3] or branch
    except Exception:
        pass

    with open("/tmp/denis/agent_result.json", "w") as f:
        json.dump(agent_result, f, indent=2)

    # Also record to graph
    try:
        from denis_unified_v1.kernel.ghost_ide.symbol_graph import record_execution

        record_execution(intent, constraints, [], session_id)
    except Exception:
        pass
