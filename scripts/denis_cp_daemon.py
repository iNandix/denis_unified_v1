#!/usr/bin/env python3
"""
Denis Control Plane Daemon - Monitors agent results and triggers approval popup.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

AGENT_RESULT_FILE = "/tmp/denis_agent_result.json"
CP_OUTPUT_FILE = "/tmp/denis_cp_approved.json"
POLL_INTERVAL = 2


def wait_for_agent_result(timeout: int = 300) -> dict | None:
    """Wait for agent result file to appear."""
    start = time.time()
    logger.info(f"Waiting for {AGENT_RESULT_FILE}...")

    while time.time() - start < timeout:
        if os.path.exists(AGENT_RESULT_FILE):
            try:
                import json

                with open(AGENT_RESULT_FILE) as f:
                    data = json.load(f)
                logger.info(f"Agent result detected: {data.get('intent', 'unknown')[:50]}")
                return data
            except Exception as e:
                logger.error(f"Error reading agent result: {e}")
                return None
        time.sleep(POLL_INTERVAL)

    logger.warning("Timeout waiting for agent result")
    return None


def generate_context_pack(agent_result: dict) -> dict:
    """Generate ContextPack from agent result."""
    from control_plane.cp_generator import CPGenerator

    generator = CPGenerator()
    cp = generator.from_agent_result(agent_result)

    return cp.to_dict()


def trigger_approval_popup(cp_dict: dict) -> bool:
    """Trigger zenity approval popup or auto-approve based on risk level."""
    from control_plane.approval_popup import show_post_brief_popup
    from control_plane.cp_generator import ContextPack

    cp = ContextPack.from_dict(cp_dict)

    if cp.risk_level in ["LOW", "MEDIUM"] and not cp.is_checkpoint:
        logger.info(
            f"Auto-approving CP {cp.cp_id} (risk={cp.risk_level}, checkpoint={cp.is_checkpoint})"
        )
        cp.human_validated = True
        cp.validated_by = "auto_approve"
        cp_dict["human_validated"] = True
        cp_dict["validated_by"] = "auto_approve"
        return True

    logger.info(f"Showing approval popup for CP {cp.cp_id} (risk={cp.risk_level})")
    result, consult = popup.show_cp_approval(cp)

    if result == "approved":
        logger.info("CP approved by human")
        return True
    elif result == "rejected":
        logger.info("CP rejected by human")
        return False
    elif result == "timeout":
        logger.warning("CP approval timed out")
        return False
    else:
        logger.warning(f"Unknown approval result: {result}")
        return False


def write_approved_cp(cp_dict: dict, approved: bool) -> None:
    """Write approved/rejected CP to output file."""
    cp_dict["human_approved"] = approved
    import json

    with open(CP_OUTPUT_FILE, "w") as f:
        json.dump(cp_dict, f, indent=2)
    logger.info(f"CP written to {CP_OUTPUT_FILE}")


def clear_agent_result() -> None:
    """Clear agent result file after processing."""
    try:
        if os.path.exists(AGENT_RESULT_FILE):
            os.remove(AGENT_RESULT_FILE)
            logger.info(f"Cleared {AGENT_RESULT_FILE}")
    except Exception as e:
        logger.error(f"Error clearing agent result: {e}")


def run_daemon(poll_interval: int = POLL_INTERVAL, max_wait: int = 300) -> None:
    """Main daemon loop with Denis Persona live."""
    import asyncio
    import json

    logger.info("Denis Control Plane Daemon started with Persona")
    logger.info("Monitoring: /tmp/denis/cp_received.json, /tmp/denis/phase_complete.json")

    denis_persona = None
    try:
        from kernel.denis_persona import get_denis_persona

        denis_persona = get_denis_persona()
        asyncio.run(denis_persona.initialize())
        logger.info("Denis Persona initialized in daemon")
    except Exception as e:
        logger.warning(f"Could not initialize Denis Persona: {e}")

    def sync_graph_engines():
        """Poll Neo4j for live engine status."""
        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            cypher = get_symbol_cypher_router()
            drivers = cypher._get_driver()
            if drivers:
                with drivers.session() as session:
                    result = session.run("""
                        MATCH (e:Engine)
                        RETURN e.name as name, e.healthy as healthy, e.endpoint as endpoint
                    """)
                    engines = list(result)
                    logger.debug(f"Graph engines polled: {len(engines)} engines")
                    return engines
        except Exception as e:
            logger.debug(f"Graph engine poll failed: {e}")
        return []

    async def learn_from_outcome(session_id: str, cp_data: dict, approved: bool):
        """Denis learns from CP outcome."""
        if not denis_persona:
            return

        outcome_str = (
            f"approved={approved}, intent={cp_data.get('intent')}, engine={cp_data.get('model')}"
        )

        try:
            await denis_persona.learn_outcome(
                session_id,
                {
                    "approved": approved,
                    "intent": cp_data.get("intent", "unknown"),
                    "engine": cp_data.get("model", "unknown"),
                },
                outcome_str,
            )
        except Exception as e:
            logger.debug(f"Denis learn_outcome failed: {e}")

    while True:
        engines = sync_graph_engines()

        if denis_persona:
            try:
                asyncio.run(denis_persona.get_stats())
            except Exception as e:
                logger.debug(f"Denis Persona stats poll: {e}")

        CP_RECEIVED_FILE = "/tmp/denis/cp_received.json"
        PHASE_COMPLETE_FILE = "/tmp/denis/phase_complete.json"

        if os.path.exists(CP_RECEIVED_FILE):
            try:
                with open(CP_RECEIVED_FILE) as f:
                    data = json.load(f)
                os.remove(CP_RECEIVED_FILE)

                from control_plane.approval_popup import show_plan_review
                from control_plane.models import ContextPack

                cp = ContextPack(**data["cp"])
                phases = data.get("phases", [])
                risks = data.get("risks", [])

                decision, correction = show_plan_review(cp, phases, risks)
                logger.info(f"Plan review: {decision}")

                if denis_persona and decision in ["approved", "correction"]:
                    try:
                        session_id = data.get("cp", {}).get("session_id", "default")
                        cp_dict = cp.to_dict()
                        outcome_str = f"decision={decision}, intent={cp.intent}"
                        asyncio.run(
                            denis_persona.learn_outcome(
                                session_id,
                                {
                                    "approved": decision == "approved",
                                    "intent": cp.intent,
                                    "engine": cp.model,
                                },
                                outcome_str,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Denis learn from plan review failed: {e}")

                if decision == "correction" and correction:
                    from control_plane.human_input_processor import process_human_input
                    from control_plane.cp_queue import CPQueue

                    delta = process_human_input(correction, cp)
                    if delta["mission_delta"]:
                        cp.mission += f"\nAJUSTE HUMANO: {delta['mission_delta']}"
                    cp.do_not_touch.extend(delta["new_do_not_touch"])

                    # Persist HumanInput to Neo4j
                    CPQueue._persist_human_input(delta, cp.cp_id)

                    if cp.hop_count < 3:
                        cp.hop_count += 1
                        os.makedirs("/tmp/denis", exist_ok=True)
                        with open("/tmp/denis/next_cp.json", "w") as f:
                            json.dump(cp.to_dict(), f, indent=2, default=str)
                    logger.info(
                        f"Human input processed: {delta['new_constraints']}, dnt: {delta['new_do_not_touch']}"
                    )

            except Exception as e:
                logger.error(f"Error in cp_received: {e}")

        elif os.path.exists(PHASE_COMPLETE_FILE):
            try:
                with open(PHASE_COMPLETE_FILE) as f:
                    data = json.load(f)
                os.remove(PHASE_COMPLETE_FILE)

                from control_plane.approval_popup import show_phase_complete

                decision, adj = show_phase_complete(
                    data["phase_num"], data["completed"], data["failed"], data["next_phase_summary"]
                )
                logger.info(f"Phase {data['phase_num']} decision: {decision}")

                if decision == "adjust" and adj:
                    from control_plane.human_input_processor import process_human_input
                    from control_plane.models import ContextPack
                    from control_plane.cp_queue import CPQueue

                    current_cp_data = data.get("current_cp", {})
                    if current_cp_data:
                        cp = ContextPack(**current_cp_data)
                        delta = process_human_input(adj, cp)
                        if delta["mission_delta"]:
                            cp.mission += f"\nAJUSTE HUMANO: {delta['mission_delta']}"
                        cp.do_not_touch.extend(delta["new_do_not_touch"])

                        # Persist HumanInput to Neo4j
                        CPQueue._persist_human_input(delta, cp.cp_id)

                        if cp.hop_count < 3:
                            cp.hop_count += 1
                            os.makedirs("/tmp/denis", exist_ok=True)
                            with open("/tmp/denis/next_cp.json", "w") as f:
                                json.dump(cp.to_dict(), f, indent=2, default=str)
                        logger.info(f"Phase adjust processed: {delta['new_constraints']}")

            except Exception as e:
                logger.error(f"Error in phase_complete: {e}")

        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Denis Control Plane Daemon")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=POLL_INTERVAL,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=300,
        help="Max wait time for agent result in seconds",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once instead of daemon loop",
    )
    args = parser.parse_args()

    if args.once:
        agent_result = wait_for_agent_result(timeout=args.max_wait)
        if agent_result:
            cp_dict = generate_context_pack(agent_result)
            approved = trigger_approval_popup(cp_dict)
            write_approved_cp(cp_dict, approved)
            clear_agent_result()
            sys.exit(0 if approved else 1)
        sys.exit(2)
    else:
        run_daemon(poll_interval=args.poll_interval, max_wait=args.max_wait)


if __name__ == "__main__":
    main()
