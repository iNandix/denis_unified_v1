#!/usr/bin/env python3
"""
Agent Result Writer - Writes agent completion results for daemon consumption.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from control_plane.repo_context import RepoContext

logger = logging.getLogger(__name__)

AGENT_RESULT_FILE = "/tmp/denis_agent_result.json"


def write_agent_result(
    intent: str,
    files_touched: List[str],
    constraints: List[str],
    mission_completed: bool,
    success: bool,
    cwd: str = None,
    implicit_tasks: List[str] = None,
    acceptance_criteria: List[str] = None,
    output_file: str = None,
) -> str:
    """
    Write agent result to file for daemon consumption.

    Returns path to the result file.
    """
    repo_ctx = RepoContext(cwd=cwd or os.getcwd())

    result = {
        "intent": intent,
        "files_touched": files_touched,
        "constraints": constraints,
        "mission_completed": mission_completed,
        "success": success,
        "cwd": cwd or os.getcwd(),
        "implicit_tasks": implicit_tasks or [],
        "acceptance_criteria": acceptance_criteria or [],
        "repo": repo_ctx.to_dict(),
    }

    filepath = output_file or AGENT_RESULT_FILE

    try:
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Agent result written to {filepath}")
    except Exception as e:
        logger.error(f"Failed to write agent result: {e}")

    return filepath


def read_agent_result(filepath: str = None) -> Optional[Dict[str, Any]]:
    """Read agent result from file."""
    filepath = filepath or AGENT_RESULT_FILE

    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read agent result: {e}")
        return None


def clear_agent_result(filepath: str = None) -> None:
    """Clear agent result file after processing."""
    filepath = filepath or AGENT_RESULT_FILE

    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Agent result cleared: {filepath}")
    except Exception as e:
        logger.error(f"Failed to clear agent result: {e}")


__all__ = [
    "write_agent_result",
    "read_agent_result",
    "clear_agent_result",
    "AGENT_RESULT_FILE",
]
