"""Sprint Orchestrator Integration Layer - Conecta todos los componentes.

Integra:
- SprintOrchestrator (flujo principal)
- GitGraphComparator (Git vs Grafo)
- AtlasGitValidator (validación de calidad)
- CodeLevelManager (niveles básico/medio/avanzado)
- Sandbox (validación segura)
- ChangeGuard (anti-placeholders)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from .orchestrator import SprintOrchestrator
from .git_graph_comparator import GitGraphComparator
from .atlas_git_validator import AtlasGitValidator, AtlasValidationConfig
from .code_level_manager import CrewLevelRouter, CodeLevel, analyze_project_levels
from .change_guard import ChangeGuard
from .config import SprintOrchestratorConfig
from .models import SprintEvent, SprintSession, WorkerAssignment
from .event_bus import EventBus, publish_event


@dataclass
class IntegratedSprintConfig:
    """Configuración para sprint integrado con todas las validaciones."""

    # Config base
    sprint_config: SprintOrchestratorConfig

    # Validaciones Atlas
    atlas_config: AtlasValidationConfig = field(default_factory=AtlasValidationConfig)

    # Niveles de código
    enable_code_levels: bool = True
    auto_assign_crews: bool = True

    # Git-Grafo
    enable_graph_sync: bool = True
    min_graph_coverage: float = 0.7

    # Sandbox
    sandbox_medium_advanced: bool = True
    sandbox_basic: bool = False

    # Validación continua
    validate_on_assignment: bool = True
    validate_on_completion: bool = True
    block_on_violations: bool = True


class IntegratedSprintOrchestrator:
    """Orchestrator integrado con validación completa.

    Este es el punto de entrada principal que coordina:
    1. SprintOrchestrator (base)
    2. GitGraphComparator (Git vs Grafo)
    3. AtlasGitValidator (calidad de código)
    4. CodeLevelManager (niveles y crews)
    5. Sandbox (ejecución segura)
    6. ChangeGuard (placeholders/stubs)

    Flujo de trabajo:
    1. Crear sprint con análisis de nivel
    2. Asignar workers según nivel de complejidad
    3. Validar cada cambio antes de commit
    4. Sincronizar Git con Grafo
    5. Ejecutar en sandbox si es necesario
    6. Garantizar avance del proyecto
    """

    def __init__(self, config: IntegratedSprintConfig):
        self.config = config

        # Componentes base
        self.orchestrator = SprintOrchestrator(config.sprint_config)
        self.store = self.orchestrator.store
        self.bus = self.orchestrator.bus

        # Componentes de validación
        self.git_comparator = GitGraphComparator(
            neo4j_uri=config.atlas_config.neo4j_uri
        )
        self.atlas_validator = AtlasGitValidator(config.atlas_config)
        self.level_router = CrewLevelRouter()
        self.change_guard = ChangeGuard(config.sprint_config)

        # Estado
        self._active_sessions: Dict[str, Any] = {}

    def create_integrated_sprint(
        self,
        *,
        prompt: str,
        workers: int,
        projects: List[Path],
        analyze_levels: bool = True,
    ) -> Dict[str, Any]:
        """Crea un sprint con análisis completo integrado.

        Args:
            prompt: Descripción del objetivo del sprint
            workers: Número de workers a asignar
            projects: Lista de proyectos a trabajar
            analyze_levels: Si analizar niveles de código

        Returns:
            Resultado con sesión, análisis de niveles, y plan integrado
        """
        # 1. Analizar proyectos y niveles
        level_analysis = None
        if analyze_levels and self.config.enable_code_levels:
            level_analysis = self._analyze_project_levels(projects)

        # 2. Comparar Git vs Grafo
        graph_analysis = None
        if self.config.enable_graph_sync:
            graph_analysis = self._analyze_graph_gaps(projects)

        # 3. Crear sesión base
        session = self.orchestrator.create_session(
            prompt=prompt,
            workers=workers,
            projects=projects,
        )

        # 4. Enriquecer assignments con niveles
        enriched_assignments = self._enrich_assignments(
            session.assignments, level_analysis
        )

        # 5. Validar estado inicial
        health_check = self._check_sprint_health(session, projects)

        # 6. Guardar estado integrado
        integrated_state = {
            "session_id": session.session_id,
            "level_analysis": level_analysis,
            "graph_analysis": graph_analysis,
            "health_check": health_check,
            "enriched_assignments": [
                self._assignment_to_dict(a) for a in enriched_assignments
            ],
            "validation_config": {
                "sandbox_medium_advanced": self.config.sandbox_medium_advanced,
                "sandbox_basic": self.config.sandbox_basic,
                "min_graph_coverage": self.config.min_graph_coverage,
                "block_on_violations": self.config.block_on_violations,
            },
        }
        self._active_sessions[session.session_id] = integrated_state

        # 7. Publicar evento de inicio integrado
        publish_event(
            self.store,
            SprintEvent(
                session_id=session.session_id,
                worker_id="system",
                kind="integrated_sprint.start",
                message=f"Sprint integrado creado con {len(enriched_assignments)} assignments enriquecidos",
                payload={
                    "levels_found": level_analysis["summary"]
                    if level_analysis
                    else None,
                    "graph_gaps": len(graph_analysis.gaps) if graph_analysis else 0,
                    "health_score": health_check.get("health_score", 0),
                },
            ),
            self.bus,
        )

        return {
            "session": session,
            "integrated_state": integrated_state,
            "recommendations": self._generate_recommendations(
                level_analysis, graph_analysis, health_check
            ),
        }

    def validate_worker_task(
        self, session_id: str, worker_id: str, task_files: List[str]
    ) -> Dict[str, Any]:
        """Valida una tarea de worker antes de ejecución.

        Esta es la función clave que valida calidad antes de commit.

        Args:
            session_id: ID de la sesión
            worker_id: ID del worker
            task_files: Archivos a modificar/crear

        Returns:
            Resultado de validación con decisión de permitir/bloquear
        """
        session_state = self._active_sessions.get(session_id, {})

        # 1. Analizar nivel de archivos
        file_levels = {}
        for file_path in task_files:
            path = Path(file_path)
            if path.exists():
                assignment = self.level_router.analyzer.assign_level(path)
                file_levels[file_path] = {
                    "level": assignment.assigned_level.value,
                    "crew": assignment.recommended_crew,
                    "sandbox": assignment.sandbox_required,
                    "metrics": assignment.metrics.to_dict(),
                }

        # 2. Validar contra Atlas (pre-commit)
        validation_result = self.atlas_validator.validate_staged_changes()

        # 3. Verificar cobertura del grafo
        graph_ok = True
        if self.config.enable_graph_sync:
            comparison = self.git_comparator.compare_project(
                self.config.atlas_config.project_path
            )
            coverage = comparison.total_entities_in_graph / max(
                comparison.total_files_in_git, 1
            )
            graph_ok = coverage >= self.config.min_graph_coverage

        # 4. Decisión final
        can_proceed = (
            validation_result.passed
            and graph_ok
            and not (validation_result.violations and self.config.block_on_violations)
        )

        result = {
            "can_proceed": can_proceed,
            "validation": {
                "passed": validation_result.passed,
                "violations": validation_result.violations,
                "warnings": validation_result.warnings,
            },
            "file_levels": file_levels,
            "graph_coverage_ok": graph_ok,
            "requires_sandbox": any(
                f.get("sandbox", False) for f in file_levels.values()
            ),
            "suggested_crews": list(
                set(f.get("crew", "unknown") for f in file_levels.values())
            ),
        }

        # Publicar evento
        publish_event(
            self.store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="task.validation",
                message=f"Validación: {'✅ PASÓ' if can_proceed else '❌ FALLÓ'}",
                payload=result,
            ),
            self.bus,
        )

        return result

    def complete_worker_task(
        self, session_id: str, worker_id: str, modified_files: List[str]
    ) -> Dict[str, Any]:
        """Completa una tarea y sincroniza con el grafo.

        Args:
            session_id: ID de la sesión
            worker_id: ID del worker
            modified_files: Archivos modificados

        Returns:
            Resultado de la sincronización
        """
        project_path = self.config.atlas_config.project_path

        # 1. Sincronizar Git al grafo
        sync_stats = None
        if self.config.enable_graph_sync:
            sync_stats = self.git_comparator.sync_git_to_graph(project_path)

        # 2. Verificar gaps post-cambio
        comparison = self.git_comparator.compare_project(project_path)

        # 3. Health check
        health = self.atlas_validator.check_project_health()

        result = {
            "sync_stats": sync_stats,
            "gaps_remaining": len(comparison.gaps),
            "health_score": health["health_score"],
            "status": health["status"],
        }

        # Publicar evento
        publish_event(
            self.store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="task.complete",
                message=f"Tarea completada. Health: {health['health_score']}/100",
                payload=result,
            ),
            self.bus,
        )

        return result

    def _analyze_project_levels(self, projects: List[Path]) -> Dict[str, Any]:
        """Analiza niveles de código en los proyectos."""
        all_results = {
            "projects": {},
            "summary": {
                "total_files": 0,
                "basic": 0,
                "medium": 0,
                "advanced": 0,
            },
        }

        for project in projects:
            if project.is_dir():
                result = analyze_project_levels(project)
                all_results["projects"][str(project)] = result

                # Agregar a sumario
                for key in ["basic", "medium", "advanced"]:
                    all_results["summary"][key] += result["summary"].get(
                        f"{key}_count", 0
                    )
                all_results["summary"]["total_files"] += result["summary"].get(
                    "total_files", 0
                )

        return all_results

    def _analyze_graph_gaps(self, projects: List[Path]):
        """Analiza gaps entre Git y el grafo."""
        # Usar el primer proyecto como principal
        if projects:
            return self.git_comparator.compare_project(projects[0])
        return None

    def _enrich_assignments(
        self, assignments: List[WorkerAssignment], level_analysis: Optional[Dict]
    ) -> List[Dict[str, Any]]:
        """Enriquece assignments con información de niveles."""
        enriched = []

        for assignment in assignments:
            enriched_assignment = {
                "base": assignment.as_dict(),
                "level": None,
                "crew": None,
                "validation_pipeline": [],
            }

            # Determinar nivel según la tarea
            task_lower = assignment.task.lower()
            if any(k in task_lower for k in ["config", "setup", "util"]):
                enriched_assignment["level"] = CodeLevel.BASIC.value
                enriched_assignment["crew"] = "config_crew"
                enriched_assignment["validation_pipeline"] = ["syntax", "lint"]
            elif any(k in task_lower for k in ["feature", "implement", "api"]):
                enriched_assignment["level"] = CodeLevel.MEDIUM.value
                enriched_assignment["crew"] = "feature_crew"
                enriched_assignment["validation_pipeline"] = [
                    "lint",
                    "tests",
                    "sandbox",
                ]
            else:
                enriched_assignment["level"] = CodeLevel.ADVANCED.value
                enriched_assignment["crew"] = "architecture_crew"
                enriched_assignment["validation_pipeline"] = [
                    "lint",
                    "tests",
                    "security",
                    "sandbox",
                ]

            enriched.append(enriched_assignment)

        return enriched

    def _check_sprint_health(
        self, session: SprintSession, projects: List[Path]
    ) -> Dict[str, Any]:
        """Verifica salud general del sprint."""
        if projects:
            return self.atlas_validator.check_project_health()
        return {"health_score": 0, "status": "unknown"}

    def _generate_recommendations(
        self,
        level_analysis: Optional[Dict],
        graph_analysis: Optional[Any],
        health_check: Dict[str, Any],
    ) -> List[str]:
        """Genera recomendaciones basadas en análisis."""
        recommendations = []

        # Recomendaciones de nivel
        if level_analysis:
            summary = level_analysis.get("summary", {})
            if summary.get("advanced", 0) > 5:
                recommendations.append(
                    f"⚠️ {summary['advanced']} archivos avanzados detectados. "
                    "Se recomienda dividir el sprint en fases."
                )

        # Recomendaciones de grafo
        if graph_analysis and len(graph_analysis.gaps) > 10:
            recommendations.append(
                f"📊 {len(graph_analysis.gaps)} gaps detectados. "
                "Ejecutar: qcli index --project ."
            )

        # Recomendaciones de salud
        health_score = health_check.get("health_score", 100)
        if health_score < 50:
            recommendations.append(
                "🚨 Salud crítica. Se requiere sincronización urgente Git-Grafo."
            )
        elif health_score < 80:
            recommendations.append("⚠️ Salud degradada. Revisar cobertura del grafo.")

        return recommendations

    def _assignment_to_dict(self, assignment: Dict) -> Dict[str, Any]:
        """Convierte assignment enriquecido a dict."""
        return assignment

    def close(self):
        """Cierra conexiones."""
        self.git_comparator.close()
        self.atlas_validator.close()


# Función de conveniencia para crear orchestrator integrado
def create_integrated_orchestrator(
    project_root: Path, neo4j_uri: str = "bolt://localhost:7687"
) -> IntegratedSprintOrchestrator:
    """Crea una instancia del orchestrator integrado con configuración por defecto."""
    from .config import load_sprint_config

    sprint_config = load_sprint_config(project_root)

    atlas_config = AtlasValidationConfig(
        project_path=project_root,
        neo4j_uri=neo4j_uri,
        auto_commit_enabled=False,  # Siempre manual por seguridad
    )

    integrated_config = IntegratedSprintConfig(
        sprint_config=sprint_config,
        atlas_config=atlas_config,
        enable_code_levels=True,
        enable_graph_sync=True,
        sandbox_medium_advanced=True,
        validate_on_assignment=True,
        validate_on_completion=True,
        block_on_violations=True,
    )

    return IntegratedSprintOrchestrator(integrated_config)
