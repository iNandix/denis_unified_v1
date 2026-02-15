"""Sprint Manager Integration for DENIS Agent.

Provides a clean API for the new DENIS agent to use the sprint orchestrator
functionality rescued from v1.
"""

from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import asyncio
import tempfile
from dataclasses import dataclass

from .integrated_orchestrator import create_integrated_orchestrator
from .code_level_manager import CodeLevel
from .models import SprintSession, WorkerAssignment
from .config import load_sprint_config


@dataclass
class SprintRequest:
    """Request to create a new sprint."""
    prompt: str
    project_paths: List[str]
    worker_count: int = 3
    complexity_focus: Optional[str] = None
    quality_requirements: List[str] = None

    def __post_init__(self):
        if self.quality_requirements is None:
            self.quality_requirements = []


@dataclass
class SprintResult:
    """Result of a sprint execution."""
    session_id: str
    status: str
    assignments: List[Dict[str, Any]]
    level_analysis: Dict[str, Any]
    health_score: float
    recommendations: List[str]
    validation_results: List[Dict[str, Any]]


class SprintManager:
    """Sprint Manager integration for DENIS agent.

    Provides a clean API to access the sprint orchestrator functionality
    rescued from v1, adapted for the new DENIS agent architecture.
    """

    def __init__(self):
        self.active_sprints: Dict[str, Any] = {}
        self.orchestrator_cache: Dict[str, Any] = {}

    async def create_sprint(self, request: SprintRequest) -> SprintResult:
        """Create a new sprint with intelligent orchestration."""
        try:
            # Convert project paths to Path objects
            project_paths = [Path(p) for p in request.project_paths]

            # Create integrated orchestrator
            orchestrator = create_integrated_orchestrator(project_paths[0])

            # Create the sprint
            result = orchestrator.create_integrated_sprint(
                prompt=request.prompt,
                workers=request.worker_count,
                projects=project_paths
            )

            # Cache the orchestrator for future operations
            session_id = result["session"].session_id
            self.active_sprints[session_id] = {
                "orchestrator": orchestrator,
                "project_paths": project_paths,
                "request": request
            }

            # Format result for DENIS agent
            assignments = []
            for assignment in result["integrated_state"]["enriched_assignments"]:
                assignments.append({
                    "worker_id": assignment.get("worker_id", f"worker-{len(assignments)+1}"),
                    "level": assignment.get("level", "medium"),
                    "crew": assignment.get("crew", "general_crew"),
                    "capabilities": assignment.get("capabilities", []),
                    "task_focus": assignment.get("task_focus", request.prompt),
                    "validation_requirements": assignment.get("validation_requirements", [])
                })

            sprint_result = SprintResult(
                session_id=session_id,
                status="created",
                assignments=assignments,
                level_analysis=result["integrated_state"]["level_analysis"],
                health_score=result["integrated_state"]["health_check"]["health_score"],
                recommendations=result.get("recommendations", []),
                validation_results=[]
            )

            return sprint_result

        except Exception as e:
            # Return error result
            return SprintResult(
                session_id="",
                status="error",
                assignments=[],
                level_analysis={},
                health_score=0.0,
                recommendations=[f"Failed to create sprint: {str(e)}"],
                validation_results=[]
            )

    async def validate_worker_task(
        self,
        session_id: str,
        worker_id: str,
        modified_files: List[str]
    ) -> Dict[str, Any]:
        """Validate a worker's task changes."""
        if session_id not in self.active_sprints:
            return {
                "valid": False,
                "error": f"Session {session_id} not found",
                "can_proceed": False
            }

        sprint_data = self.active_sprints[session_id]
        orchestrator = sprint_data["orchestrator"]

        try:
            # Convert file paths
            file_paths = [Path(f) for f in modified_files]

            # Validate the task
            validation = orchestrator.validate_worker_task(
                session_id=session_id,
                worker_id=worker_id,
                task_files=file_paths
            )

            return {
                "valid": validation.get("can_proceed", False),
                "level_analysis": validation.get("file_levels", {}),
                "validation_steps": validation.get("validation_steps", []),
                "violations": validation.get("validation", {}).get("violations", []),
                "can_proceed": validation.get("can_proceed", False),
                "recommendations": validation.get("recommendations", [])
            }

        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation failed: {str(e)}",
                "can_proceed": False
            }

    async def complete_worker_task(
        self,
        session_id: str,
        worker_id: str,
        modified_files: List[str]
    ) -> Dict[str, Any]:
        """Complete a worker's task and sync with project."""
        if session_id not in self.active_sprints:
            return {
                "success": False,
                "error": f"Session {session_id} not found"
            }

        sprint_data = self.active_sprints[session_id]
        orchestrator = sprint_data["orchestrator"]

        try:
            # Convert file paths
            file_paths = [Path(f) for f in modified_files]

            # Complete the task
            completion = orchestrator.complete_worker_task(
                session_id=session_id,
                worker_id=worker_id,
                modified_files=file_paths
            )

            return {
                "success": True,
                "sync_stats": completion.get("sync_stats", {}),
                "gaps_remaining": completion.get("gaps_remaining", 0),
                "health_score": completion.get("health_score", 0.0),
                "recommendations": completion.get("recommendations", [])
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Task completion failed: {str(e)}"
            }

    async def get_sprint_status(self, session_id: str) -> Dict[str, Any]:
        """Get comprehensive sprint status."""
        if session_id not in self.active_sprints:
            return {
                "found": False,
                "error": f"Session {session_id} not found"
            }

        sprint_data = self.active_sprints[session_id]
        orchestrator = sprint_data["orchestrator"]

        try:
            # Get session status from orchestrator
            status = orchestrator.get_session_status(session_id)

            return {
                "found": True,
                "session_id": session_id,
                "status": status.get("status", "unknown"),
                "workers_active": status.get("active_workers", 0),
                "tasks_completed": status.get("completed_tasks", 0),
                "health_score": status.get("health_score", 0.0),
                "level_distribution": status.get("level_distribution", {}),
                "validation_summary": status.get("validation_summary", {})
            }

        except Exception as e:
            return {
                "found": True,
                "session_id": session_id,
                "error": f"Status retrieval failed: {str(e)}"
            }

    async def analyze_code_complexity(self, project_path: str) -> Dict[str, Any]:
        """Analyze code complexity for project planning."""
        try:
            from .code_level_manager import CodeLevelAnalyzer

            analyzer = CodeLevelAnalyzer()
            project = Path(project_path)

            # Analyze all Python files
            python_files = list(project.rglob("*.py"))

            analysis_results = {}
            level_counts = {"basic": 0, "medium": 0, "advanced": 0}

            for file_path in python_files:
                try:
                    assignment = analyzer.assign_level(file_path)
                    analysis_results[str(file_path)] = {
                        "level": assignment.assigned_level.value,
                        "crew": assignment.recommended_crew,
                        "complexity": assignment.metrics.cyclomatic_complexity,
                        "lines": assignment.metrics.lines_of_code,
                        "functions": assignment.metrics.num_functions,
                        "requires_sandbox": assignment.sandbox_required
                    }
                    level_counts[assignment.assigned_level.value] += 1

                except Exception as e:
                    analysis_results[str(file_path)] = {
                        "error": f"Analysis failed: {str(e)}"
                    }

            return {
                "project_path": project_path,
                "files_analyzed": len(analysis_results),
                "level_distribution": level_counts,
                "file_details": analysis_results,
                "recommendations": self._generate_complexity_recommendations(level_counts)
            }

        except Exception as e:
            return {
                "error": f"Complexity analysis failed: {str(e)}",
                "project_path": project_path
            }

    def _generate_complexity_recommendations(self, level_counts: Dict[str, str]) -> List[str]:
        """Generate recommendations based on complexity analysis."""
        recommendations = []

        total_files = sum(level_counts.values())
        if total_files == 0:
            return ["No Python files found for analysis"]

        advanced_ratio = level_counts["advanced"] / total_files

        if advanced_ratio > 0.5:
            recommendations.append("High complexity project - consider breaking into smaller modules")
            recommendations.append("Implement comprehensive testing strategy for advanced components")

        if level_counts["basic"] > level_counts["advanced"] * 2:
            recommendations.append("Mostly basic code - good candidate for rapid development")
            recommendations.append("Consider adding advanced features to increase project maturity")

        if level_counts["advanced"] > 0:
            recommendations.append("Advanced components detected - ensure proper sandboxing and validation")

        return recommendations

    def list_active_sprints(self) -> List[Dict[str, Any]]:
        """List all currently active sprints."""
        return [
            {
                "session_id": session_id,
                "project_paths": [str(p) for p in data["project_paths"]],
                "worker_count": data["request"].worker_count,
                "prompt": data["request"].prompt[:50] + "..." if len(data["request"].prompt) > 50 else data["request"].prompt
            }
            for session_id, data in self.active_sprints.items()
        ]

    async def cleanup_sprint(self, session_id: str) -> bool:
        """Clean up a completed sprint."""
        if session_id in self.active_sprints:
            try:
                orchestrator = self.active_sprints[session_id]["orchestrator"]
                orchestrator.close()
                del self.active_sprints[session_id]
                return True
            except Exception:
                return False
        return False


# Global instance for easy access
_sprint_manager: Optional[SprintManager] = None


def get_sprint_manager() -> SprintManager:
    """Get the global sprint manager instance."""
    global _sprint_manager
    if _sprint_manager is None:
        _sprint_manager = SprintManager()
    return _sprint_manager
