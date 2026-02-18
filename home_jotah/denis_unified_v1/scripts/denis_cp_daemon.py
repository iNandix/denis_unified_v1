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
    """Trigger zenity approval popup."""
    from control_plane.approval_popup import ApprovalPopup
    from control_plane.cp_generator import ContextPack

    cp = ContextPack.from_dict(cp_dict)
    popup = ApprovalPopup()

    logger.info(f"Showing approval popup for CP {cp.cp_id}")
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
    """Main daemon loop."""
    logger.info("Denis Control Plane Daemon started")
    logger.info(f"Monitoring: {AGENT_RESULT_FILE}")
    logger.info(f"Output: {CP_OUTPUT_FILE}")

    while True:
        agent_result = wait_for_agent_result(timeout=max_wait)

        if not agent_result:
            logger.warning("No agent result, continuing to poll...")
            time.sleep(poll_interval)
            continue

        try:
            cp_dict = generate_context_pack(agent_result)
            approved = trigger_approval_popup(cp_dict)
            write_approved_cp(cp_dict, approved)
            clear_agent_result()

            if approved:
                logger.info("✅ Approval flow completed successfully")
            else:
                logger.info("❌ Approval flow rejected or cancelled")

        except Exception as e:
            logger.error(f"Error in approval flow: {e}")
            import traceback

            traceback.print_exc()
            time.sleep(poll_interval)

        time.sleep(poll_interval)


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
