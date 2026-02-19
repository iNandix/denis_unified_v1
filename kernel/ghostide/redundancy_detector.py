import json
import hashlib
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from kernel.ghostide.symbolgraph import SymbolGraph


class RedundancyDetector:
    """
    Detector de redundancia con validación de patrones.

    El control plane NO bloquea el aprendizaje - bloquea la consolidación prematura.
    Un patrón solo se auto-injecta si pasa todos los filtros:

    frequency >= 3       → candidato
    success_rate >= 0.8  → validado
    no conflicts         → aprobado
    last_validated < 7 days → no drift
    → ENTONCES auto_inject = True
    """

    LEARNED_PATTERNS_FILE = "/tmp/denis/learnedpatterns.json"

    # Thresholds
    MIN_FREQUENCY_FOR_CANDIDATE = 3
    MIN_SUCCESS_RATE = 0.8
    MAX_DAYS_SINCE_VALIDATION = 7
    MAX_DAYS_SINCE_SEEN = 14
    CONFLICT_THRESHOLD = 0.6

    def __init__(self, session_id: str, symbol_graph: SymbolGraph):
        self.session_id = session_id
        self.symbol_graph = symbol_graph
        self.learned_patterns: Dict[str, Any] = {}
        self.load_learned_patterns()

    def record_execution(
        self, intent: str, constraints: List[str], tasks_run: List[str], success: bool = True
    ) -> None:
        """
        Registra una ejecución del patrón.

        Args:
            intent: El intent ejecutado
            constraints: Constraints activos
            tasks_run: Tareas ejecutadas
            success: Si la ejecución fue exitosa (affecta success_rate)
        """
        pattern_key = hashlib.sha256((intent + "".join(sorted(constraints))).encode()).hexdigest()[
            :12
        ]
        name = f"pattern:{intent}:{','.join(sorted(constraints)[:3])}"

        self.symbol_graph.upsert_hygiene_pattern(name, intent, constraints, tasks_run)

        # Actualizar frecuencia y success_rate
        self._update_pattern_stats(name, success)

        self.learned_patterns[name] = {
            "intent": intent,
            "constraints": constraints,
            "tasks": tasks_run,
            "frequency": self.learned_patterns.get(name, {}).get("frequency", 0) + 1,
            "success_rate": self.learned_patterns.get(name, {}).get("success_rate", 1.0),
            "last_executed": datetime.now(timezone.utc).isoformat(),
        }
        self._persist_learned_patterns()

    def _update_pattern_stats(self, name: str, success: bool) -> None:
        """Actualiza estadísticas del patrón."""
        current = self.learned_patterns.get(name, {})

        frequency = current.get("frequency", 0)
        total_success = current.get("total_success", 0)

        if success:
            total_success += 1

        new_frequency = frequency + 1
        new_success_rate = total_success / new_frequency if new_frequency > 0 else 0.0

        self.learned_patterns[name] = {
            **current,
            "frequency": new_frequency,
            "total_success": total_success,
            "success_rate": new_success_rate,
            "last_validated": datetime.now(timezone.utc).isoformat(),
        }

    def validate_pattern(self, pattern: Dict[str, Any]) -> tuple[bool, str]:
        """
        Valida un patrón contra los criterios del control plane.

        Returns: (is_valid, reason)
        """
        frequency = pattern.get("frequency", 0)
        success_rate = pattern.get("success_rate", 0.0)

        # 1. Frecuencia mínima
        if frequency < self.MIN_FREQUENCY_FOR_CANDIDATE:
            return False, f"frequency {frequency} < {self.MIN_FREQUENCY_FOR_CANDIDATE}"

        # 2. Success rate mínimo
        if success_rate < self.MIN_SUCCESS_RATE:
            return False, f"success_rate {success_rate:.2f} < {self.MIN_SUCCESS_RATE}"

        # 3. Validación reciente (pattern drift check)
        last_validated = pattern.get("last_validated")
        if last_validated:
            try:
                last_val = datetime.fromisoformat(last_validated.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - last_val).days
                if days_since > self.MAX_DAYS_SINCE_VALIDATION:
                    return False, f"pattern_drift: last_validated {days_since} days ago"
            except Exception:
                pass

        # 4. Conflict check
        conflicts = self._check_conflicts(pattern)
        if conflicts:
            return False, f"conflict_with: {conflicts}"

        return True, "approved"

    def _check_conflicts(self, pattern: Dict[str, Any]) -> List[str]:
        """Detecta patrones conflictivos."""
        conflicts = []
        pattern_intent = pattern.get("intent", "")
        pattern_constraints = set(pattern.get("constraints", []))

        for name, other in self.learned_patterns.items():
            if name == pattern.get("name"):
                continue

            other_constraints = set(other.get("constraints", []))

            # Buscar constraints opuestos
            overlap = pattern_constraints & other_constraints
            if overlap:
                # Mismos constraints pero intents distintos = potencial conflicto
                if other.get("intent") != pattern_intent:
                    conflicts.append(name)

        return conflicts[:3]  # Max 3 conflicts

    def get_auto_inject_for(self, intent: str, constraints: List[str]) -> List[str]:
        """
        Obtiene tareas para auto-inject SIEMPRE validando primero.

        Un patrón NO se inyecta si no pasa todos los filtros.
        """
        try:
            patterns = self.symbol_graph.get_auto_inject_patterns(intent, constraints, threshold=3)
            if not patterns:
                return []

            all_tasks = []
            valid_count = 0
            blocked_count = 0

            for p in patterns:
                # Añadir metadata local si existe
                pattern_with_meta = {**p, **self.learned_patterns.get(p.get("name", ""), {})}

                # VALIDAR antes de usar
                is_valid, reason = self.validate_pattern(pattern_with_meta)

                if is_valid:
                    all_tasks.extend(p.get("tasks", []))
                    valid_count += 1
                else:
                    blocked_count += 1
                    print(f"[RedundancyDetector] Pattern blocked: {reason}")

            if blocked_count > 0:
                print(
                    f"[RedundancyDetector] {valid_count} patterns approved, {blocked_count} blocked"
                )

            # Dedupe
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

    def get_pattern_health(self) -> Dict[str, Any]:
        """Retorna salud de todos los patrones."""
        health = {
            "total_patterns": len(self.learned_patterns),
            "approved": 0,
            "blocked": 0,
            "needs_review": 0,
            "pattern_details": [],
        }

        for name, pattern in self.learned_patterns.items():
            is_valid, reason = self.validate_pattern(pattern)

            detail = {
                "name": name,
                "frequency": pattern.get("frequency", 0),
                "success_rate": pattern.get("success_rate", 0.0),
                "status": "approved" if is_valid else reason,
            }

            if is_valid:
                health["approved"] += 1
            elif "conflict" in reason:
                health["needs_review"] += 1
            else:
                health["blocked"] += 1

            health["pattern_details"].append(detail)

        return health

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
