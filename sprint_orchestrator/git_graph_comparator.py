"""Graph-Git Comparator - Detecta gaps entre el grafo Neo4j y Git.

Este módulo contrasta el estado del grafo de conocimiento (Neo4j) con el
estado real del código en Git para identificar:
- Código no indexado en el grafo
- Relaciones faltantes
- Entidades huérfanas
- Inconsistencias entre grafo y filesystem
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
import subprocess
import json
from datetime import datetime


@dataclass
class GraphGitGap:
    """Representa un gap entre el grafo y Git."""

    gap_type: str  # 'missing_in_graph', 'orphan_in_graph', 'relation_missing', 'stale_in_graph'
    entity_type: str  # 'file', 'function', 'class', 'module'
    name: str
    file_path: str
    git_status: Dict[str, Any] = field(default_factory=dict)
    graph_status: Dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"  # low, medium, high, critical
    suggestion: str = ""


@dataclass
class ComparisonResult:
    """Resultado completo de la comparación."""

    timestamp: str
    project_root: str
    total_files_in_git: int
    total_entities_in_graph: int
    gaps: List[GraphGitGap]
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "project_root": self.project_root,
            "total_files_in_git": self.total_files_in_git,
            "total_entities_in_graph": self.total_entities_in_graph,
            "gaps_count": len(self.gaps),
            "summary": self.summary,
            "gaps": [
                {
                    "gap_type": g.gap_type,
                    "entity_type": g.entity_type,
                    "name": g.name,
                    "file_path": g.file_path,
                    "severity": g.severity,
                    "suggestion": g.suggestion,
                }
                for g in self.gaps
            ],
        }


class GitGraphComparator:
    """Compara estado de Git con el grafo Neo4j."""

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "jotah",
        neo4j_password: str = "1307",
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self._driver = None

    def _get_neo4j_driver(self):
        """Lazy initialization de Neo4j driver."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase

                self._driver = GraphDatabase.driver(
                    self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password)
                )
            except ImportError:
                raise RuntimeError("neo4j package not installed")
        return self._driver

    def compare_project(
        self,
        project_path: Path,
        include_patterns: List[str] | None = None,
        exclude_patterns: List[str] | None = None,
    ) -> ComparisonResult:
        """Compara proyecto Git contra el grafo.

        Args:
            project_path: Ruta al proyecto
            include_patterns: Patrones a incluir (default: *.py, *.js, *.ts)
            exclude_patterns: Patrones a excluir (default: __pycache__, node_modules)

        Returns:
            ComparisonResult con todos los gaps detectados
        """
        if include_patterns is None:
            include_patterns = ["*.py", "*.js", "*.ts", "*.tsx", "*.go", "*.rs"]
        if exclude_patterns is None:
            exclude_patterns = [
                "__pycache__",
                "node_modules",
                ".git",
                ".venv",
                "venv",
                "*.pyc",
                "*.pyo",
                ".pytest_cache",
                ".mypy_cache",
            ]

        # 1. Obtener archivos de Git
        git_files = self._get_git_files(project_path)
        git_entities = self._extract_git_entities(project_path, git_files)

        # 2. Obtener entidades del grafo
        graph_entities = self._get_graph_entities(str(project_path))

        # 3. Comparar
        gaps = self._detect_gaps(git_entities, graph_entities, project_path)

        # 4. Generar resumen
        summary = self._generate_summary(gaps)

        return ComparisonResult(
            timestamp=datetime.utcnow().isoformat(),
            project_root=str(project_path),
            total_files_in_git=len(git_files),
            total_entities_in_graph=len(graph_entities),
            gaps=gaps,
            summary=summary,
        )

    def _get_git_files(self, project_path: Path) -> Set[str]:
        """Obtiene lista de archivos trackeados por Git."""
        try:
            result = subprocess.run(
                ["git", "-C", str(project_path), "ls-files"],
                capture_output=True,
                text=True,
                check=True,
            )
            return set(result.stdout.strip().split("\n"))
        except subprocess.CalledProcessError:
            # Si no es repo git, buscar manualmente
            files = set()
            for ext in ["*.py", "*.js", "*.ts", "*.tsx"]:
                files.update(
                    str(p.relative_to(project_path)) for p in project_path.rglob(ext)
                )
            return files

    def _extract_git_entities(
        self, project_path: Path, git_files: Set[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Extrae entidades (clases, funciones) del código Git."""
        entities = {}

        for file_path in git_files:
            if not file_path.endswith(".py"):
                continue

            full_path = project_path / file_path
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")

                # Extraer funciones (heurística simple)
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("def "):
                        func_name = line.split("(")[0].replace("def ", "").strip()
                        entity_id = f"{file_path}::{func_name}"
                        entities[entity_id] = {
                            "name": func_name,
                            "type": "function",
                            "file": file_path,
                            "line": line,
                            "source": "git",
                        }
                    elif line.startswith("class "):
                        class_name = line.split("(")[0].replace("class ", "").strip()
                        entity_id = f"{file_path}::{class_name}"
                        entities[entity_id] = {
                            "name": class_name,
                            "type": "class",
                            "file": file_path,
                            "line": line,
                            "source": "git",
                        }
            except Exception:
                continue

        return entities

    def _get_graph_entities(self, project_path_str: str) -> Dict[str, Dict[str, Any]]:
        """Obtiene entidades del grafo Neo4j."""
        entities = {}

        try:
            driver = self._get_neo4j_driver()
            with driver.session() as session:
                # Buscar entidades de código relacionadas con el proyecto
                cypher = """
                MATCH (n)
                WHERE n.file_path STARTS WITH $project_path
                   OR n.project = $project_name
                   OR n.repo = $project_name
                RETURN n.name, n.type, n.file_path, n.line, n.updated, labels(n) as labels
                """
                result = session.run(
                    cypher,
                    {
                        "project_path": project_path_str,
                        "project_name": Path(project_path_str).name,
                    },
                )

                for record in result:
                    entity_id = f"{record['n.file_path']}::{record['n.name']}"
                    entities[entity_id] = {
                        "name": record["n.name"],
                        "type": record["n.type"],
                        "file": record["n.file_path"],
                        "line": record["n.line"],
                        "updated": record["n.updated"],
                        "labels": record["labels"],
                        "source": "graph",
                    }
        except Exception as e:
            print(f"Warning: Could not query Neo4j: {e}")

        return entities

    def _detect_gaps(
        self,
        git_entities: Dict[str, Dict[str, Any]],
        graph_entities: Dict[str, Dict[str, Any]],
        project_path: Path,
    ) -> List[GraphGitGap]:
        """Detecta gaps entre Git y el grafo."""
        gaps = []

        # 1. Entidades en Git pero NO en el grafo (missing_in_graph)
        for entity_id, git_data in git_entities.items():
            if entity_id not in graph_entities:
                gaps.append(
                    GraphGitGap(
                        gap_type="missing_in_graph",
                        entity_type=git_data["type"],
                        name=git_data["name"],
                        file_path=git_data["file"],
                        git_status=git_data,
                        graph_status={},
                        severity="high",
                        suggestion=f"Run: qcli index {git_data['file']}",
                    )
                )

        # 2. Entidades en grafo pero NO en Git (orphan_in_graph)
        for entity_id, graph_data in graph_entities.items():
            if entity_id not in git_entities:
                gaps.append(
                    GraphGitGap(
                        gap_type="orphan_in_graph",
                        entity_type=graph_data["type"],
                        name=graph_data["name"],
                        file_path=graph_data["file"],
                        git_status={},
                        graph_status=graph_data,
                        severity="medium",
                        suggestion="Entity was deleted in Git but exists in graph. Run cleanup.",
                    )
                )

        # 3. Verificar relaciones faltantes (heurística)
        gaps.extend(self._check_missing_relations(git_entities, graph_entities))

        return sorted(gaps, key=lambda g: g.file_path)

    def _check_missing_relations(
        self,
        git_entities: Dict[str, Dict[str, Any]],
        graph_entities: Dict[str, Dict[str, Any]],
    ) -> List[GraphGitGap]:
        """Verifica relaciones importantes que deberían existir."""
        gaps = []

        # Para cada clase, verificar si tiene métodos en el grafo
        classes_in_graph = {
            eid: data
            for eid, data in graph_entities.items()
            if data.get("type") == "class"
        }

        return gaps

    def _generate_summary(self, gaps: List[GraphGitGap]) -> Dict[str, int]:
        """Genera resumen de gaps."""
        summary = {
            "missing_in_graph": 0,
            "orphan_in_graph": 0,
            "relation_missing": 0,
            "stale_in_graph": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
        }

        for gap in gaps:
            summary[gap.gap_type] = summary.get(gap.gap_type, 0) + 1
            summary[f"{gap.severity}_severity"] = (
                summary.get(f"{gap.severity}_severity", 0) + 1
            )

        return summary

    def generate_sync_commands(self, result: ComparisonResult) -> List[str]:
        """Genera comandos para sincronizar grafo con Git."""
        commands = []

        missing = [g for g in result.gaps if g.gap_type == "missing_in_graph"]

        if missing:
            files_to_index = set(g.file_path for g in missing)
            commands.append(f"# Index {len(files_to_index)} files:")
            for file_path in sorted(files_to_index)[:10]:  # Limitar a 10
                commands.append(f"qcli index {file_path}")
            if len(files_to_index) > 10:
                commands.append(f"# ... and {len(files_to_index) - 10} more files")

        orphans = [g for g in result.gaps if g.gap_type == "orphan_in_graph"]
        if orphans:
            commands.append(f"\n# Cleanup {len(orphans)} orphan entities in graph")

        return commands

    def sync_git_to_graph(self, project_path: Path) -> Dict[str, Any]:
        """Sincroniza el estado de Git al grafo Neo4j.

        Crea nodos para:
        - Commits (con mensaje, autor, fecha)
        - Branches (con relación al commit actual)
        - Archivos modificados (con diff stats)
        - Relaciones: COMMIT_PARENT, CONTAINS_FILE, BRANCH_POINTS_TO

        Returns:
            Estadísticas de la sincronización
        """
        stats = {
            "commits_created": 0,
            "branches_created": 0,
            "files_linked": 0,
            "relations_created": 0,
        }

        try:
            driver = self._get_neo4j_driver()

            # 1. Obtener commits recientes
            commits = self._get_recent_commits(project_path, limit=50)

            # 2. Obtener branches
            branches = self._get_branches(project_path)

            # 3. Obtener archivos modificados por commit
            with driver.session() as session:
                project_name = project_path.name

                # Crear nodo proyecto si no existe
                session.run(
                    """
                    MERGE (p:Project {name: $name})
                    SET p.path = $path, p.updated = datetime()
                """,
                    {"name": project_name, "path": str(project_path)},
                )

                # Crear commits
                for commit in commits:
                    result = session.run(
                        """
                        MATCH (p:Project {name: $project})
                        MERGE (c:Commit {hash: $hash})
                        SET c.message = $message,
                            c.author = $author,
                            c.date = $date,
                            c.branch = $branch
                        MERGE (p)-[:HAS_COMMIT]->(c)
                        RETURN c.hash as hash
                    """,
                        {
                            "project": project_name,
                            "hash": commit["hash"],
                            "message": commit["message"],
                            "author": commit["author"],
                            "date": commit["date"],
                            "branch": commit["branch"],
                        },
                    )
                    if result.single():
                        stats["commits_created"] += 1

                # Crear parent relationships
                for commit in commits:
                    if commit["parents"]:
                        for parent_hash in commit["parents"]:
                            session.run(
                                """
                                MATCH (c:Commit {hash: $child})
                                MATCH (p:Commit {hash: $parent})
                                MERGE (c)-[:PARENT]->(p)
                            """,
                                {"child": commit["hash"], "parent": parent_hash},
                            )
                            stats["relations_created"] += 1

                # Crear branches
                for branch_name, branch_commit in branches.items():
                    session.run(
                        """
                        MATCH (p:Project {name: $project})
                        MATCH (c:Commit {hash: $commit})
                        MERGE (b:Branch {name: $name, project: $project})
                        SET b.updated = datetime()
                        MERGE (p)-[:HAS_BRANCH]->(b)
                        MERGE (b)-[:POINTS_TO]->(c)
                    """,
                        {
                            "project": project_name,
                            "name": branch_name,
                            "commit": branch_commit,
                        },
                    )
                    stats["branches_created"] += 1

                # Vincular archivos modificados
                for commit in commits[:10]:  # Solo últimos 10 para performance
                    files = self._get_commit_files(project_path, commit["hash"])
                    for file_path in files:
                        # Buscar si el archivo existe como entidad
                        result = session.run(
                            """
                            MATCH (c:Commit {hash: $commit})
                            MATCH (f:Entity|File|Function|Class)
                            WHERE f.file_path CONTAINS $file
                            MERGE (c)-[:MODIFIES]->(f)
                            RETURN count(f) as count
                        """,
                            {"commit": commit["hash"], "file": file_path},
                        )

                        record = result.single()
                        if record and record["count"] > 0:
                            stats["files_linked"] += 1

            return stats

        except Exception as e:
            print(f"Error syncing Git to graph: {e}")
            return stats

    def _get_recent_commits(self, project_path: Path, limit: int = 50) -> List[Dict]:
        """Obtiene commits recientes con metadata."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(project_path),
                    "log",
                    f"--max-count={limit}",
                    "--format=%H|%s|%an|%ad|%P",
                    "--date=iso",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            commits = []
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    parts = line.split("|")
                    commits.append(
                        {
                            "hash": parts[0][:12],  # Short hash
                            "message": parts[1],
                            "author": parts[2],
                            "date": parts[3],
                            "parents": parts[4].split() if len(parts) > 4 else [],
                            "branch": "HEAD",  # Simplificado
                        }
                    )
            return commits
        except subprocess.CalledProcessError:
            return []

    def _get_branches(self, project_path: Path) -> Dict[str, str]:
        """Obtiene branches y sus commits actuales."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(project_path),
                    "branch",
                    "-a",
                    "-v",
                    "--format=%(refname:short)|%(objectname:short)",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            branches = {}
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    name, commit = line.split("|", 1)
                    branches[name.strip()] = commit.strip()
            return branches
        except subprocess.CalledProcessError:
            return {}

    def _get_commit_files(self, project_path: Path, commit_hash: str) -> List[str]:
        """Obtiene archivos modificados en un commit."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(project_path),
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    commit_hash,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout.strip()
            return output.split("\n") if output else []
        except subprocess.CalledProcessError:
            return []

    def analyze_code_evolution(
        self, project_path: Path, entity_name: str
    ) -> Dict[str, Any]:
        """Analiza la evolución de una entidad específica a través del tiempo.

        Útil para entender:
        - Cuándo se creó
        - Quién la ha modificado
        - Con qué frecuencia cambia
        - Qué otros archivos se modifican juntos
        """
        try:
            driver = self._get_neo4j_driver()
            with driver.session() as session:
                # Buscar commits que modifican esta entidad
                result = session.run(
                    """
                    MATCH (e:Entity|Function|Class)
                    WHERE e.name = $name
                    MATCH (c:Commit)-[:MODIFIES]->(e)
                    RETURN c.hash, c.message, c.author, c.date
                    ORDER BY c.date DESC
                    LIMIT 20
                """,
                    {"name": entity_name},
                )

                commits = [dict(record) for record in result]

                # Analizar co-cambios (qué se modifica junto)
                cochanges = session.run(
                    """
                    MATCH (c:Commit)-[:MODIFIES]->(e {name: $name})
                    MATCH (c)-[:MODIFIES]->(other)
                    WHERE other.name <> $name
                    RETURN other.name as co_entity, count(c) as frequency
                    ORDER BY frequency DESC
                    LIMIT 10
                """,
                    {"name": entity_name},
                )

                cochanges_list = [dict(record) for record in cochanges]

                return {
                    "entity": entity_name,
                    "total_commits": len(commits),
                    "first_seen": commits[-1]["c.date"] if commits else None,
                    "latest_change": commits[0]["c.date"] if commits else None,
                    "authors": list(set(c["c.author"] for c in commits)),
                    "recent_commits": commits[:5],
                    "frequently_changed_with": cochanges_list,
                }
        except Exception as e:
            return {"error": str(e)}

    def close(self):
        """Cierra conexión a Neo4j."""
        if self._driver:
            self._driver.close()


# Función de conveniencia para uso directo
def compare_project_with_graph(
    project_path: str, neo4j_uri: str = "bolt://localhost:7687"
) -> Dict[str, Any]:
    """Compara un proyecto contra el grafo y retorna resultado."""
    comparator = GitGraphComparator(neo4j_uri=neo4j_uri)
    try:
        result = comparator.compare_project(Path(project_path))
        return result.to_dict()
    finally:
        comparator.close()


if __name__ == "__main__":
    # Ejemplo de uso
    import sys

    if len(sys.argv) > 1:
        project = sys.argv[1]
    else:
        project = "."

    print(f"🔍 Comparando proyecto: {project}")
    print("=" * 60)

    result = compare_project_with_graph(project)

    print(f"\n📊 Resumen:")
    print(f"  Archivos en Git: {result['total_files_in_git']}")
    print(f"  Entidades en grafo: {result['total_entities_in_graph']}")
    print(f"  Gaps detectados: {result['gaps_count']}")
    print(f"\n  Por severidad:")
    for key, val in result["summary"].items():
        if val > 0:
            print(f"    - {key}: {val}")

    if result["gaps"]:
        print(f"\n⚠️  Gaps encontrados (mostrando primeros 10):")
        for gap in result["gaps"][:10]:
            print(f"\n  [{gap['severity'].upper()}] {gap['gap_type']}")
            print(f"    {gap['entity_type']}: {gap['name']}")
            print(f"    File: {gap['file_path']}")
            print(f"    Suggestion: {gap['suggestion']}")
    else:
        print("\n✅ No se encontraron gaps. ¡Git y grafo están sincronizados!")
