"""Code Level Manager - Gestiona niveles básico/medio/avanzado con CrewAI.

Integra:
- Niveles de complejidad de código (basic/medium/advanced)
- CrewAI para asignación de crews especializados
- Sandbox para validación segura
- Atlas para tracking de progreso
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import ast
import re


class CodeLevel(Enum):
    """Niveles de complejidad de código."""

    BASIC = "basic"  # Configuración, utilidades simples
    MEDIUM = "medium"  # Lógica de negocio, integraciones
    ADVANCED = "advanced"  # Algoritmos complejos, ML, sistemas distribuidos


@dataclass
class CodeMetrics:
    """Métricas calculadas del código."""

    lines_of_code: int
    cyclomatic_complexity: int
    num_functions: int
    num_classes: int
    num_imports: int
    has_docstrings: bool
    type_coverage: float  # 0.0 - 1.0
    test_coverage: float  # 0.0 - 1.0
    external_dependencies: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lines_of_code": self.lines_of_code,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "complexity_level": "low"
            if self.cyclomatic_complexity < 5
            else "medium"
            if self.cyclomatic_complexity < 10
            else "high",
            "num_functions": self.num_functions,
            "num_classes": self.num_classes,
            "has_docstrings": self.has_docstrings,
            "type_coverage": f"{self.type_coverage:.0%}",
            "test_coverage": f"{self.test_coverage:.0%}",
        }


@dataclass
class LevelAssignment:
    """Asignación de nivel para una tarea/código."""

    file_path: str
    assigned_level: CodeLevel
    confidence: float  # 0.0 - 1.0
    metrics: CodeMetrics
    reasoning: List[str]
    recommended_crew: str
    sandbox_required: bool
    validation_steps: List[str]


class CodeLevelAnalyzer:
    """Analiza código y determina su nivel de complejidad."""

    def __init__(self):
        self._complexity_thresholds = {
            CodeLevel.BASIC: {"max_lines": 50, "max_complexity": 3, "max_deps": 3},
            CodeLevel.MEDIUM: {"max_lines": 200, "max_complexity": 8, "max_deps": 8},
            CodeLevel.ADVANCED: {
                "max_lines": float("inf"),
                "max_complexity": float("inf"),
                "max_deps": float("inf"),
            },
        }

    def analyze_file(self, file_path: Path) -> CodeMetrics:
        """Analiza un archivo y extrae métricas."""
        if not file_path.exists() or file_path.suffix != ".py":
            return CodeMetrics(0, 0, 0, 0, 0, False, 0.0, 0.0, [])

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            # Análisis AST
            try:
                tree = ast.parse(content)
            except SyntaxError:
                return CodeMetrics(len(lines), 0, 0, 0, 0, False, 0.0, 0.0, [])

            # Contar funciones y clases
            functions = [
                node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            classes = [
                node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
            ]
            imports = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ]

            # Calcular complejidad ciclomática (simplificada)
            complexity = self._calculate_complexity(tree)

            # Verificar docstrings
            has_docs = any(ast.get_docstring(node) for node in functions + classes)

            # Verificar type hints (simplificado)
            type_coverage = self._estimate_type_coverage(tree)

            # Extraer dependencias
            deps = []
            for node in imports:
                if isinstance(node, ast.Import):
                    deps.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    deps.append(node.module)

            return CodeMetrics(
                lines_of_code=len([l for l in lines if l.strip()]),
                cyclomatic_complexity=complexity,
                num_functions=len(functions),
                num_classes=len(classes),
                num_imports=len(imports),
                has_docstrings=has_docs,
                type_coverage=type_coverage,
                test_coverage=0.0,  # Requiere análisis de tests
                external_dependencies=deps,
            )
        except Exception:
            return CodeMetrics(0, 0, 0, 0, 0, False, 0.0, 0.0, [])

    def _calculate_complexity(self, tree: ast.AST) -> int:
        """Calcula complejidad ciclomática simplificada."""
        complexity = 1  # Base

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1

        return complexity

    def _estimate_type_coverage(self, tree: ast.AST) -> float:
        """Estima cobertura de type hints."""
        total_funcs = 0
        typed_funcs = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                total_funcs += 1
                # Verificar anotaciones de retorno y parámetros
                if node.returns:
                    typed_funcs += 1
                elif any(arg.annotation for arg in node.args.args):
                    typed_funcs += 0.5

        return typed_funcs / total_funcs if total_funcs > 0 else 0.0

    def assign_level(
        self, file_path: Path, context: Optional[Dict] = None
    ) -> LevelAssignment:
        """Asigna nivel de complejidad a un archivo."""
        metrics = self.analyze_file(file_path)
        reasoning = []

        # Reglas de asignación
        if metrics.lines_of_code <= 50 and metrics.cyclomatic_complexity <= 3:
            level = CodeLevel.BASIC
            confidence = 0.9
            reasoning.append(f"Código corto ({metrics.lines_of_code} líneas)")
            reasoning.append(f"Baja complejidad ({metrics.cyclomatic_complexity})")
            crew = "config_crew"
            sandbox = False

        elif metrics.lines_of_code <= 200 and metrics.cyclomatic_complexity <= 8:
            level = CodeLevel.MEDIUM
            confidence = 0.8
            reasoning.append(f"Complejidad media ({metrics.cyclomatic_complexity})")
            reasoning.append(f"Tamaño moderado ({metrics.lines_of_code} líneas)")
            crew = "feature_crew"
            sandbox = True

        else:
            level = CodeLevel.ADVANCED
            confidence = 0.85
            reasoning.append(f"Alta complejidad ({metrics.cyclomatic_complexity})")
            reasoning.append(f"Código extenso ({metrics.lines_of_code} líneas)")
            if metrics.num_classes > 0:
                reasoning.append(f"Usa OOP ({metrics.num_classes} clases)")
            crew = "architecture_crew"
            sandbox = True

        # Ajustes adicionales
        validation_steps = ["lint", "typecheck"]
        if level in [CodeLevel.MEDIUM, CodeLevel.ADVANCED]:
            validation_steps.extend(["tests", "security"])

        return LevelAssignment(
            file_path=str(file_path),
            assigned_level=level,
            confidence=confidence,
            metrics=metrics,
            reasoning=reasoning,
            recommended_crew=crew,
            sandbox_required=sandbox,
            validation_steps=validation_steps,
        )


class CrewLevelRouter:
    """Router que asigna tareas a crews basado en nivel de código."""

    def __init__(self):
        self.analyzer = CodeLevelAnalyzer()
        self._crew_configs = {
            "config_crew": {
                "agents": ["config_specialist"],
                "tools": ["file_read", "file_write"],
                "validation": ["syntax_check"],
                "sandbox": False,
            },
            "feature_crew": {
                "agents": ["backend_dev", "tester"],
                "tools": ["code_edit", "test_runner", "git"],
                "validation": ["lint", "tests", "typecheck"],
                "sandbox": True,
            },
            "architecture_crew": {
                "agents": ["architect", "senior_dev", "security_specialist"],
                "tools": [
                    "code_edit",
                    "refactor",
                    "security_scan",
                    "complexity_analyzer",
                ],
                "validation": ["lint", "tests", "typecheck", "security", "performance"],
                "sandbox": True,
            },
        }

    def route_task(self, file_path: Path, task_description: str) -> Dict[str, Any]:
        """Rutea una tarea al crew apropiado."""
        assignment = self.analyzer.assign_level(file_path)
        crew_config = self._crew_configs[assignment.recommended_crew]

        return {
            "file": str(file_path),
            "level": assignment.assigned_level.value,
            "confidence": assignment.confidence,
            "crew": assignment.recommended_crew,
            "agents": crew_config["agents"],
            "tools": crew_config["tools"],
            "sandbox_required": crew_config["sandbox"],
            "validation_steps": crew_config["validation"],
            "reasoning": assignment.reasoning,
            "metrics": assignment.metrics.to_dict(),
            "task": task_description,
        }

    def get_validation_pipeline(self, level: CodeLevel) -> List[str]:
        """Retorna pipeline de validación según nivel."""
        pipelines = {
            CodeLevel.BASIC: ["syntax", "basic_lint"],
            CodeLevel.MEDIUM: ["lint", "typecheck", "unit_tests", "sandbox"],
            CodeLevel.ADVANCED: [
                "lint",
                "typecheck",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "performance",
                "sandbox",
                "review",
            ],
        }
        return pipelines.get(level, ["basic_lint"])


# Integración con el sistema existente


def analyze_project_levels(project_path: Path) -> Dict[str, Any]:
    """Analiza todo un proyecto y asigna niveles."""
    router = CrewLevelRouter()
    results = {
        "basic": [],
        "medium": [],
        "advanced": [],
        "summary": {
            "total_files": 0,
            "basic_count": 0,
            "medium_count": 0,
            "advanced_count": 0,
        },
    }

    for py_file in project_path.rglob("*.py"):
        # Ignorar tests y __pycache__
        if "test" in py_file.name or "__pycache__" in str(py_file):
            continue

        assignment = router.analyzer.assign_level(py_file)
        results["summary"]["total_files"] += 1

        file_info = {
            "path": str(py_file.relative_to(project_path)),
            "metrics": assignment.metrics.to_dict(),
            "reasoning": assignment.reasoning,
        }

        if assignment.assigned_level == CodeLevel.BASIC:
            results["basic"].append(file_info)
            results["summary"]["basic_count"] += 1
        elif assignment.assigned_level == CodeLevel.MEDIUM:
            results["medium"].append(file_info)
            results["summary"]["medium_count"] += 1
        else:
            results["advanced"].append(file_info)
            results["summary"]["advanced_count"] += 1

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        project = Path(sys.argv[1])
    else:
        project = Path.cwd()

    print(f"🔍 Analizando niveles de código en: {project}")
    print("=" * 70)

    results = analyze_project_levels(project)

    print(f"\n📊 Resumen:")
    print(f"  Total archivos: {results['summary']['total_files']}")
    print(f"  🟢 Básico: {results['summary']['basic_count']}")
    print(f"  🟡 Medio: {results['summary']['medium_count']}")
    print(f"  🔴 Avanzado: {results['summary']['advanced_count']}")

    for level, files in [
        ("Básico", results["basic"]),
        ("Medio", results["medium"]),
        ("Avanzado", results["advanced"]),
    ]:
        if files:
            print(f"\n{level}:")
            for f in files[:5]:  # Mostrar primeros 5
                print(f"  - {f['path']}")
            if len(files) > 5:
                print(f"  ... y {len(files) - 5} más")
