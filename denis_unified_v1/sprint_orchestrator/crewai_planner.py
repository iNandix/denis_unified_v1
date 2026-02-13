"""CrewAI-based planner for generating canonical PlanJSON."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from crewai import Agent, Task, Crew
from .plan_schema import PlanJSON, Project, Constraint, Risk, Milestone, Task as PlanTask, DispatchPolicy, Slot
from .model_adapter import build_provider_request, invoke_provider_request, parse_provider_response
from .providers import load_provider_statuses
from .config import SprintOrchestratorConfig


def get_repo_snapshot(project_root: str) -> str:
    """Generate a summary of the repo for planning."""
    root = Path(project_root)
    summary = f"Project root: {project_root}\n"
    summary += f"Files:\n"
    for file in root.rglob("*.py"):
        summary += f"- {file.relative_to(root)}\n"
    # Add more: pyproject.toml, tests, endpoints, git log
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        summary += f"\nPyproject:\n{pyproject.read_text()[:500]}\n"
    tests_dir = root / "tests"
    if tests_dir.exists():
        summary += f"\nTests: {len(list(tests_dir.rglob('*.py')))} files\n"
    # Endpoints detection (basic)
    endpoints = []
    for file in root.rglob("*.py"):
        content = file.read_text()
        if "app.add_route" in content or "@app." in content:
            endpoints.extend([line for line in content.split('\n') if "@app." in line][:5])
    if endpoints:
        summary += f"\nEndpoints:\n" + '\n'.join(endpoints[:10]) + '\n'
    # Git log
    try:
        import subprocess
        result = subprocess.run(["git", "-C", project_root, "log", "--oneline", "-10"], capture_output=True, text=True)
        summary += f"\nGit log:\n{result.stdout}"
    except:
        pass
    return summary[:3000]  # limit


def build_plan(nl_prompt: str, rasa_intent: str, confidence: float, project_root: str, config: SprintOrchestratorConfig) -> PlanJSON:
    threshold = 0.8
    if confidence < threshold:
        # Fallback to LLM planner
        statuses = load_provider_statuses(config)
        canonical_status = next((s for s in statuses if s.provider == "denis_canonical"), None)
        if not canonical_status or not canonical_status.configured:
            raise RuntimeError("Fallback planner requires configured denis_canonical")
        
        repo_snapshot = get_repo_snapshot(project_root)

        system_prompt = f"""
        Eres "SprintPlanner". Tu salida DEBE ser SOLO el JSON canónico válido, sin markdown, sin comentarios.
        Input: nl_prompt="{nl_prompt}", rasa_intent="{rasa_intent}", confidence={confidence}, project_root="{project_root}", repo_snapshot="{repo_snapshot}"
        Usa el repo_snapshot para assumptions. Divide en milestones y tasks atómicas con verify_targets reales.
        Aplica contracts_change_policy=always_approve.
        Marca requires_approval=true si toca contracts/*, security/gates, infra/systemd, o herramientas peligrosas.
        Output: JSON válido como especificado.
        """

        messages = [{"role": "user", "content": system_prompt}]
        request = build_provider_request(config=config, status=canonical_status, messages=messages)
        response = invoke_provider_request(request, timeout_sec=60)
        normalized = parse_provider_response(canonical_status, response["data"])
        plan_dict = json.loads(normalized["text"])
        plan = PlanJSON(**plan_dict)
        return plan

    # CrewAI
    try:
        repo_snapshot = get_repo_snapshot(project_root)

        system_prompt = f"""
        Eres "SprintPlanner". Tu salida DEBE ser SOLO el JSON canónico válido, sin markdown, sin comentarios.
        Input: nl_prompt="{nl_prompt}", rasa_intent="{rasa_intent}", confidence={confidence}, project_root="{project_root}", repo_snapshot="{repo_snapshot}"
        Usa el repo_snapshot para assumptions. Divide en milestones y tasks atómicas con verify_targets reales.
        Aplica contracts_change_policy=always_approve.
        Marca requires_approval=true si toca contracts/*, security/gates, infra/systemd, o herramientas peligrosas.
        Output: JSON válido como especificado.
        """

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

        manager = Agent(
            role="SprintPlanner",
            goal="Create a step-by-step plan and output ONLY the canonical JSON.",
            backstory="Planning agent that structures complex tasks into milestones and atomic tasks.",
            allow_delegation=True
        )

        plan_task = Task(
            description=system_prompt,
            agent=manager,
            expected_output="Valid JSON object matching the PlanJSON schema."
        )

        crew = Crew(
            agents=[architect, coder, qa, ops, manager],
            tasks=[plan_task],
            verbose=True,
            planning=True
        )

        result = crew.kickoff()
        plan_dict = json.loads(str(result))
        plan = PlanJSON(**plan_dict)
        return plan
    except ImportError:
        raise RuntimeError("CrewAI not installed; use fallback or install CrewAI")
