from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


REPORTS_DIR = Path(os.getenv("DENIS_REPORTS_DIR", "denis_unified_v1/_reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TOOLCHAIN_STEP_PATH = REPORTS_DIR / "toolchain_step.jsonl"


def emit_tool_step(step: Dict[str, Any]) -> bool:
    """
    Canonical P1.3 step logger.
    Writes JSONL and (optionally) projects to graph if projection hook exists.
    """
    try:
        # Enforce minimal fields
        step.setdefault("ts", time.time())
        if "request_id" not in step:
            step["request_id"] = ""
        if "step_id" not in step:
            step["step_id"] = ""

        # Write JSONL
        with TOOLCHAIN_STEP_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(step, ensure_ascii=False) + "\n")

        # Optional graph projection (best-effort, no hard dependency)
        try:
            from denis_unified_v1.delivery.graph_projection import get_voice_projection  # type: ignore
            proj = get_voice_projection()

            # Prefer a dedicated method if you have one
            if hasattr(proj, "project_tool_step"):
                proj.project_tool_step(**step)  # type: ignore
            else:
                # Best-effort generic: MERGE Tool + ToolchainStep if hooks exist
                if hasattr(proj, "project_tool"):
                    proj.project_tool(
                        name=step.get("tool", ""),
                        domain=step.get("domain", ""),
                        mutability=step.get("mutability", ""),
                        risk=step.get("risk", ""),
                    )
                if hasattr(proj, "project_generic_step"):
                    proj.project_generic_step(step)  # type: ignore
        except Exception:
            # Graph is optional here; never fail the run because of projection.
            pass

        return True
    except Exception:
        return False
