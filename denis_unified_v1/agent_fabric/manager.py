import json
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .providers import ProviderRegistry
from .schemas import GoalInput, TaskSpec, AgentResult, ExecutionReport


class RoutedRequest:
    """Minimal RoutedRequest for agent fabric."""

    def __init__(self, model: str, intent: str, prompt: str):
        self.model = model
        self.intent = intent
        self.prompt = prompt
        self.implicit_tasks: List[str] = []
        self.context_prefilled: Dict = {}
        self.do_not_touch_auto: List[str] = []
        self.constraints: List[str] = []
        self.acceptance_criteria: List[str] = []
        self.repo_id: str = ""
        self.repo_name: str = ""
        self.branch: str = ""


class AgentFabricManager:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.providers = ProviderRegistry()
        self._model_caller = None

    def _get_model_caller(self):
        """Lazy load model caller."""
        if self._model_caller is None:
            try:
                from denis_unified_v1.inference.modelcaller import call_model

                self._model_caller = call_model
            except ImportError:
                pass
        return self._model_caller

    def _get_repo_context(self) -> Dict:
        """Get repo context."""
        try:
            from control_plane.repo_context import RepoContext

            repo = RepoContext(cwd=self.repo_root)
            return {"repo_id": repo.repo_id, "repo_name": repo.repo_name, "branch": repo.branch}
        except Exception:
            return {"repo_id": "", "repo_name": "unknown", "branch": "main"}

    def try_record_agent_run(
        self, trace_id, goal_text, profile, started_ts, finished_ts=None, ok=None
    ):
        try:
            from ...tools.ide_graph.ide_graph_client import IdeGraphClient
            import os

            client = IdeGraphClient(
                os.getenv("IDE_GRAPH_URI", "bolt://127.0.0.1:7689"),
                os.getenv("IDE_GRAPH_USER", "neo4j"),
                os.getenv("IDE_GRAPH_PASSWORD", "denis-ide-graph"),
                os.getenv("IDE_GRAPH_DB", "denis_ide_graph"),
            )
            client.record_agent_run(trace_id, goal_text, profile, started_ts, finished_ts, ok)
            client.close()
        except Exception:
            pass  # fail-open

    def try_record_agent_task(self, trace_id, task_id, role, summary, status):
        try:
            from ...tools.ide_graph.ide_graph_client import IdeGraphClient
            import os

            client = IdeGraphClient(
                os.getenv("IDE_GRAPH_URI", "bolt://127.0.0.1:7689"),
                os.getenv("IDE_GRAPH_USER", "neo4j"),
                os.getenv("IDE_GRAPH_PASSWORD", "denis-ide-graph"),
                os.getenv("IDE_GRAPH_DB", "denis_ide_graph"),
            )
            client.record_agent_task(trace_id, task_id, role, summary, status)
            client.close()
        except Exception:
            pass  # fail-open

    def try_record_agent_result(
        self, trace_id, task_id, ok, files_touched, artifacts, external_refs
    ):
        try:
            from ...tools.ide_graph.ide_graph_client import IdeGraphClient
            import os

            client = IdeGraphClient(
                os.getenv("IDE_GRAPH_URI", "bolt://127.0.0.1:7689"),
                os.getenv("IDE_GRAPH_USER", "neo4j"),
                os.getenv("IDE_GRAPH_PASSWORD", "denis-ide-graph"),
                os.getenv("IDE_GRAPH_DB", "denis_ide_graph"),
            )
            client.record_agent_result(
                trace_id, task_id, ok, files_touched, artifacts, external_refs
            )
            client.close()
        except Exception:
            pass  # fail-open

    def run(self, goal: GoalInput) -> ExecutionReport:
        from datetime import datetime

        trace_id = str(uuid.uuid4())
        selected_profile = goal.profile

        started_ts = datetime.now().isoformat()
        self.try_record_agent_run(trace_id, goal.goal_text, selected_profile, started_ts)

        repo_ctx = self._get_repo_context()

        tasks = self._plan_tasks(goal.goal_text, repo_ctx)

        results = []
        for task in tasks:
            self.try_record_agent_task(trace_id, task.task_id, task.role, task.summary, "running")

            result = self._execute_task(task, goal.goal_text, repo_ctx)

            self.try_record_agent_result(
                trace_id, task.task_id, result.ok, result.files_touched, [], result.external_refs
            )
            self.try_record_agent_task(
                trace_id, task.task_id, task.role, task.summary, "done" if result.ok else "failed"
            )
            results.append(result)

        artifacts = [f"artifacts/agent_fabric/{trace_id}.json"]
        pending_confirmations = []

        finished_ts = datetime.now().isoformat()
        ok_global = all(r.ok for r in results)
        self.try_record_agent_run(
            trace_id, goal.goal_text, selected_profile, started_ts, finished_ts, ok_global
        )

        report = ExecutionReport(
            trace_id=trace_id,
            selected_profile=selected_profile,
            tasks=tasks,
            results=results,
            artifacts=artifacts,
            pending_confirmations=pending_confirmations,
        )

        report_path = Path(self.repo_root) / artifacts[0]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2)

        return report

    def _plan_tasks(self, goal_text: str, repo_ctx: Dict) -> List[TaskSpec]:
        """Plan tasks based on goal using model if available."""
        model_caller = self._get_model_caller()

        if model_caller:
            try:
                routed = RoutedRequest(
                    model="groq",
                    intent="plan_tasks",
                    prompt=f"Goal: {goal_text}\nRepo: {repo_ctx.get('repo_name', 'unknown')}\nBreak down into tasks.",
                )
                response = model_caller(
                    routed, "You are a task planner. Return a JSON array of tasks.", goal_text
                )

                tasks = self._parse_planned_tasks(response.text)
                if tasks:
                    return tasks
            except Exception:
                pass

        return self._default_tasks(goal_text)

    def _parse_planned_tasks(self, response: str) -> List[TaskSpec]:
        """Parse tasks from model response."""
        import re

        try:
            import json

            tasks_data = json.loads(response)
            if isinstance(tasks_data, list):
                return [
                    TaskSpec(
                        task_id=t.get("id", f"task_{i}"),
                        role=t.get("role", "coding"),
                        summary=t.get("summary", ""),
                        risk_level=t.get("risk", "medium"),
                    )
                    for i, t in enumerate(tasks_data)
                ]
        except Exception:
            pass
        return []

    def _default_tasks(self, goal_text: str) -> List[TaskSpec]:
        """Default task plan."""
        return [
            TaskSpec(
                task_id="research",
                role="research",
                summary=f"Research: {goal_text[:50]}",
                risk_level="low",
            ),
            TaskSpec(
                task_id="coding",
                role="coding",
                summary=f"Implement: {goal_text[:50]}",
                depends_on=["research"],
                risk_level="medium",
            ),
        ]

    def _execute_task(self, task: TaskSpec, goal_text: str, repo_ctx: Dict) -> AgentResult:
        """Execute a single task using model caller."""
        model_caller = self._get_model_caller()

        provider = self.providers.get_provider(task.role)

        prompt = f"Goal: {goal_text}\nTask: {task.summary}\nRole: {task.role}"

        if model_caller and task.role in ["research", "coding"]:
            try:
                routed = RoutedRequest(
                    model=provider,
                    intent=task.role,
                    prompt=prompt,
                )
                routed.repo_id = repo_ctx.get("repo_id", "")
                routed.repo_name = repo_ctx.get("repo_name", "")
                routed.branch = repo_ctx.get("branch", "main")

                system_prompt = f"You are a {task.role} agent. Execute the task: {task.summary}"
                response = model_caller(routed, system_prompt, prompt)

                return AgentResult(
                    task_id=task.task_id,
                    ok=True,
                    summary=response.text[:500] if response.text else f"Executed {task.role}",
                    files_touched=[],
                    decision_trace=[
                        f"Used model: {response.model}, fallback: {response.used_fallback}"
                    ],
                )
            except Exception as e:
                return AgentResult(
                    task_id=task.task_id,
                    ok=False,
                    summary=f"Error: {str(e)[:200]}",
                    decision_trace=[f"Error: {e}"],
                )

        return AgentResult(
            task_id=task.task_id,
            ok=True,
            summary=f"Mocked {task.role} for {goal_text[:30]}",
            files_touched=[],
            decision_trace=[f"Role: {task.role}, Provider: {provider}"],
        )
