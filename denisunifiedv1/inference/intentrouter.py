import hashlib
import logging
import threading
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from kernel.ghostide.symbolgraph import SymbolGraph
from kernel.ghostide.redundancy_detector import RedundancyDetector
from denisunifiedv1.inference.implicittasks import get_implicit_tasks

logger = logging.getLogger(__name__)


@dataclass
class RoutedRequest:
    intent: str
    constraints: List[str]
    implicit_tasks: List[str]
    session_id: str
    symbols: List[str]
    repo_id: str = ""
    repo_name: str = ""
    branch: str = "main"
    model: str = "llamaLocal"


class IntentRouter:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or "default"
        self._symbol_graph = SymbolGraph()
        self._detector = None
        try:
            from kernel.ghostide.redundancy_detector import RedundancyDetector

            self._detector = RedundancyDetector(
                session_id=self._read_session_id(),
                symbol_graph=self._symbol_graph,
            )
            self._detector.load_learned_patterns()
        except Exception as _exc:
            self._detector = None
            logger.debug("RedundancyDetector unavailable: %s", _exc)

    def _read_session_id(self) -> str:
        try:
            raw = open("/tmp/denis/sessionid.txt").read().strip()
            return raw.split("|")[0] if "|" in raw else raw
        except Exception:
            return "default"

    def _read_repo_parts(self) -> tuple:
        try:
            raw = open("/tmp/denis/sessionid.txt").read().strip()
            parts = (raw + "||||").split("|")
            return parts[1], parts[2] or "unknown", parts[3] or "main"
        except Exception:
            return "", "unknown", "main"

    def route(
        self, intent: str, constraints: List[str] = None, context: Dict[str, Any] = None
    ) -> RoutedRequest:
        if constraints is None:
            constraints = []

        implicit_tasks = self._build_implicit_tasks(intent, constraints)

        repo_id, repo_name, branch = self._read_repo_parts()

        routed = RoutedRequest(
            intent=intent,
            constraints=constraints,
            implicit_tasks=implicit_tasks,
            session_id=self.session_id,
            symbols=[],
            repo_id=repo_id,
            repo_name=repo_name,
            branch=branch,
        )

        if self._detector is not None:
            threading.Thread(
                target=self._detector.record_execution,
                args=(intent, constraints, implicit_tasks),
                daemon=True,
            ).start()

        return routed

    def build_implicit_tasks(self, intent: str, constraints: List[str]) -> List[str]:
        auto = []
        if self._detector is not None:
            try:
                auto = self._detector.get_auto_inject_for(intent, constraints)
            except Exception as exc:
                logger.debug("getAutoInjectFor failed (skip): %s", exc)
        static = get_implicit_tasks(intent)
        return list(dict.fromkeys(auto + static))

    def _build_implicit_tasks(self, intent: str, constraints: List[str]) -> List[str]:
        return self.build_implicit_tasks(intent, constraints)


def route_input(
    intent: str, session_id: str = None, constraints: List[str] = None
) -> RoutedRequest:
    router = IntentRouter(session_id=session_id)
    return router.route(intent, constraints)
