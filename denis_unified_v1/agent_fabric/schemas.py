from pydantic import BaseModel
from typing import List, Optional

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
