from dataclasses import dataclass
from typing import Any, Dict, List

IMPLICITTASKS = {
    "crea_endpoint": [
        "validate_input_schema",
        "add_cors_headers",
        "add_request_logging",
        "handle_errors_gracefully",
    ],
    "crea_tests": [
        "setup_test_environment",
        "teardown_after_tests",
        "assert_response_status",
        "assert_json_schema",
    ],
    "crea_db_model": ["validate_foreign_keys", "add_timestamps", "add_soft_delete"],
    "crea_api_client": ["add_retry_logic", "add_timeout", "validate_response"],
    "crea_middleware": ["log_request_id", "add_cors", "handle_auth"],
}


def get_implicit_tasks(intent: str) -> list:
    intent_lower = intent.lower()

    for key, tasks in IMPLICITTASKS.items():
        if key in intent_lower:
            return tasks

    return []


@dataclass
class EnrichedContext:
    session_id: str
    do_not_touch_auto: List[str]
    context_prefilled: Dict[str, Any]
    implicit_tasks: List[str]
    modified_paths: List[str] = None

    def __post_init__(self):
        if self.modified_paths is None:
            self.modified_paths = []


def enrich_with_session(
    session_id: str,
    intent: str,
    constraints: List[str],
) -> EnrichedContext:
    static_tasks = IMPLICITTASKS.get(intent, [])
    empty = EnrichedContext(
        session_id=session_id,
        do_not_touch_auto=[],
        context_prefilled={},
        implicit_tasks=static_tasks,
        modified_paths=[],
    )
    try:
        sid = session_id
        try:
            raw = open("/tmp/denis/sessionid.txt").read().strip()
            sid = raw.split("|")[0] if "|" in raw else raw
        except Exception:
            pass

        from kernel.ghostide.contextharvester import ContextHarvester
        from kernel.ghostide.symbolgraph import SymbolGraph
        from kernel.ghostide.redundancy_detector import RedundancyDetector

        ctx = ContextHarvester(session_id=sid, watch_paths=[]).get_session_context()

        sg = SymbolGraph()
        det = RedundancyDetector(session_id=sid, symbol_graph=sg)
        det.load_learned_patterns()
        auto_tasks = det.get_auto_inject_for(intent, constraints)

        merged = list(dict.fromkeys(auto_tasks + static_tasks))

        return EnrichedContext(
            session_id=sid,
            do_not_touch_auto=ctx.get("do_not_touch_auto", []),
            context_prefilled=ctx.get("context_prefilled", {}),
            implicit_tasks=merged,
            modified_paths=ctx.get("modified_paths", []),
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("enrichWithSession fail-open: %s", exc)
        return empty
