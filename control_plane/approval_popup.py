#!/usr/bin/env python3
"""Approval Popup - Zenity-based approval dialog for Control Plane.

Tres momentos deterministas cuando salta el popup:
1. POST-BRIEF: Agente propone implementación después del brief del usuario
2. FASE-COMPLETA/ERROR: Termina fase o hay problema que requiere atención
3. SPRINT-CLOSE: Finalización del sprint o proyecto

Control Plane tiene autoridad absoluta:
- Si usuario marca PARAR → modelo PARA (determinista)
- Modelo obligado a reformular con feedback del Control Plane
- Todo en JSON (lenguaje máquina)
- Todo grafocéntrico (Neo4j)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from control_plane.ai_consult import AIConsult, ConsultResult
from control_plane.cp_generator import ContextPack

logger = logging.getLogger(__name__)


class ControlPlaneAuthority:
    """
    Autoridad absoluta del Control Plane.

    Cuando el usuario dice PARAR, el modelo PARA.
    El feedback va al grafo y el modelo debe reformular.
    """

    def __init__(self):
        self.blocked_models = set()
        self.pending_reformulation = {}

    def stop_model(self, model_id: str, reason: str) -> dict:
        """
        Bloquea un modelo y genera feedback estructurado.

        Returns:
            JSON con acción requerida para el modelo
        """
        self.blocked_models.add(model_id)

        feedback = {
            "action": "STOP",
            "authority": "ControlPlane",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "model_id": model_id,
            "required": {
                "halt_execution": True,
                "save_state": True,
                "wait_for_reformulation": True,
            },
            "next_steps": [
                "Guardar estado actual en /tmp/denis/suspended_{model_id}.json",
                "Esperar señal de CONTINUAR o REFORMULAR del Control Plane",
                "NO proceder hasta nuevo CP aprobado",
            ],
        }

        # Persistir al grafo
        self._persist_stop_to_graph(model_id, feedback)

        return feedback

    def _persist_stop_to_graph(self, model_id: str, feedback: dict):
        """Persiste la parada al grafo como (:ControlPlaneDecision)."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                session.run(
                    """
                    MERGE (cpd:ControlPlaneDecision {id: $id})
                    SET cpd.action = 'STOP',
                        cpd.model_id = $model_id,
                        cpd.reason = $reason,
                        cpd.timestamp = datetime(),
                        cpd.feedback = $feedback_json
                    WITH cpd
                    MATCH (m:Model {name: $model_id})
                    MERGE (m)-[:BLOCKED_BY]->(cpd)
                """,
                    id=f"stop_{model_id}_{int(datetime.now().timestamp())}",
                    model_id=model_id,
                    reason=feedback["reason"],
                    feedback_json=json.dumps(feedback),
                )
            driver.close()
        except Exception as e:
            logger.error(f"Failed to persist stop to graph: {e}")

    def signal_reformulate(self, model_id: str, new_constraints: list) -> dict:
        """
        Señal para que el modelo reformule con nuevas constraints.

        Returns:
            JSON con instrucciones de reformulación
        """
        self.pending_reformulation[model_id] = new_constraints

        reformulation = {
            "action": "REFORMULATE",
            "authority": "ControlPlane",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_id": model_id,
            "new_constraints": new_constraints,
            "required": {
                "re_read_cp": True,
                "apply_constraints": True,
                "generate_new_plan": True,
                "submit_for_approval": True,
            },
            "source": "user_feedback_via_control_plane",
            "grafocentric": {
                "query": "MATCH (cp:ContextPack {status: 'rejected'})-[:BLOCKED_BY]->(:ControlPlaneDecision) RETURN cp.constraints",
                "apply_to": model_id,
            },
        }

        self._persist_reformulation_to_graph(model_id, reformulation)

        return reformulation

    def _persist_reformulation_to_graph(self, model_id: str, reformulation: dict):
        """Persiste la señal de reformulación al grafo."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                session.run(
                    """
                    MERGE (r:ReformulationSignal {id: $id})
                    SET r.action = 'REFORMULATE',
                        r.model_id = $model_id,
                        r.timestamp = datetime(),
                        r.constraints = $constraints,
                        r.signal_json = $signal_json
                    WITH r
                    MATCH (m:Model {name: $model_id})
                    MERGE (m)-[:MUST_REFORMULATE]->(r)
                """,
                    id=f"ref_{model_id}_{int(datetime.now().timestamp())}",
                    model_id=model_id,
                    constraints=json.dumps(reformulation["new_constraints"]),
                    signal_json=json.dumps(reformulation),
                )
            driver.close()
        except Exception as e:
            logger.error(f"Failed to persist reformulation to graph: {e}")


# Singleton
_authority = None


def get_control_plane_authority() -> ControlPlaneAuthority:
    """Get Control Plane Authority singleton."""
    global _authority
    if _authority is None:
        _authority = ControlPlaneAuthority()
    return _authority


async def consult_graph(query: str, cp: ContextPack, symbols_context: list = None) -> ConsultResult:
    """Graph-enhanced consult (existing)."""
    from control_plane.repo_context import RepoContext
    from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

    cypher_router = get_symbol_cypher_router()
    repo_ctx = RepoContext()

    if symbols_context is None:
        symbols = cypher_router.get_symbols_context(cp.intent, repo_ctx.get_session_id(), limit=10)
        symbols_context = [{"path": s.path, "name": s.name, "kind": s.kind} for s in symbols]

    ai_consult = AIConsult()

    enriched_context = f"""CONTEXTO GRAFICO DENIS:
Repo: {cp.repo_name} · {cp.branch}
Intent: {cp.intent}
Mission: {cp.mission}

SIMBOLOS RELACIONADOS DEL GRAFO:
{chr(10).join([f"- {s['name']} ({s['kind']}): {s['path']}" for s in symbols_context[:5]])}

Archivos a leer: {", ".join(cp.files_to_read[:3])}
Modelo: {cp.model}

PREGUNTA: {query}"""

    return await ai_consult.consult_with_context(query, cp)


# ============================================================================
# TRES MOMENTOS DETERMINISTAS DEL POPUP
# ============================================================================


def show_post_brief_popup(cp: ContextPack) -> Tuple[str, str]:
    """
    MOMENTO 1: POST-BRIEF

    El agente propone implementación después del brief del usuario.
    Este es el punto de control inicial.
    """
    summary = f"""🤖 DENIS — POST-BRIEF: Propuesta de Implementación

🎯 MISIÓN PROPUESTA:
{cp.mission[:120]}...

💻 MODELO ASIGNADO: {cp.model}
📁 ARCHIVOS INVOLUCRADOS: {len(cp.files_to_read)}
⚙️  CONSTRAINTS: {", ".join(cp.constraints[:3]) if cp.constraints else "none"}

El agente está listo para ejecutar. ¿Aprobar?"""

    try:
        result = subprocess.run(
            [
                "zenity",
                "--question",
                "--title=🤖 DENIS — POST-BRIEF [Determinista]",
                f"--text={summary}",
                "--ok-label=✅ APROBAR Y LANZAR",
                "--cancel-label=⛔ PARAR",
                "--extra-button=✏️ EDITAR",
                "--width=700",
                "--height=400",
                "--timeout=180",  # 3 min para decidir
            ],
            capture_output=True,
            text=True,
        )

        authority = get_control_plane_authority()

        if result.returncode == 0:
            return "approved", ""
        elif result.returncode == 1:
            # PARAR - Control Plane tiene autoridad
            feedback = authority.stop_model(cp.model, "Usuario rechazó en POST-BRIEF")
            return "stopped", json.dumps(feedback)
        elif result.returncode == 2:
            return "edit", ""
        else:
            # Timeout = PARAR por seguridad
            feedback = authority.stop_model(cp.model, "Timeout en POST-BRIEF")
            return "stopped", json.dumps(feedback)

    except Exception as e:
        logger.error(f"Popup failed: {e}")
        # Fallback: PARAR si no hay UI
        authority = get_control_plane_authority()
        feedback = authority.stop_model(cp.model, f"UI failure: {e}")
        return "stopped", json.dumps(feedback)


def show_phase_complete_popup(cp: ContextPack, phase_result: dict) -> Tuple[str, str]:
    """
    MOMENTO 2: FASE-COMPLETA o ERROR

    Termina una fase o hay problema que requiere atención.
    """
    status = phase_result.get("status", "unknown")
    phase_num = phase_result.get("phase_num", 1)
    errors = phase_result.get("errors", [])

    if errors:
        error_str = "\n".join([f"  ❌ {e[:80]}" for e in errors[:3]])
        summary = f"""🤖 DENIS — FASE {phase_num}: ⚠️ ERRORES DETECTADOS

🎯 {cp.mission[:80]}...

ERRORES:
{error_str}

¿Continuar con la siguiente fase?"""
    else:
        summary = f"""🤖 DENIS — FASE {phase_num}: ✅ COMPLETADA

🎯 {cp.mission[:80]}...

Fase completada exitosamente.

¿Continuar con la siguiente fase?"""

    try:
        result = subprocess.run(
            [
                "zenity",
                "--question",
                f"--title=🤖 DENIS — FASE {phase_num} [Determinista]",
                f"--text={summary}",
                "--ok-label=✅ CONTINUAR",
                "--cancel-label=⛔ PARAR",
                "--extra-button=🔄 REFORMULAR",
                "--width=700",
                "--height=450",
                "--timeout=120",
            ],
            capture_output=True,
            text=True,
        )

        authority = get_control_plane_authority()

        if result.returncode == 0:
            return "continue", ""
        elif result.returncode == 1:
            feedback = authority.stop_model(cp.model, f"Usuario paró en FASE {phase_num}")
            return "stopped", json.dumps(feedback)
        elif result.returncode == 2:
            # REFORMULAR - enviar feedback al grafo
            new_constraints = phase_result.get("suggested_constraints", [])
            reformulation = authority.signal_reformulate(cp.model, new_constraints)
            return "reformulate", json.dumps(reformulation)
        else:
            feedback = authority.stop_model(cp.model, f"Timeout en FASE {phase_num}")
            return "stopped", json.dumps(feedback)

    except Exception as e:
        authority = get_control_plane_authority()
        feedback = authority.stop_model(cp.model, f"UI failure en fase: {e}")
        return "stopped", json.dumps(feedback)


def show_sprint_close_popup(cp: ContextPack, sprint_summary: dict) -> Tuple[str, str]:
    """
    MOMENTO 3: SPRINT-CLOSE

    Finalización del sprint o proyecto.
    """
    tasks_completed = sprint_summary.get("tasks_completed", 0)
    tasks_failed = sprint_summary.get("tasks_failed", 0)
    files_changed = sprint_summary.get("files_changed", [])

    summary = f"""🤖 DENIS — SPRINT CLOSE: Resumen Final

🎯 SPRINT: {cp.mission[:80]}...

📊 RESULTADOS:
  ✅ Completadas: {tasks_completed}
  ❌ Fallidas: {tasks_failed}
  📝 Archivos modificados: {len(files_changed)}

¿Aprobar cierre del sprint?"""

    try:
        result = subprocess.run(
            [
                "zenity",
                "--question",
                "--title=🤖 DENIS — SPRINT CLOSE [Determinista]",
                f"--text={summary}",
                "--ok-label=✅ CERRAR SPRINT",
                "--cancel-label=⛔ PARAR (revisar)",
                "--extra-button=📝 VER DETALLES",
                "--width=700",
                "--height=400",
                "--timeout=300",  # 5 min para revisar
            ],
            capture_output=True,
            text=True,
        )

        authority = get_control_plane_authority()

        if result.returncode == 0:
            # Persistir cierre al grafo
            _persist_sprint_close_to_graph(cp, sprint_summary)
            return "close_approved", ""
        elif result.returncode == 1:
            feedback = authority.stop_model(cp.model, "Usuario rechazó cierre de sprint")
            return "stopped", json.dumps(feedback)
        elif result.returncode == 2:
            return "view_details", ""
        else:
            # Timeout en cierre = revisar manualmente
            return "timeout_review", "Revisar manualmente"

    except Exception as e:
        return "error", str(e)


def _persist_sprint_close_to_graph(cp: ContextPack, sprint_summary: dict):
    """Persiste el cierre del sprint al grafo."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
        with driver.session() as session:
            session.run(
                """
                MERGE (s:SprintClose {id: $id})
                SET s.cp_id = $cp_id,
                    s.timestamp = datetime(),
                    s.tasks_completed = $completed,
                    s.tasks_failed = $failed,
                    s.summary_json = $summary
                WITH s
                MATCH (cp:ContextPack {id: $cp_id})
                MERGE (cp)-[:CLOSED_AS]->(s)
            """,
                id=f"sprint_close_{int(datetime.now().timestamp())}",
                cp_id=cp.cp_id,
                completed=sprint_summary.get("tasks_completed", 0),
                failed=sprint_summary.get("tasks_failed", 0),
                summary=json.dumps(sprint_summary),
            )
        driver.close()
    except Exception as e:
        logger.error(f"Failed to persist sprint close: {e}")


# ============================================================================
# COMPATIBILIDAD CON CÓDIGO EXISTENTE
# ============================================================================


def show_cp_approval(cp: ContextPack) -> Tuple[str, str]:
    """Compatibilidad: usa POST-BRIEF por defecto."""
    return show_post_brief_popup(cp)


def show_plan_review(cp: ContextPack, phases: list, risks: list) -> Tuple[str, str]:
    """Compatibilidad: usa FASE-COMPLETA."""
    phase_result = {
        "status": "complete",
        "phase_num": 1,
        "errors": [],
        "phases": phases,
        "risks": risks,
    }
    return show_phase_complete_popup(cp, phase_result)


def show_upload_cp_popup() -> Tuple[str, Optional[ContextPack]]:
    """
    ANEXO: Cargar CP desde archivo de disco.

    Permite al usuario seleccionar un archivo JSON con CP y cargarlo
    directamente al Control Plane.

    Returns:
        (decision, cp_object) - cp_object es None si se canceló
    """
    try:
        # Abrir diálogo de selección de archivo
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=📂 Cargar ContextPack desde archivo",
                "--filename=/tmp/denis/",
                "--file-filter=ContextPacks (*.json) | *.json",
                "--file-filter=Todos los archivos | *",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return "cancelled", None

        filepath = result.stdout.strip()
        if not filepath or not os.path.exists(filepath):
            return "cancelled", None

        # Cargar y validar CP
        with open(filepath, "r") as f:
            data = json.load(f)

        from control_plane.cp_generator import ContextPack

        # Detectar formato (puede ser CP completo o solo datos)
        if "cp_id" in data:
            # Formato completo ContextPack
            cp = ContextPack.from_dict(data)
        elif "mission" in data:
            # Formato simplificado - construir CP
            cp = ContextPack(
                cp_id=f"upload_{int(datetime.now().timestamp())}",
                mission=data.get("mission", "Mission from uploaded CP"),
                model=data.get("model", "groq"),
                files_to_read=data.get("files_to_read", []),
                files_touched=data.get("files_touched", []),
                success=data.get("success", False),
                risk_level=data.get("risk_level", "MEDIUM"),
                is_checkpoint=data.get("is_checkpoint", True),
                do_not_touch=data.get("do_not_touch", []),
                implicit_tasks=data.get("implicit_tasks", []),
                acceptance_criteria=data.get("acceptance_criteria", []),
                intent=data.get("intent", "implement_feature"),
                constraints=data.get("constraints", []),
                repo_id=data.get("repo_id", ""),
                repo_name=data.get("repo_name", "denis_unified_v1"),
                branch=data.get("branch", "main"),
            )
        else:
            return "invalid_format", None

        # Mostrar preview y pedir confirmación
        preview = f"""📂 CP CARGADO DESDE DISCO:

🎯 MISSION: {cp.mission[:100]}...
💻 MODEL: {cp.model}
📁 FILES: {len(cp.files_to_read)} archivos
⚙️  CONSTRAINTS: {", ".join(cp.constraints[:3]) if cp.constraints else "none"}
📄 ARCHIVO: {filepath}

¿Proceder con este CP?"""

        confirm = subprocess.run(
            [
                "zenity",
                "--question",
                "--title=📂 Confirmar CP Cargado",
                f"--text={preview}",
                "--ok-label=✅ CARGAR Y LANZAR",
                "--cancel-label=❌ CANCELAR",
                "--width=700",
                "--height=400",
            ],
            capture_output=True,
            text=True,
        )

        if confirm.returncode == 0:
            logger.info(f"CP cargado desde {filepath}: {cp.cp_id}")
            return "loaded", cp
        else:
            return "cancelled", None

    except FileNotFoundError:
        # zenity no disponible - fallback CLI
        print("📂 Cargar CP desde archivo")
        filepath = input("Ruta al archivo JSON: ").strip()

        if not filepath or not os.path.exists(filepath):
            print("Archivo no encontrado")
            return "cancelled", None

        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            from control_plane.cp_generator import ContextPack

            cp = ContextPack.from_dict(data) if "cp_id" in data else None

            if cp:
                resp = input(f"CP: {cp.mission[:60]}...\n¿Cargar? [s/n]: ").lower()
                if resp in ["s", "si", "yes"]:
                    return "loaded", cp
            return "cancelled", None

        except Exception as e:
            print(f"Error cargando CP: {e}")
            return "error", None

    except Exception as e:
        logger.error(f"Failed to upload CP: {e}")
        return "error", None


__all__ = [
    "show_post_brief_popup",
    "show_phase_complete_popup",
    "show_sprint_close_popup",
    "show_cp_approval",
    "show_plan_review",
    "show_upload_cp_popup",
    "ControlPlaneAuthority",
    "get_control_plane_authority",
]
