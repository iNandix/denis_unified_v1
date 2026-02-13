"""CrewAI-based planner for generating canonical PlanJSON."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from crewai import Agent, Task, Crew
from .plan_schema import PlanJSON, Project, Constraint, Risk, Milestone, Task as PlanTask, DispatchPolicy, Slot


def get_repo_snapshot(project_root: str) -> str:
    """Generate a summary of the repo for planning."""
    root = Path(project_root)
    summary = f"Project root: {project_root}\n"
    summary += f"Files:\n"
    for file in root.rglob("*.py"):
        summary += f"- {file.relative_to(root)}\n"
    # Add more: pyproject.toml, tests, etc.
    return summary[:2000]  # limit


def build_plan(nl_prompt: str, rasa_intent: str, confidence: float, project_root: str) -> PlanJSON:
    threshold = 0.8
    if confidence < threshold:
        # Fallback to simple LLM planner
        # For now, raise error
        raise NotImplementedError(f"Confidence {confidence} < {threshold}, fallback not implemented")

    repo_snapshot = get_repo_snapshot(project_root)

    # Define agents
    architect = Agent(
        role="Architect",
        goal="Define structure, contracts, interfaces; no code writing except minimal scaffolding.",
        backstory="Expert in system architecture and design patterns."
    )

    coder = Agent(
        role="Coder",
        goal="Define implementation steps and concrete commands; prioritize small verifiable changes.",
        backstory="Expert in coding, debugging, and incremental development."
    )

    qa = Agent(
        role="QA",
        goal="Define verify_targets, tests, harness/smokes and done criteria.",
        backstory="Expert in quality assurance, testing strategies, and validation."
    )

    ops = Agent(
        role="Ops",
        goal="Define deploy/runbook, flags/env, systemd/docker, observability.",
        backstory="Expert in operations, deployment, and system administration."
    )

    # Manager/Planning agent
    manager = Agent(
        role="SprintPlanner",
        goal="Create a step-by-step plan and output ONLY the canonical JSON.",
        backstory="Planning agent that structures complex tasks into milestones and atomic tasks.",
        allow_delegation=True
    )

    # System prompt for manager
    system_prompt = f"""
    Eres "SprintPlanner". Tu salida DEBE ser SOLO el JSON canónico válido, sin markdown, sin comentarios.
    Input: nl_prompt="{nl_prompt}", rasa_intent="{rasa_intent}", confidence={confidence}, project_root="{project_root}", repo_snapshot="{repo_snapshot}"
    Usa el repo_snapshot para assumptions. Divide en milestones y tasks atómicas con verify_targets reales.
    Aplica contracts_change_policy=always_approve.
    Marca requires_approval=true si toca contracts/*, security/gates, infra/systemd, o herramientas peligrosas.
    Output: JSON válido como especificado.
    """

    # Task
    plan_task = Task(
        description=system_prompt,
        agent=manager,
        expected_output="Valid JSON object matching the PlanJSON schema."
    )

    # Crew with planning enabled
    crew = Crew(
        agents=[architect, coder, qa, ops, manager],
        tasks=[plan_task],
        verbose=True,
        planning=True  # Enable planning agent
    )

    # Run
    result = crew.kickoff()
    # Assume result is JSON string
    plan_dict = json.loads(str(result))
    # Validate
    plan = PlanJSON(**plan_dict)
    return plan
