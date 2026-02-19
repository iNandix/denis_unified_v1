import hashlib
import threading
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from kernel.ghostide.symbolgraph import SymbolGraph
from kernel.ghostide.redundancy_detector import RedundancyDetector
from denisunifiedv1.inference.implicittasks import get_implicit_tasks


@dataclass
class RoutedRequest:
    intent: str
    constraints: List[str]
    implicit_tasks: List[str]
    session_id: str
    symbols: List[str]


class IntentRouter:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or "default"
        self.symbol_graph = SymbolGraph()
        self.detector = RedundancyDetector(self.session_id, self.symbol_graph)
        self.detector.load_learned_patterns()

    def route(
        self, intent: str, constraints: List[str] = None, context: Dict[str, Any] = None
    ) -> RoutedRequest:
        if constraints is None:
            constraints = []

        implicit_tasks = self._build_implicit_tasks(intent, constraints)

        routed = RoutedRequest(
            intent=intent,
            constraints=constraints,
            implicit_tasks=implicit_tasks,
            session_id=self.session_id,
            symbols=[],
        )

        thread = threading.Thread(
            target=self._record_execution_background,
            args=(intent, constraints, implicit_tasks),
            daemon=True,
        )
        thread.start()

        return routed

    def _build_implicit_tasks(self, intent: str, constraints: List[str]) -> List[str]:
        auto_tasks = []
        try:
            auto_tasks = self.detector.get_auto_inject_for(intent, constraints)
        except Exception as e:
            pass

        static_tasks = get_implicit_tasks(intent)

        all_tasks = []
        seen = set()
        for t in auto_tasks + static_tasks:
            if t not in seen:
                seen.add(t)
                all_tasks.append(t)

        return all_tasks

    def _record_execution_background(
        self, intent: str, constraints: List[str], implicit_tasks: List[str]
    ) -> None:
        try:
            self.detector.record_execution(intent, constraints, implicit_tasks)
        except Exception as e:
            pass


def route_input(
    intent: str, session_id: str = None, constraints: List[str] = None
) -> RoutedRequest:
    router = IntentRouter(session_id=session_id)
    return router.route(intent, constraints)
