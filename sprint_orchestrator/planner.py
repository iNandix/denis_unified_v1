"""Prompt-to-worker planning for sprint sessions."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .config import SprintOrchestratorConfig
from .models import GitProjectStatus, WorkerAssignment


@dataclass(frozen=True)
class WorkerRoleTemplate:
    role: str
    fallback_task: str


_ROLE_TEMPLATES: list[WorkerRoleTemplate] = [
    WorkerRoleTemplate(
        role="integrator",
        fallback_task="Integrar cambios de la fase activa, asegurar compatibilidad y preparar merge atómico.",
    ),
    WorkerRoleTemplate(
        role="hardening",
        fallback_task="Ejecutar gates de calidad/seguridad y reportar riesgos con rollback.",
    ),
    WorkerRoleTemplate(
        role="implementer",
        fallback_task="Implementar el bloque técnico principal con pruebas smoke inmediatas.",
    ),
    WorkerRoleTemplate(
        role="reviewer",
        fallback_task="Revisar regresiones, contratos y deuda técnica; proponer refactor mínimo viable.",
    ),
]


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
            provider = providers[idx % len(providers)]
            task = prompt_chunks[idx] if idx < len(prompt_chunks) else template.fallback_task
            priority = "high" if idx < 2 else "medium"
            assignments.append(
                WorkerAssignment(
                    worker_id=worker_id,
                    role=template.role,
                    provider=provider,
                    task=task,
                    project_path=project_path,
                    priority=priority,
                    status="planned",
                )
            )
        return assignments
