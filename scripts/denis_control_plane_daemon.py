#!/usr/bin/env python3
"""Denis Control Plane Daemon — Observa, genera CPs, pide aprobación.

Flujo:
1. Observa /tmp/denis_agent_result.json
2. CPGenerator crea CP desde resultado del agente
3. ApprovalPopup muestra zenity (3 momentos deterministas)
4. Si aprueba → escribe /tmp/denis_next_cp.json
5. Si para → ControlPlaneAuthority bloquea modelo

Todo grafocéntrico. Todo determinista.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Setup paths
sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")
sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah/denis_unified_v1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/denis/daemon.log")],
)
logger = logging.getLogger(__name__)

# Archivos de comunicación
AGENT_RESULT_FILE = "/tmp/denis_agent_result.json"
NEXT_CP_FILE = "/tmp/denis_next_cp.json"
PHASE_COMPLETE_FILE = "/tmp/denis/phase_complete.json"
SPRINT_SUMMARY_FILE = "/tmp/denis/sprint_summary.json"
UPLOADED_CP_FILE = "/tmp/denis/uploaded_cp.json"
PID_FILE = "/tmp/denis/daemon.pid"


class ControlPlaneDaemon:
    """
    Daemon del Control Plane.

    Observa el sistema y genera CPs que requieren aprobación humana.
    """

    def __init__(self):
        self.running = True
        self.cp_generator = None
        self.cp_queue = None
        self.last_check = 0

    def _init_components(self):
        """Inicializa componentes del Control Plane."""
        try:
            from control_plane.cp_generator import CPGenerator
            from control_plane.cp_queue import get_cp_queue

            self.cp_generator = CPGenerator()
            self.cp_queue = get_cp_queue()
            logger.info("Control Plane components initialized")
        except Exception as e:
            logger.error(f"Failed to init components: {e}")

    def _load_agent_result(self) -> dict:
        """Carga resultado del agente si existe."""
        if not os.path.exists(AGENT_RESULT_FILE):
            return None

        try:
            with open(AGENT_RESULT_FILE, "r") as f:
                data = json.load(f)
            os.remove(AGENT_RESULT_FILE)  # Consumir el archivo
            return data
        except Exception as e:
            logger.error(f"Failed to load agent result: {e}")
            return None

    def _load_phase_complete(self) -> dict:
        """Carga completación de fase si existe."""
        if not os.path.exists(PHASE_COMPLETE_FILE):
            return None

        try:
            with open(PHASE_COMPLETE_FILE, "r") as f:
                data = json.load(f)
            os.remove(PHASE_COMPLETE_FILE)
            return data
        except Exception as e:
            logger.error(f"Failed to load phase complete: {e}")
            return None

    def _load_sprint_summary(self) -> dict:
        """Carga resumen de sprint si existe."""
        if not os.path.exists(SPRINT_SUMMARY_FILE):
            return None

        try:
            with open(SPRINT_SUMMARY_FILE, "r") as f:
                data = json.load(f)
            os.remove(SPRINT_SUMMARY_FILE)
            return data
        except Exception as e:
            logger.error(f"Failed to load sprint summary: {e}")
            return None

    def _load_uploaded_cp(self) -> dict:
        """ANEXO: Carga CP subido manualmente desde disco."""
        if not os.path.exists(UPLOADED_CP_FILE):
            return None

        try:
            with open(UPLOADED_CP_FILE, "r") as f:
                data = json.load(f)
            os.remove(UPLOADED_CP_FILE)
            logger.info(f"Loaded uploaded CP: {data.get('cp_id', 'unknown')}")
            return data
        except Exception as e:
            logger.error(f"Failed to load uploaded CP: {e}")
            return None

    def _handle_uploaded_cp(self, cp_data: dict):
        """
        ANEXO: Maneja CP subido manualmente desde disco.

        Flujo: Usuario sube CP → popup de confirmación → mismo flow que POST-BRIEF
        """
        logger.info("UPLOADED-CP: Procesando CP subido manualmente")

        try:
            from control_plane.cp_generator import ContextPack
            from control_plane.approval_popup import show_upload_cp_popup, show_post_brief_popup
            from control_plane.cp_queue import get_cp_queue

            # Construir CP desde datos subidos
            if "cp_id" in cp_data:
                cp = ContextPack.from_dict(cp_data)
            else:
                # Formato simplificado
                cp = ContextPack(
                    cp_id=f"upload_{int(datetime.now().timestamp())}",
                    mission=cp_data.get("mission", "Uploaded CP"),
                    model=cp_data.get("model", "groq"),
                    files_to_read=cp_data.get("files_to_read", []),
                    files_touched=cp_data.get("files_touched", []),
                    success=cp_data.get("success", False),
                    risk_level=cp_data.get("risk_level", "MEDIUM"),
                    is_checkpoint=True,
                    do_not_touch=cp_data.get("do_not_touch", []),
                    implicit_tasks=cp_data.get("implicit_tasks", []),
                    acceptance_criteria=cp_data.get("acceptance_criteria", []),
                    intent=cp_data.get("intent", "implement_feature"),
                    constraints=cp_data.get("constraints", []),
                    repo_id=cp_data.get("repo_id", ""),
                    repo_name=cp_data.get("repo_name", "denis_unified_v1"),
                    branch=cp_data.get("branch", "main"),
                )

            # Mostrar popup de confirmación (mismo que POST-BRIEF)
            decision, feedback = show_post_brief_popup(cp)

            logger.info(f"UPLOADED-CP decision: {decision}")

            if decision == "approved":
                cp.human_validated = True
                cp.validated_by = "user_uploaded"

                queue = get_cp_queue()
                queue.push(cp)

                with open(NEXT_CP_FILE, "w") as f:
                    json.dump(cp.to_dict(), f, indent=2, default=str)

                logger.info(f"Uploaded CP {cp.cp_id} approved and queued")

            elif decision == "stopped":
                from control_plane.approval_popup import get_control_plane_authority

                authority = get_control_plane_authority()
                stop_signal = authority.stop_model(
                    cp.model, "Usuario rechazó CP subido manualmente"
                )

                stop_file = f"/tmp/denis/stop_{cp.model}.json"
                with open(stop_file, "w") as f:
                    json.dump(stop_signal, f, indent=2)

            elif decision == "edit":
                self._handle_edit_request(cp)

        except Exception as e:
            logger.error(f"UPLOADED-CP failed: {e}", exc_info=True)

    def _handle_post_brief(self, agent_result: dict):
        """
        MOMENTO 1: POST-BRIEF

        Agente terminó de procesar brief del usuario.
        Genera CP y pide aprobación.
        """
        logger.info("POST-BRIEF: Generando CP desde agent_result")

        try:
            from control_plane.cp_generator import ContextPack
            from control_plane.approval_popup import show_post_brief_popup
            from control_plane.cp_queue import get_cp_queue

            cp = self.cp_generator.from_agent_result(agent_result)

            # Persistir al grafo como propuesta
            self._persist_proposal_to_graph(cp, "post_brief")

            # Mostrar popup (bloquea hasta decisión)
            decision, feedback = show_post_brief_popup(cp)

            logger.info(f"POST-BRIEF decision: {decision}")

            if decision == "approved":
                # Aprobar y poner en cola
                cp.human_validated = True
                cp.validated_by = "user_post_brief"

                queue = get_cp_queue()
                queue.push(cp)

                # Escribir para que el agente lo lea
                with open(NEXT_CP_FILE, "w") as f:
                    json.dump(cp.to_dict(), f, indent=2, default=str)

                logger.info(f"CP {cp.cp_id} approved and queued")

            elif decision == "stopped":
                # Control Plane tiene autoridad - modelo debe parar
                self._handle_stop(cp, feedback, "post_brief")

            elif decision == "edit":
                # Usuario quiere editar - pedir corrección
                self._handle_edit_request(cp)

        except Exception as e:
            logger.error(f"POST-BRIEF failed: {e}", exc_info=True)

    def _handle_phase_complete(self, phase_data: dict):
        """
        MOMENTO 2: FASE-COMPLETA o ERROR

        Terminó una fase o hay problema.
        """
        logger.info(f"FASE-COMPLETA: Phase {phase_data.get('phase_num', '?')}")

        try:
            from control_plane.approval_popup import show_phase_complete_popup
            from control_plane.cp_queue import get_cp_queue

            # Recuperar CP actual
            queue = get_cp_queue()
            cp = queue.peek()

            if not cp:
                logger.warning("No active CP for phase complete")
                return

            # Persistir progreso al grafo
            self._persist_phase_to_graph(cp, phase_data)

            # Mostrar popup
            decision, feedback = show_phase_complete_popup(cp, phase_data)

            logger.info(f"FASE-COMPLETA decision: {decision}")

            if decision == "continue":
                # Continuar con siguiente fase
                logger.info("Continuando a siguiente fase")

            elif decision == "stopped":
                # Parar ejecución
                self._handle_stop(cp, feedback, f"phase_{phase_data.get('phase_num')}")

            elif decision == "reformulate":
                # Reformular con nuevas constraints
                self._handle_reformulation(cp, feedback)

        except Exception as e:
            logger.error(f"FASE-COMPLETA failed: {e}", exc_info=True)

    def _handle_sprint_close(self, sprint_summary: dict):
        """
        MOMENTO 3: SPRINT-CLOSE

        Finalización del sprint.
        """
        logger.info("SPRINT-CLOSE: Cerrando sprint")

        try:
            from control_plane.approval_popup import show_sprint_close_popup
            from control_plane.cp_queue import get_cp_queue

            queue = get_cp_queue()
            cp = queue.peek()

            if not cp:
                logger.warning("No active CP for sprint close")
                return

            # Mostrar popup
            decision, feedback = show_sprint_close_popup(cp, sprint_summary)

            logger.info(f"SPRINT-CLOSE decision: {decision}")

            if decision == "close_approved":
                # Cerrar y limpiar
                queue.pop()  # Sacar de la cola
                self._persist_sprint_close_to_graph(cp, sprint_summary)
                logger.info("Sprint cerrado exitosamente")

            elif decision == "stopped":
                # Revisar antes de cerrar
                self._handle_stop(cp, feedback, "sprint_close")

            elif decision == "view_details":
                # Mostrar detalles (podría abrir un reporte)
                logger.info("Usuario quiere ver detalles del sprint")

        except Exception as e:
            logger.error(f"SPRINT-CLOSE failed: {e}", exc_info=True)

    def _handle_stop(self, cp, feedback: str, moment: str):
        """Maneja la parada determinista del modelo."""
        logger.warning(f"Control Plane STOP en {moment}: {feedback}")

        # Persistir decisión al grafo
        try:
            from control_plane.approval_popup import get_control_plane_authority

            authority = get_control_plane_authority()
            stop_signal = authority.stop_model(cp.model, f"Usuario paró en {moment}")

            # Escribir señal de parada para que el modelo la lea
            stop_file = f"/tmp/denis/stop_{cp.model}.json"
            with open(stop_file, "w") as f:
                json.dump(stop_signal, f, indent=2)

            logger.info(f"Stop signal written to {stop_file}")

        except Exception as e:
            logger.error(f"Failed to handle stop: {e}")

    def _handle_edit_request(self, cp):
        """Maneja solicitud de edición del CP."""
        logger.info("Usuario solicita editar CP")

        try:
            from control_plane.approval_popup import get_correction_input
            from control_plane.human_input_processor import process_human_input

            correction = get_correction_input()

            if correction:
                # Procesar corrección
                delta = process_human_input(correction, cp)

                # Aplicar cambios al CP
                if delta.get("mission_delta"):
                    cp.mission += f"\nAJUSTE: {delta['mission_delta']}"

                cp.do_not_touch.extend(delta.get("new_do_not_touch", []))
                cp.constraints.extend(delta.get("new_constraints", []))

                # Re-encolar CP modificado
                from control_plane.cp_queue import get_cp_queue

                queue = get_cp_queue()
                queue.push(cp)

                logger.info("CP modificado y re-encolado")

        except Exception as e:
            logger.error(f"Failed to handle edit: {e}")

    def _handle_reformulation(self, cp, feedback: str):
        """Maneja solicitud de reformulación."""
        logger.info("Control Plane solicita reformulación")

        try:
            reformulation = json.loads(feedback)
            new_constraints = reformulation.get("new_constraints", [])

            # Aplicar nuevas constraints
            cp.constraints.extend(new_constraints)
            cp.notes = f"REFORMULACIÓN: {new_constraints}"

            # Re-encolar
            from control_plane.cp_queue import get_cp_queue

            queue = get_cp_queue()
            queue.push(cp)

            logger.info(f"CP reformulado con constraints: {new_constraints}")

        except Exception as e:
            logger.error(f"Failed to handle reformulation: {e}")

    def _persist_proposal_to_graph(self, cp, moment: str):
        """Persiste propuesta de CP al grafo."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                session.run(
                    """
                    MERGE (prop:CPProposal {id: $id})
                    SET prop.cp_id = $cp_id,
                        prop.moment = $moment,
                        prop.timestamp = datetime(),
                        prop.mission = $mission,
                        prop.model = $model
                    WITH prop
                    MATCH (cp:ContextPack {id: $cp_id})
                    MERGE (cp)-[:PROPOSED_IN]->(prop)
                """,
                    id=f"prop_{cp.cp_id}_{moment}",
                    cp_id=cp.cp_id,
                    moment=moment,
                    mission=cp.mission[:200],
                    model=cp.model,
                )
            driver.close()
        except Exception as e:
            logger.debug(f"Failed to persist proposal: {e}")

    def _persist_phase_to_graph(self, cp, phase_data: dict):
        """Persiste completación de fase al grafo."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                session.run(
                    """
                    MERGE (phase:PhaseComplete {id: $id})
                    SET phase.cp_id = $cp_id,
                        phase.phase_num = $phase_num,
                        phase.status = $status,
                        phase.timestamp = datetime()
                    WITH phase
                    MATCH (cp:ContextPack {id: $cp_id})
                    MERGE (cp)-[:HAS_PHASE]->(phase)
                """,
                    id=f"phase_{cp.cp_id}_{phase_data.get('phase_num')}",
                    cp_id=cp.cp_id,
                    phase_num=phase_data.get("phase_num", 0),
                    status=phase_data.get("status", "unknown"),
                )
            driver.close()
        except Exception as e:
            logger.debug(f"Failed to persist phase: {e}")

    def _persist_sprint_close_to_graph(self, cp, sprint_summary: dict):
        """Persiste cierre de sprint al grafo."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                session.run(
                    """
                    MERGE (close:SprintClose {id: $id})
                    SET close.cp_id = $cp_id,
                        close.timestamp = datetime(),
                        close.tasks_completed = $completed,
                        close.tasks_failed = $failed
                    WITH close
                    MATCH (cp:ContextPack {id: $cp_id})
                    MERGE (cp)-[:CLOSED_AS]->(close)
                """,
                    id=f"sprint_close_{cp.cp_id}",
                    cp_id=cp.cp_id,
                    completed=sprint_summary.get("tasks_completed", 0),
                    failed=sprint_summary.get("tasks_failed", 0),
                )
            driver.close()
        except Exception as e:
            logger.debug(f"Failed to persist sprint close: {e}")

    def _cleanup_expired(self):
        """Limpia CPs expirados."""
        try:
            from control_plane.cp_queue import get_cp_queue

            queue = get_cp_queue()
            removed = queue.purge_expired()
            if removed > 0:
                logger.info(f"Cleaned up {removed} expired CPs")
        except Exception as e:
            logger.debug(f"Cleanup failed: {e}")

    def run(self):
        """Loop principal del daemon."""
        logger.info("=" * 60)
        logger.info("DENIS CONTROL PLANE DAEMON STARTED")
        logger.info("=" * 60)
        logger.info("Observando tres momentos deterministas:")
        logger.info("  1. POST-BRIEF (agent_result.json)")
        logger.info("  2. FASE-COMPLETA (phase_complete.json)")
        logger.info("  3. SPRINT-CLOSE (sprint_summary.json)")
        logger.info("ANEXO: UPLOADED-CP (uploaded_cp.json)")
        logger.info("=" * 60)

        self._init_components()

        # Escribir PID
        os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        try:
            while self.running:
                # MOMENTO 1: POST-BRIEF
                agent_result = self._load_agent_result()
                if agent_result:
                    self._handle_post_brief(agent_result)

                # MOMENTO 2: FASE-COMPLETA
                phase_data = self._load_phase_complete()
                if phase_data:
                    self._handle_phase_complete(phase_data)

                # MOMENTO 3: SPRINT-CLOSE
                sprint_summary = self._load_sprint_summary()
                if sprint_summary:
                    self._handle_sprint_close(sprint_summary)

                # ANEXO: UPLOADED-CP (CP subido manualmente desde disco)
                uploaded_cp = self._load_uploaded_cp()
                if uploaded_cp:
                    self._handle_uploaded_cp(uploaded_cp)

                # Cleanup periódico
                self._cleanup_expired()

                # Esperar antes de siguiente ciclo
                time.sleep(2)

        except KeyboardInterrupt:
            logger.info("Daemon stopped by user")
        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            logger.info("Daemon shutdown complete")


def signal_handler(signum, frame):
    """Maneja señales de sistema."""
    logger.info(f"Received signal {signum}")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    daemon = ControlPlaneDaemon()
    daemon.run()
