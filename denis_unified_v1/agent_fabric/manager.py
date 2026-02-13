import json
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

from .providers import ProviderRegistry


class GoalInput(BaseModel):
    goal_text: str
    repo_root: str
    profile: str = "auto"
    network_policy: str = "restricted"
    approval_token: Optional[str] = None


class TaskSpec(BaseModel):
    task_id: str
    role: str
    summary: str
    inputs: List[str] = []
    outputs: List[str] = []
    commands: List[str] = []
    verify_targets: List[str] = []
    depends_on: List[str] = []
    risk_level: str


class AgentResult(BaseModel):
    task_id: str
    ok: bool
    summary: str
    files_touched: List[str] = []
    commands: List[str] = []
    verify_targets: List[str] = []
    external_refs: List[str] = []
    decision_trace: List[str] = []


class ExecutionReport(BaseModel):
    trace_id: str
    selected_profile: str
    tasks: List[TaskSpec]
    results: List[AgentResult]
    artifacts: List[str]
    pending_confirmations: List[str]


class AgentFabricManager:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        # Mock providers
        self.providers = ProviderRegistry()

    def try_record_agent_run(self, trace_id, goal_text, profile, started_ts, finished_ts=None, ok=None):
        try:
            from ...tools.ide_graph.ide_graph_client import IdeGraphClient
            import os
            client = IdeGraphClient(
                os.getenv('IDE_GRAPH_URI', 'bolt://127.0.0.1:7689'),
                os.getenv('IDE_GRAPH_USER', 'neo4j'),
                os.getenv('IDE_GRAPH_PASSWORD', 'denis-ide-graph'),
                os.getenv('IDE_GRAPH_DB', 'denis_ide_graph')
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
                os.getenv('IDE_GRAPH_URI', 'bolt://127.0.0.1:7689'),
                os.getenv('IDE_GRAPH_USER', 'neo4j'),
                os.getenv('IDE_GRAPH_PASSWORD', 'denis-ide-graph'),
                os.getenv('IDE_GRAPH_DB', 'denis_ide_graph')
            )
            client.record_agent_task(trace_id, task_id, role, summary, status)
            client.close()
        except Exception:
            pass  # fail-open

    def try_record_agent_result(self, trace_id, task_id, ok, files_touched, artifacts, external_refs):
        try:
            from ...tools.ide_graph.ide_graph_client import IdeGraphClient
            import os
            client = IdeGraphClient(
                os.getenv('IDE_GRAPH_URI', 'bolt://127.0.0.1:7689'),
                os.getenv('IDE_GRAPH_USER', 'neo4j'),
                os.getenv('IDE_GRAPH_PASSWORD', 'denis-ide-graph'),
                os.getenv('IDE_GRAPH_DB', 'denis_ide_graph')
            )
            client.record_agent_result(trace_id, task_id, ok, files_touched, artifacts, external_refs)
            client.close()
        except Exception:
            pass  # fail-open

    def run(self, goal: GoalInput) -> ExecutionReport:
        from datetime import datetime
        trace_id = str(uuid.uuid4())
        selected_profile = goal.profile

        started_ts = datetime.now().isoformat()
        self.try_record_agent_run(trace_id, goal.goal_text, selected_profile, started_ts)

        # Mock context pack
        context_pack = {}

        # Mock planner: generate basic tasks
        tasks = [
            TaskSpec(
                task_id='research',
                role='research',
                summary='Research options for goal',
                inputs=[],
                outputs=[],
                commands=[],
                verify_targets=[],
                depends_on=[],
                risk_level='low'
            ),
            TaskSpec(
                task_id='coding',
                role='coding',
                summary='Implement changes for goal',
                inputs=[],
                outputs=[],
                commands=[],
                verify_targets=[],
                depends_on=['research'],
                risk_level='medium'
            )
        ]

        results = []
        for task in tasks:
            self.try_record_agent_task(trace_id, task.task_id, task.role, task.summary, "running")
            # Mock agent execution
            result = AgentResult(
                task_id=task.task_id,
                ok=True,
                summary=f'Executed {task.role} for {goal.goal_text}',
                files_touched=[],
                commands=[],
                verify_targets=[],
                external_refs=[],
                decision_trace=[f'Decided to {task.role} based on goal']
            )
            self.try_record_agent_result(trace_id, task.task_id, result.ok, result.files_touched, [], result.external_refs)
            self.try_record_agent_task(trace_id, task.task_id, task.role, task.summary, "done" if result.ok else "failed")
            results.append(result)

        artifacts = [f'artifacts/agent_fabric/{trace_id}.json']
        pending_confirmations = []

        finished_ts = datetime.now().isoformat()
        ok_global = all(r.ok for r in results)
        self.try_record_agent_run(trace_id, goal.goal_text, selected_profile, started_ts, finished_ts, ok_global)

        report = ExecutionReport(
            trace_id=trace_id,
            selected_profile=selected_profile,
            tasks=tasks,
            results=results,
            artifacts=artifacts,
            pending_confirmations=pending_confirmations
        )

        # Save report
        report_path = Path(self.repo_root) / artifacts[0]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report.model_dump(mode="json"), f, indent=2)

        return report
