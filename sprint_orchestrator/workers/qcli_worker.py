"""Worker: qcli-searcher - code intelligence tasks using qcli."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from sprint_orchestrator.event_bus import EventBus, publish_event
from sprint_orchestrator.models import SprintEvent, SprintTask
from sprint_orchestrator.session_store import SessionStore
from sprint_orchestrator.qcli_integration import get_qcli


def qcli_search_worker(
    session_id: str,
    worker_id: str,
    task: SprintTask,
    store: SessionStore,
    bus: EventBus | None = None,
) -> Dict[str, Any]:
    """Worker que realiza búsquedas inteligentes usando qcli."""
    query = task.payload.get("query", "")
    limit = int(task.payload.get("limit", 20))

    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="qcli.search.start",
            message=f"Buscando: {query}",
            payload={"query": query, "limit": limit, "task_id": task.task_id},
        ),
        bus,
    )

    try:
        qcli = get_qcli()
        results = qcli.search(query=query, limit=limit, session_id=session_id)

        # Formatear resultados para consumo externo
        formatted = {
            "query": query,
            "total": len(results.get("results", [])),
            "results": results.get("results", [])[:limit],
            "summary": results.get("summary", ""),
            "classification": results.get("classification", {}),
        }

        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="qcli.search.done",
                message=f"Encontrados {formatted['total']} resultados",
                payload={"formatted": formatted, "task_id": task.task_id},
            ),
            bus,
        )

        return {"status": "ok", "results": formatted, "task_id": task.task_id}
    except Exception as exc:
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="qcli.search.error",
                message=f"Error: {exc}",
                payload={"error": str(exc), "task_id": task.task_id},
            ),
            bus,
        )
        return {"status": "error", "error": str(exc), "task_id": task.task_id}


def qcli_crossref_worker(
    session_id: str,
    worker_id: str,
    task: SprintTask,
    store: SessionStore,
    bus: EventBus | None = None,
) -> Dict[str, Any]:
    """Worker que obtiene referencias cruzadas de un símbolo."""
    symbol = task.payload.get("symbol", "")
    file = task.payload.get("file")

    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="qcli.crossref.start",
            message=f"CrossRef para: {symbol}",
            payload={"symbol": symbol, "file": file, "task_id": task.task_id},
        ),
        bus,
    )

    try:
        qcli = get_qcli()
        refs = qcli.crossref(symbol=symbol, file=file, session_id=session_id)

        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="qcli.crossref.done",
                message=f"CrossRef: {refs.get('total', 0)} referencias",
                payload={"refs": refs, "task_id": task.task_id},
            ),
            bus,
        )

        return {"status": "ok", "refs": refs, "task_id": task.task_id}
    except Exception as exc:
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="qcli.crossref.error",
                message=f"Error: {exc}",
                payload={"error": str(exc), "task_id": task.task_id},
            ),
            bus,
        )
        return {"status": "error", "error": str(exc), "task_id": task.task_id}


def qcli_index_worker(
    session_id: str,
    worker_id: str,
    task: SprintTask,
    store: SessionStore,
    bus: EventBus | None = None,
) -> Dict[str, Any]:
    """Worker que indexa archivos o el proyecto completo."""
    paths = task.payload.get("paths", [])  # Lista de rutas relativas
    project_path = Path(task.project_path)

    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="qcli.index.start",
            message=f"Indexando {len(paths) if paths else 'proyecto completo'}",
            payload={
                "paths": paths,
                "project_path": str(project_path),
                "task_id": task.task_id,
            },
        ),
        bus,
    )

    try:
        qcli = get_qcli(project_root=project_path)
        if paths:
            path_objs = [project_path / p for p in paths]
        else:
            path_objs = None
        result = qcli.index_project(paths=path_objs)

        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="qcli.index.done",
                message=f"Indexación completada",
                payload={"result": result, "task_id": task.task_id},
            ),
            bus,
        )

        return {"status": "ok", "result": result, "task_id": task.task_id}
    except Exception as exc:
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="qcli.index.error",
                message=f"Error: {exc}",
                payload={"error": str(exc), "task_id": task.task_id},
            ),
            bus,
        )
        return {"status": "error", "error": str(exc), "task_id": task.task_id}


# Registry para que el worker_dispatch descubra estos workers
QCLI_WORKERS = {
    "qcli.search": qcli_search_worker,
    "qcli.crossref": qcli_crossref_worker,
    "qcli.index": qcli_index_worker,
}
