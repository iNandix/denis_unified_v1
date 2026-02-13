"""Canonical Plan JSON schema using Pydantic."""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Dict


class Project(BaseModel):
    name: str
    root: str
    branch: str


class Constraint(BaseModel):
    time_budget_minutes: int
    network_policy: str  # offline|restricted|full
    dangerous_tools: str  # deny|approve
    contracts_change_policy: str  # always_approve


class Risk(BaseModel):
    id: str
    summary: str
    mitigation: str


class Task(BaseModel):
    id: str
    area: str  # ARCH|CODING|QA|OPS
    summary: str
    rationale: str
    inputs: List[str]
    outputs: List[str]
    files_touched: List[str]
    commands: List[str]
    verify_targets: List[str]
    rollback: str
    requires_approval: bool
    depends_on: List[str]
    budget_minutes: int


class Milestone(BaseModel):
    id: str
    title: str
    acceptance: List[str]
    tasks: List[Task]


class Slot(BaseModel):
    area: str
    preferred_provider: str
    fallback: List[str]


class DispatchPolicy(BaseModel):
    slots: Dict[str, Slot]


class PlanJSON(BaseModel):
    version: str
    trace_id: str
    project: Project
    objective: str
    assumptions: List[str]
    constraints: Constraint
    risks: List[Risk]
    milestones: List[Milestone]
    dispatch_policy: DispatchPolicy
