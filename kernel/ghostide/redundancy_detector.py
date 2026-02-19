import json
import hashlib
import os
from typing import List, Dict, Any, Optional
from kernel.ghostide.symbolgraph import SymbolGraph


class RedundancyDetector:
    LEARNED_PATTERNS_FILE = "/tmp/denis/learnedpatterns.json"

    def __init__(self, session_id: str, symbol_graph: SymbolGraph):
        self.session_id = session_id
        self.symbol_graph = symbol_graph
        self.learned_patterns: Dict[str, Any] = {}
        self.load_learned_patterns()

    def record_execution(self, intent: str, constraints: List[str], tasks_run: List[str]) -> None:
        pattern_key = hashlib.sha256((intent + "".join(sorted(constraints))).encode()).hexdigest()[
            :12
        ]
        name = f"pattern:{intent}:{','.join(sorted(constraints)[:3])}"

        self.symbol_graph.upsert_hygiene_pattern(name, intent, constraints, tasks_run)
        frequency = self.symbol_graph.increment_pattern_frequency(name)

        self.learned_patterns[name] = {
            "intent": intent,
            "constraints": constraints,
            "tasks": tasks_run,
            "frequency": frequency,
        }
        self._persist_learned_patterns()

    def get_auto_inject_for(self, intent: str, constraints: List[str]) -> List[str]:
        try:
            patterns = self.symbol_graph.get_auto_inject_patterns(intent, constraints, threshold=3)
            if not patterns:
                return []

            all_tasks = []
            for p in patterns:
                all_tasks.extend(p.get("tasks", []))

            seen = set()
            unique_tasks = []
            for t in all_tasks:
                if t not in seen:
                    seen.add(t)
                    unique_tasks.append(t)

            return unique_tasks
        except Exception as e:
            print(f"[RedundancyDetector] get_auto_inject_for failed: {e}")
            return []

    def suggest_new_implicit_tasks(self) -> List[Dict[str, Any]]:
        try:
            all_patterns = self.symbol_graph.get_all_patterns()
            candidates = []
            for p in all_patterns:
                if p.get("frequency", 0) >= 10:
                    candidates.append(
                        {
                            "name": p.get("name"),
                            "intent": p.get("intent"),
                            "constraints": p.get("constraints", []),
                            "tasks": p.get("tasks", []),
                            "frequency": p.get("frequency"),
                        }
                    )
            return candidates
        except Exception as e:
            print(f"[RedundancyDetector] suggest_new_implicit_tasks failed: {e}")
            return []

    def export_learned_patterns(self) -> Dict[str, Any]:
        return self.learned_patterns.copy()

    def load_learned_patterns(self) -> None:
        if not os.path.exists(self.LEARNED_PATTERNS_FILE):
            return

        try:
            with open(self.LEARNED_PATTERNS_FILE, "r") as f:
                self.learned_patterns = json.load(f)

            for name, data in self.learned_patterns.items():
                self.symbol_graph.upsert_hygiene_pattern(
                    name, data.get("intent", ""), data.get("constraints", []), data.get("tasks", [])
                )
        except Exception as e:
            print(f"[RedundancyDetector] load_learned_patterns error: {e}")

    def _persist_learned_patterns(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.LEARNED_PATTERNS_FILE), exist_ok=True)

            existing = {}
            if os.path.exists(self.LEARNED_PATTERNS_FILE):
                with open(self.LEARNED_PATTERNS_FILE, "r") as f:
                    existing = json.load(f)

            existing.update(self.learned_patterns)

            with open(self.LEARNED_PATTERNS_FILE, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            print(f"[RedundancyDetector] _persist_learned_patterns error: {e}")
