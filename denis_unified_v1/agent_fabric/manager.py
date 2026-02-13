import json
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

from .providers import ProviderRegistry


class Goal(BaseModel):
    text: str
    repo_root: str
    file_focus: Optional[str] = None
    constraints: Optional[Dict] = None
    approval_token: Optional[str] = None


class Task(BaseModel):
    agent: str
    goal: str


class ExecutionReport(BaseModel):
    trace_id: str
    selected_agents: List[str]
    tasks: List[Task]
    actions_taken: List[str]
    artifacts: List[str]
    verify_results: List[str]
    pending_approvals: List[str]


class AgentManager:
    def __init__(self, providers: ProviderRegistry):
        self.providers = providers

    def classify_command(self, cmd: str) -> str:
        if 'rm -rf' in cmd or 'git reset --hard' in cmd or 'kill -9' in cmd:
            return 'DESTRUCTIVE'
        elif 'git pull' in cmd or 'pip install' in cmd:
            return 'CAUTION'
        else:
            return 'SAFE'

    def execute_goal(self, goal: Goal) -> ExecutionReport:
        trace_id = str(uuid.uuid4())
        selected_agents = ['research', 'arch', 'coding', 'qa', 'ops', 'neo4j']
        tasks = [Task(agent=a, goal=goal.text) for a in selected_agents]
        actions_taken = []
        artifacts = []
        verify_results = []
        pending_approvals = []

        for task in tasks:
            try:
                agent_module = __import__(f'denis_unified_v1.agent_fabric.agents.{task.agent}', fromlist=[''])
                agent_class = getattr(agent_module, f'{task.agent.capitalize()}Agent')
                provider = self.providers.get_provider(task.agent)
                agent = agent_class(provider)
                result = agent.execute(task.goal)
                actions_taken.extend(result.get('actions', []))
                for action in result.get('actions', []):
                    if 'command' in action:
                        cmd_class = self.classify_command(action['command'])
                        if cmd_class == 'DESTRUCTIVE':
                            pending_approvals.append(f"DESTRUCTIVE: {action['command']}")
                        else:
                            try:
                                subprocess.run(action['command'], shell=True, check=True)
                            except subprocess.CalledProcessError:
                                verify_results.append(f"Failed: {action['command']}")
            except Exception as e:
                verify_results.append(f"Agent {task.agent} failed: {str(e)}")

        # Log to artifact
        log_file = Path(goal.repo_root) / 'artifacts' / 'agent_fabric' / f'{trace_id}.json'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w') as f:
            json.dump(ExecutionReport(
                trace_id=trace_id,
                selected_agents=selected_agents,
                tasks=tasks,
                actions_taken=actions_taken,
                artifacts=artifacts,
                verify_results=verify_results,
                pending_approvals=pending_approvals
            ).dict(), f, indent=2)
        artifacts.append(str(log_file))

        return ExecutionReport(
            trace_id=trace_id,
            selected_agents=selected_agents,
            tasks=tasks,
            actions_taken=actions_taken,
            artifacts=artifacts,
            verify_results=verify_results,
            pending_approvals=pending_approvals
        )
