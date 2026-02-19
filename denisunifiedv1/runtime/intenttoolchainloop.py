import json
import os
from typing import Any, Dict


def write_agent_result(
    intent: str,
    constraints: list,
    mission_completed: str,
    success: bool,
    session_id: str,
    repo_id: str,
    repo_name: str,
    branch: str,
    model: str,
    tokens_used: int,
) -> None:
    os.makedirs("/tmp/denis", exist_ok=True)

    agent_result = {
        "intent": intent,
        "constraints": constraints,
        "mission_completed": mission_completed[:200],
        "success": success,
        "session_id": session_id,
        "repo_id": repo_id,
        "repo_name": repo_name,
        "branch": branch,
        "model": model,
        "tokens_used": tokens_used,
    }

    try:
        raw = open("/tmp/denis/sessionid.txt").read().strip()
        parts = (raw + "||||").split("|")
        agent_result["repo_id"] = parts[1] or repo_id
        agent_result["repo_name"] = parts[2] or repo_name
        agent_result["branch"] = parts[3] or branch
    except Exception:
        pass

    with open("/tmp/denis/agentresult.json", "w") as f:
        json.dump(agent_result, f, indent=2)
