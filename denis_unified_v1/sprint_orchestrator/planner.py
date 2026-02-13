"""Prompt-to-worker planning for sprint sessions."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .config import SprintOrchestratorConfig
from .models import GitProjectStatus, WorkerAssignment
from .plan_schema import PlanJSON


@dataclass(frozen=True)
class WorkerRoleTemplate:
    role: str
    fallback_task: str


_ROLE_TEMPLATES: list[WorkerRoleTemplate] = [
    WorkerRoleTemplate(
        role="arch",
        fallback_task="Diseñar arquitectura y especificar contratos para el sprint.",
    ),
    WorkerRoleTemplate(
        role="coding",
        fallback_task="Implementar código según especificaciones, con pruebas unitarias.",
    ),
    WorkerRoleTemplate(
        role="qa",
        fallback_task="Ejecutar pruebas de calidad, reportar bugs y validar contratos.",
    ),
    WorkerRoleTemplate(
        role="ops",
        fallback_task="Desplegar, monitorear y asegurar operaciones del sistema.",
    ),
]


_ROLE_PROVIDER_MAPPING = {
    "coding": "denis_agent",
}


def _extract_prompt_chunks(prompt: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"[\n\.\;]+", prompt) if chunk.strip()]
    return chunks[:8]


class SprintPlanner:
    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config

    def build_assignments(
        self,
        *,
        prompt: str,
        workers: int,
        projects: list[GitProjectStatus],
        provider_pool: list[str] | None = None,
    ) -> list[WorkerAssignment]:
        safe_workers = max(1, min(workers, min(4, self.config.max_workers)))
        prompt_chunks = _extract_prompt_chunks(prompt)
        providers = [p.strip() for p in (provider_pool or self.config.provider_pool) if p.strip()]
        if not providers:
            raise ValueError("No configured providers available for sprint assignments")

        if not projects:
            project_path = str(self.config.projects_scan_root)
        else:
            primary = projects[0]
            project_path = primary.path

        assignments: list[WorkerAssignment] = []
        for idx in range(safe_workers):
            worker_num = idx + 1
            worker_id = f"worker-{worker_num}"
            template = _ROLE_TEMPLATES[idx % len(_ROLE_TEMPLATES)]
            preferred_provider = _ROLE_PROVIDER_MAPPING.get(template.role)
            if preferred_provider and preferred_provider in providers:
                provider = preferred_provider
            else:
                provider = providers[idx % len(providers)]
            task = prompt_chunks[idx] if idx < len(prompt_chunks) else template.fallback_task
            priority = "high" if idx < 2 else "medium"
            phase = {
                0: "design",
                1: "implementation",
                2: "testing",
                3: "deployment"
            }.get(idx, "general")
            assignments.append(
                WorkerAssignment(
                    worker_id=worker_id,
                    role=template.role,
                    provider=provider,
                    task=task,
                    project_path=project_path,
                    priority=priority,
                    status="planned",
                    phase=phase,
                )
            )
        return assignments


    def build_assignments_from_plan_json(self, plan_json: PlanJSON, config: SprintOrchestratorConfig) -> list[WorkerAssignment]:
        assignments = []
        slot_mapping = plan_json.dispatch_policy.slots
        for milestone in plan_json.milestones:
            for task in milestone.tasks:
                area = task.area
                slot_key = None
                for k, slot in slot_mapping.items():
                    if slot.area == area:
                        slot_key = k
                        break
                if not slot_key:
                    continue
                slot_info = slot_mapping[slot_key]
                provider = slot_info.preferred_provider
                # Check if configured, else fallback
                # For now, use provider
                assignment = WorkerAssignment(
                    worker_id=slot_key.replace("slot-", "worker-"),
                    role=area.lower(),
                    provider=provider,
                    task=task.summary,
                    project_path=plan_json.project.root,
                    priority="medium",
                    status="planned",
                    phase=milestone.id
                )
                assignments.append(assignment)
        return assignments
