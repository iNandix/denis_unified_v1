"""
Celery + Redis Backend para Workers Denis
MVP de procesamiento paralelo
"""

from celery import Celery, group, chain
from celery.result import GroupResult
import json
import os

# Configuración Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Inicializar Celery
app = Celery("denis_workers", broker=REDIS_URL, backend=REDIS_URL)

# Configuración
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 min max por tarea
    worker_prefetch_multiplier=1,  # Fair scheduling
)

# ============================================================================
# WORKER 1: SEARCH
# ============================================================================


@app.task(bind=True, name="workers.search")
def worker_search(self, query: str, intent: str, session_id: str):
    """
    Worker de búsqueda - Busca símbolos y contexto.
    """
    self.update_state(state="STARTED", meta={"step": "connecting_neo4j"})

    try:
        from kernel.ghostide.symbolgraph import SymbolGraph

        graph = SymbolGraph()

        # Buscar símbolos relevantes
        symbols = graph.find_symbols_by_intent(intent, limit=20)

        # Buscar en vector store
        self.update_state(state="PROGRESS", meta={"step": "semantic_search"})
        related = graph.semantic_search(query, limit=10)

        result = {
            "worker": "SEARCH",
            "symbols_found": len(symbols),
            "symbols": [{"name": s.name, "file": s.file, "type": s.kind} for s in symbols],
            "related_files": [r.file for r in related],
            "status": "completed",
        }

        # Persistir en grafo
        _persist_worker_result(self.request.id, "SEARCH", result, session_id)

        return result

    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise


# ============================================================================
# WORKER 2: ANALYSIS
# ============================================================================


@app.task(bind=True, name="workers.analysis")
def worker_analysis(self, files: list, intent: str, session_id: str):
    """
    Worker de análisis - Analiza código y dependencias.
    """
    self.update_state(state="STARTED", meta={"step": "reading_files"})

    try:
        from kernel.ghostide.symbolgraph import SymbolGraph

        graph = SymbolGraph()
        analysis = {"files_analyzed": 0, "dependencies": [], "complexity_score": 0, "issues": []}

        for file in files:
            self.update_state(
                state="PROGRESS",
                meta={
                    "step": f"analyzing_{file}",
                    "progress": f"{analysis['files_analyzed']}/{len(files)}",
                },
            )

            # Analizar archivo
            deps = graph.get_file_dependencies(file)
            analysis["dependencies"].extend(deps)
            analysis["files_analyzed"] += 1

        result = {
            "worker": "ANALYSIS",
            "files_analyzed": analysis["files_analyzed"],
            "dependencies_found": len(analysis["dependencies"]),
            "complexity": analysis["complexity_score"],
            "issues": analysis["issues"][:5],  # Top 5 issues
            "status": "completed",
        }

        _persist_worker_result(self.request.id, "ANALYSIS", result, session_id)

        return result

    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise


# ============================================================================
# WORKER 3: CREATE
# ============================================================================


@app.task(bind=True, name="workers.create")
def worker_create(self, spec: dict, context: dict, session_id: str):
    """
    Worker de creación - Genera código nuevo.
    """
    self.update_state(state="STARTED", meta={"step": "generating"})

    try:
        # Generar código basado en spec
        files_created = []

        for file_spec in spec.get("files", []):
            self.update_state(state="PROGRESS", meta={"step": f"creating_{file_spec['name']}"})

            # Crear archivo
            content = _generate_file_content(file_spec, context)
            files_created.append(
                {
                    "name": file_spec["name"],
                    "path": file_spec.get("path", ""),
                    "content_length": len(content),
                }
            )

        result = {
            "worker": "CREATE",
            "files_created": len(files_created),
            "files": files_created,
            "status": "completed",
        }

        _persist_worker_result(self.request.id, "CREATE", result, session_id)

        return result

    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise


# ============================================================================
# WORKER 4: MODIFY
# ============================================================================


@app.task(bind=True, name="workers.modify")
def worker_modify(self, changes: list, validation: bool, session_id: str):
    """
    Worker de modificación - Aplica cambios atómicos.
    """
    self.update_state(state="STARTED", meta={"step": "preparing"})

    try:
        from denis_unified_v1.atlas.atlas_fork import AtlasFork

        atlas = AtlasFork()
        applied_changes = []

        for i, change in enumerate(changes):
            self.update_state(
                state="PROGRESS",
                meta={"step": f"applying_change_{i + 1}", "progress": f"{i + 1}/{len(changes)}"},
            )

            # Aplicar cambio con Atlas (backup + patch + validate)
            result = atlas.atomic_refactor(
                files=change["files"],
                pattern=change["pattern"],
                replacement=change["replacement"],
                create_backup=True,
                validate_with_lsp=validation,
            )

            applied_changes.append(
                {
                    "files": change["files"],
                    "success": result.success,
                    "backup_created": result.backup_path,
                }
            )

        result = {
            "worker": "MODIFY",
            "changes_applied": len(applied_changes),
            "changes": applied_changes,
            "all_success": all(c["success"] for c in applied_changes),
            "status": "completed",
        }

        _persist_worker_result(self.request.id, "MODIFY", result, session_id)

        return result

    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise


# ============================================================================
# ORQUESTACIÓN CON CHAINS
# ============================================================================


def execute_parallel_workflow(intent: str, complexity: int, context: dict, session_id: str) -> dict:
    """
    Ejecuta workflow paralelo basado en complejidad.

    Args:
        intent: Qué hacer
        complexity: 1-10 complejidad
        context: Contexto de ejecución
        session_id: ID de sesión

    Returns:
        dict con resultados consolidados
    """

    # Determinar qué workers necesitamos
    if complexity <= 4:
        # Solo SEARCH + MODIFY
        workflow = group(
            worker_search.s(context.get("query", ""), intent, session_id),
            worker_modify.s(context.get("changes", []), True, session_id),
        )

    elif complexity <= 7:
        # SEARCH → ANALYSIS → MODIFY
        workflow = chain(
            worker_search.s(context.get("query", ""), intent, session_id),
            worker_analysis.s(intent, session_id),
            worker_modify.s(context.get("changes", []), True, session_id),
        )

    else:
        # Todos los workers en paralelo donde sea posible
        # SEARCH + ANALYSIS primero, luego CREATE + MODIFY
        job = chain(
            group(
                worker_search.s(context.get("query", ""), intent, session_id),
                worker_analysis.s(context.get("files", []), intent, session_id),
            ),
            group(
                worker_create.s(context.get("spec", {}), context, session_id),
                worker_modify.s(context.get("changes", []), True, session_id),
            ),
        )

        result = job.apply_async()
        return _consolidate_results(result, session_id)

    # Ejecutar
    result = workflow.apply_async()
    return _consolidate_results(result, session_id)


def _consolidate_results(result, session_id: str) -> dict:
    """Consolida resultados de workers en un CP limpio."""

    # Esperar resultados (timeout 5 min)
    results = result.get(timeout=300)

    consolidated = {
        "session_id": session_id,
        "workers_executed": 0,
        "results": {},
        "files_touched": [],
        "symbols_modified": [],
        "total_time": 0,
        "status": "completed",
    }

    # Procesar resultados
    for worker_result in results if isinstance(results, list) else [results]:
        if isinstance(worker_result, dict):
            worker_type = worker_result.get("worker", "UNKNOWN")
            consolidated["results"][worker_type] = worker_result
            consolidated["workers_executed"] += 1

            # Extraer archivos tocados
            if "files" in worker_result:
                consolidated["files_touched"].extend(
                    [f["name"] if isinstance(f, dict) else f for f in worker_result["files"]]
                )

    # Persistir consolidado en grafo
    _persist_consolidated_result(consolidated, session_id)

    return consolidated


# ============================================================================
# PERSISTENCIA GRAFOCENTRICA
# ============================================================================


def _persist_worker_result(task_id: str, worker_type: str, result: dict, session_id: str):
    """Persiste resultado de worker en Neo4j."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
        with driver.session() as session:
            session.run(
                """
                MERGE (w:WorkerTask {id: $task_id})
                SET w.worker_type = $worker_type,
                    w.status = $status,
                    w.result = $result_json,
                    w.completed_at = datetime()
                WITH w
                MATCH (s:Session {session_id: $session_id})
                MERGE (w)-[:EXECUTED_IN]->(s)
            """,
                task_id=task_id,
                worker_type=worker_type,
                status=result.get("status", "unknown"),
                result_json=json.dumps(result),
                session_id=session_id,
            )
        driver.close()
    except Exception as e:
        print(f"Failed to persist worker result: {e}")


def _persist_consolidated_result(result: dict, session_id: str):
    """Persiste resultado consolidado en Neo4j."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
        with driver.session() as session:
            session.run(
                """
                MERGE (c:ConsolidatedResult {session_id: $session_id})
                SET c.workers_executed = $workers,
                    c.files_touched = $files,
                    c.status = $status,
                    c.timestamp = datetime(),
                    c.result_json = $result_json
            """,
                session_id=session_id,
                workers=result["workers_executed"],
                files=json.dumps(result["files_touched"]),
                status=result["status"],
                result_json=json.dumps(result),
            )
        driver.close()
    except Exception as e:
        print(f"Failed to persist consolidated result: {e}")


def _generate_file_content(spec: dict, context: dict) -> str:
    """Genera contenido de archivo (simplificado)."""
    # Aquí iría la lógica real de generación
    return f"# Generated {spec['name']}\n# Context: {context}\n"


if __name__ == "__main__":
    # Ejemplo de uso
    print("Celery Workers Denis iniciados")
    print("Ejecutar: celery -A celery_workers worker -l info -c 4")
