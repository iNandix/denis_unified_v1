"""Atlas Git-Graph Integration - Validación automatizada de commits.

Integra Atlas (sistema de gestión de conocimiento) con Git y el grafo Neo4j
para crear un pipeline de validación automatizada que:

1. Detecta cambios en el filesystem
2. Valida contra el grafo de conocimiento
3. Bloquea commits de baja calidad (placeholders, stubs)
4. Automatiza commits válidos con contexto enriquecido
5. Garantiza que el proyecto avanza (sin código huérfano)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import subprocess
import json
import hashlib

from git_graph_comparator import GitGraphComparator, GraphGitGap
import re


@dataclass
class ValidationResult:
    """Resultado de validación de un commit propuesto."""

    passed: bool
    commit_hash: str
    commit_message: str
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    auto_commit_message: str = ""


@dataclass
class AtlasValidationConfig:
    """Configuración para validación Atlas."""

    # Validación de calidad
    block_placeholders: bool = True
    block_stubs: bool = True
    block_missing_tests: bool = True

    # Umbral de cobertura del grafo
    min_graph_coverage: float = 0.8  # 80% de entidades deben estar en el grafo

    # Auto-commit
    auto_commit_enabled: bool = False  # Requiere aprobación explícita
    auto_commit_prefix: str = "[auto]"

    # Validación de avance
    ensure_no_orphans: bool = True
    check_related_entities: bool = True

    # Integración
    neo4j_uri: str = "bolt://localhost:7687"
    project_path: Path = field(default_factory=lambda: Path.cwd())


class AtlasGitValidator:
    """Validador automatizado que integra Atlas, Git y el Grafo.

    Esta clase actúa como puerta de enlace entre:
    - El filesystem (Git)
    - El grafo de conocimiento (Neo4j)
    - El sistema de validación (ChangeGuard + análisis estático)

    Flujo:
    1. Detectar cambios staged en Git
    2. Comparar con el grafo (¿qué entidades son nuevas/modificadas?)
    3. Validar calidad (placeholders, stubs, tests faltantes)
    4. Verificar avance (¿conecta con el grafo existente?)
    5. Sugerir o auto-generar mensaje de commit enriquecido
    6. Permitir o bloquear el commit
    """

    def __init__(self, config: Optional[AtlasValidationConfig] = None):
        self.config = config or AtlasValidationConfig()
        self.comparator = GitGraphComparator(neo4j_uri=self.config.neo4j_uri)
        self._placeholder_patterns = [
            r"TODO|FIXME|XXX|HACK",
            r"pass\s*$",  # Funciones vacías
            r"NotImplementedError",
            r"raise\s+Exception.*not.*implemented",
            r"stub|placeholder|mock.*only",
        ]

    def validate_staged_changes(self) -> ValidationResult:
        """Valida cambios staged para commit.

        Este es el método principal que se ejecuta como pre-commit hook.

        Returns:
            ValidationResult con decisión de permitir/bloquear commit
        """
        project_path = self.config.project_path

        # 1. Obtener archivos staged
        staged_files = self._get_staged_files(project_path)
        if not staged_files:
            return ValidationResult(
                passed=False,
                commit_hash="",
                commit_message="No hay archivos staged para commit",
            )

        violations = []
        warnings = []
        suggestions = []
        context = {
            "staged_files": staged_files,
            "new_entities": [],
            "modified_entities": [],
            "graph_coverage": 0.0,
        }

        # 2. Analizar cada archivo staged
        for file_path in staged_files:
            file_violations = self._analyze_file_quality(project_path / file_path)
            violations.extend(file_violations)

        # 3. Comparar con el grafo
        comparison = self.comparator.compare_project(project_path)

        # Verificar cobertura del grafo
        if comparison.total_files_in_git > 0:
            coverage = (
                comparison.total_entities_in_graph / comparison.total_files_in_git
            )
            context["graph_coverage"] = coverage

            if coverage < self.config.min_graph_coverage:
                violations.append(
                    f"Cobertura del grafo muy baja: {coverage:.1%} "
                    f"(mínimo requerido: {self.config.min_graph_coverage:.1%})"
                )

        # 4. Detectar gaps críticos
        critical_gaps = [
            g
            for g in comparison.gaps
            if g.severity in ["critical", "high"] and g.gap_type == "missing_in_graph"
        ]

        for gap in critical_gaps:
            if self.config.ensure_no_orphans:
                warnings.append(
                    f"Entidad '{gap.name}' no está en el grafo. "
                    f"Sugerencia: {gap.suggestion}"
                )

        # 5. Verificar que el cambio conecta con el grafo
        if self.config.check_related_entities:
            related = self._find_related_entities(staged_files)
            if not related:
                warnings.append(
                    "El cambio no parece conectar con entidades existentes en el grafo. "
                    "¿Estás creando código aislado?"
                )
            else:
                context["related_entities"] = related

        # 6. Generar mensaje de commit enriquecido
        auto_message = self._generate_commit_message(staged_files, comparison, context)

        # Decisión final
        passed = len(violations) == 0

        return ValidationResult(
            passed=passed,
            commit_hash=self._get_staged_commit_hash(project_path),
            commit_message=auto_message,
            violations=violations,
            warnings=warnings,
            suggestions=suggestions,
            context=context,
            auto_commit_message=auto_message if passed else "",
        )

    def auto_commit(self, validation: ValidationResult) -> bool:
        """Ejecuta commit automatizado si la validación pasó.

        Args:
            validation: Resultado de validación (debe haber pasado)

        Returns:
            True si el commit fue exitoso
        """
        if not validation.passed:
            print("❌ Validación falló. No se puede hacer auto-commit.")
            return False

        if not self.config.auto_commit_enabled:
            print("⚠️ Auto-commit deshabilitado en configuración.")
            print(f"Mensaje sugerido: {validation.auto_commit_message}")
            return False

        try:
            # Hacer commit con el mensaje enriquecido
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.config.project_path),
                    "commit",
                    "-m",
                    validation.auto_commit_message,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"✅ Auto-commit exitoso: {result.stdout}")

            # Opcional: sincronizar con el grafo
            self.comparator.sync_git_to_graph(self.config.project_path)

            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error en auto-commit: {e.stderr}")
            return False

    def _get_staged_files(self, project_path: Path) -> List[str]:
        """Obtiene lista de archivos staged para commit."""
        try:
            result = subprocess.run(
                ["git", "-C", str(project_path), "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                check=True,
            )
            return [f for f in result.stdout.strip().split("\n") if f]
        except subprocess.CalledProcessError:
            return []

    def _get_staged_commit_hash(self, project_path: Path) -> str:
        """Obtiene hash del commit staged (si existe)."""
        try:
            result = subprocess.run(
                ["git", "-C", str(project_path), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"

    def _analyze_file_quality(self, file_path: Path) -> List[str]:
        """Analiza calidad de un archivo buscando placeholders/stubs."""
        violations = []

        if not file_path.exists() or not file_path.suffix == ".py":
            return violations

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Verificar patrones de placeholder
                if self.config.block_placeholders:
                    import re

                    for pattern in self._placeholder_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            violations.append(
                                f"{file_path}:{i}: Posible placeholder/stub detectado: {line.strip()[:50]}"
                            )
                            break

                # Verificar funciones vacías (solo pass)
                if self.config.block_stubs:
                    if re.search(r"^\s*def\s+\w+.*:\s*$", line):
                        # Revisar siguiente línea
                        if i < len(lines) and re.search(r"^\s*pass\s*$", lines[i]):
                            violations.append(
                                f"{file_path}:{i}: Función vacía con 'pass' detectada"
                            )
        except Exception:
            pass

        return violations

    def _find_related_entities(self, staged_files: List[str]) -> List[Dict[str, Any]]:
        """Busca entidades relacionadas en el grafo."""
        related = []

        try:
            driver = self.comparator._get_neo4j_driver()
            with driver.session() as session:
                # Buscar entidades que importan o son importadas por los archivos staged
                for file_path in staged_files[:5]:  # Limitar a 5 archivos
                    result = session.run(
                        """
                        MATCH (f:File|Entity)
                        WHERE f.file_path CONTAINS $file
                        OPTIONAL MATCH (f)-[:IMPORTS|USES|CALLS]->(related)
                        RETURN f.name as entity, f.type as type, 
                               collect(related.name) as related_names
                        LIMIT 5
                    """,
                        {"file": Path(file_path).name},
                    )

                    for record in result:
                        related.append(
                            {
                                "entity": record["entity"],
                                "type": record["type"],
                                "related_to": record["related_names"][:5],
                            }
                        )
        except Exception:
            pass

        return related

    def _generate_commit_message(
        self, staged_files: List[str], comparison: Any, context: Dict[str, Any]
    ) -> str:
        """Genera mensaje de commit enriquecido con contexto del grafo.

        El mensaje incluye:
        - Tipo de cambio (feat/fix/docs)
        - Entidades afectadas
        - Conexiones con el grafo
        - Cobertura de entidades
        """
        # Determinar tipo de cambio
        change_type = "feat"
        if any("fix" in f.lower() or "bug" in f.lower() for f in staged_files):
            change_type = "fix"
        elif any("test" in f.lower() for f in staged_files):
            change_type = "test"
        elif any("doc" in f.lower() for f in staged_files):
            change_type = "docs"

        # Extraer entidades modificadas
        entities = []
        for gap in comparison.gaps[:3]:
            if gap.gap_type == "missing_in_graph":
                entities.append(gap.name)

        # Construir mensaje
        prefix = (
            f"{self.config.auto_commit_prefix} "
            if self.config.auto_commit_enabled
            else ""
        )

        message_parts = [f"{prefix}{change_type}: update"]

        if entities:
            message_parts.append(f"({', '.join(entities)})")

        # Agregar archivos
        files_str = ", ".join(Path(f).name for f in staged_files[:3])
        if len(staged_files) > 3:
            files_str += f" +{len(staged_files) - 3} more"
        message_parts.append(f"[{files_str}]")

        # Agregar contexto del grafo
        coverage = context.get("graph_coverage", 0)
        message_parts.append(f"[graph: {coverage:.0%} covered]")

        return " ".join(message_parts)

    def check_project_health(self) -> Dict[str, Any]:
        """Verifica salud general del proyecto.

        Útil para ejecutar periódicamente y asegurar que el proyecto avanza.

        Returns:
            Reporte de salud con métricas y recomendaciones
        """
        project_path = self.config.project_path

        print("🔍 Verificando salud del proyecto...")
        print("=" * 70)

        # 1. Comparación completa
        comparison = self.comparator.compare_project(project_path)

        # 2. Estadísticas
        health_score = 100
        issues = []

        # Penalizar por gaps críticos
        critical_count = sum(1 for g in comparison.gaps if g.severity == "critical")
        if critical_count > 0:
            health_score -= critical_count * 10
            issues.append(f"{critical_count} gaps críticos detectados")

        # Penalizar por baja cobertura
        if comparison.total_files_in_git > 0:
            coverage = (
                comparison.total_entities_in_graph / comparison.total_files_in_git
            )
            if coverage < 0.5:
                health_score -= 20
                issues.append(f"Cobertura muy baja: {coverage:.1%}")
            elif coverage < 0.8:
                health_score -= 10
                issues.append(f"Cobertura baja: {coverage:.1%}")

        # Penalizar por orphans
        orphan_count = sum(
            1 for g in comparison.gaps if g.gap_type == "orphan_in_graph"
        )
        if orphan_count > 10:
            health_score -= 15
            issues.append(f"{orphan_count} entidades huérfanas en el grafo")

        health_score = max(0, health_score)

        # 3. Recomendaciones
        recommendations = []
        if health_score < 50:
            recommendations.append(
                "🚨 Prioridad alta: Sincronizar Git con el grafo inmediatamente"
            )
        if critical_count > 0:
            recommendations.append(
                "⚠️ Resolver gaps críticos antes de continuar desarrollo"
            )
        if coverage < 0.8:
            recommendations.append("💡 Ejecutar: qcli index --project .")

        return {
            "health_score": health_score,
            "status": "healthy"
            if health_score >= 80
            else "degraded"
            if health_score >= 50
            else "critical",
            "total_gaps": len(comparison.gaps),
            "critical_gaps": critical_count,
            "orphan_entities": orphan_count,
            "graph_coverage": comparison.total_entities_in_graph
            / max(comparison.total_files_in_git, 1),
            "issues": issues,
            "recommendations": recommendations,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def close(self):
        """Cierra conexiones."""
        self.comparator.close()


# Funciones de conveniencia para CLI


def install_git_hook(project_path: Path) -> bool:
    """Instala el validador como pre-commit hook.

    Args:
        project_path: Ruta al proyecto Git

    Returns:
        True si se instaló correctamente
    """
    hook_path = project_path / ".git" / "hooks" / "pre-commit"

    hook_content = """#!/bin/bash
# Atlas Git-Graph Validator Pre-commit Hook

echo "🔍 Validando cambios con Atlas..."

python3 "{sprint_orchestrator}/atlas_git_validator.py" --check-staged

exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo "❌ Validación falló. Commit cancelado."
    echo "   Corre los issues o usa --no-verify para saltar (no recomendado)"
    exit 1
fi

echo "✅ Validación pasada. Procediendo con commit..."
exit 0
""".format(sprint_orchestrator=Path(__file__).parent)

    try:
        hook_path.write_text(hook_content)
        hook_path.chmod(0o755)
        print(f"✅ Pre-commit hook instalado en: {hook_path}")
        return True
    except Exception as e:
        print(f"❌ Error instalando hook: {e}")
        return False


if __name__ == "__main__":
    # Ejemplo de uso
    import sys

    config = AtlasValidationConfig(
        project_path=Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd(),
        auto_commit_enabled=False,  # Siempre manual por seguridad
    )

    validator = AtlasGitValidator(config)

    try:
        # Validar cambios staged
        result = validator.validate_staged_changes()

        print("\n" + "=" * 70)
        print(f"Resultado de validación: {'✅ PASÓ' if result.passed else '❌ FALLÓ'}")
        print("=" * 70)

        if result.violations:
            print(f"\n🚫 Violaciones ({len(result.violations)}):")
            for v in result.violations:
                print(f"   - {v}")

        if result.warnings:
            print(f"\n⚠️  Advertencias ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"   - {w}")

        if result.passed:
            print(f"\n💬 Mensaje de commit sugerido:")
            print(f"   {result.auto_commit_message}")

            print(f"\n📊 Contexto:")
            print(
                f"   Cobertura del grafo: {result.context.get('graph_coverage', 0):.1%}"
            )
            if "related_entities" in result.context:
                print(
                    f"   Entidades relacionadas: {len(result.context['related_entities'])}"
                )

        sys.exit(0 if result.passed else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Validación cancelada")
        sys.exit(130)
    finally:
        validator.close()
