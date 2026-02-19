#!/usr/bin/env python3
"""Constitución Level0 para Denis - Principios inmutables.

La constitución define los principios que NUNCA pueden ser violados
por ningún sistema (Rasa, ParLAI, ControlPlane, Memoria, etc.)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConstitutionalRule:
    """Una regla constitucional."""

    id: str
    title: str
    rule: str
    violation_severity: str  # critical, high, medium, low
    mutable: bool


class DenisConstitution:
    """
    Constitución de Denis - Principios inmutables.

    Nivel 0 contratos que NUNCA pueden cambiar:
    - L0.IDENTITY.CORE     - Continuity of identity
    - L0.SAFETY.NO_SECRET_LOGGING - No secret leakage
    - L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD
    - L0.RESILIENCE.ROLLBACK_REQUIRED
    """

    RULES = {
        "L0.IDENTITY.CORE": ConstitutionalRule(
            id="L0.IDENTITY.CORE",
            title="Continuity of Denis identity",
            rule="Core identity metadata must remain traceable across all phases.",
            violation_severity="critical",
            mutable=False,
        ),
        "L0.SAFETY.NO_SECRET_LOGGING": ConstitutionalRule(
            id="L0.SAFETY.NO_SECRET_LOGGING",
            title="No secret leakage",
            rule="Tokens, passwords, and sensitive secrets must not be logged or serialized.",
            violation_severity="critical",
            mutable=False,
        ),
        "L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD": ConstitutionalRule(
            id="L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD",
            title="Human approval for self-modification",
            rule="Any autopoiesis execution beyond sandbox requires explicit human approval.",
            violation_severity="critical",
            mutable=False,
        ),
        "L0.RESILIENCE.ROLLBACK_REQUIRED": ConstitutionalRule(
            id="L0.RESILIENCE.ROLLBACK_REQUIRED",
            title="Rollback always available",
            rule="Each phase change must include a tested rollback command or script.",
            violation_severity="high",
            mutable=False,
        ),
    }

    def __init__(self):
        self._violations: List[Dict] = []

    def check_action(self, action: Dict) -> tuple[bool, List[str]]:
        """
        Verifica que una acción no viole la constitución.

        Returns: (is_allowed, violations)
        """
        violations = []

        if not action:
            return True, []

        action_type = action.get("type", "")
        payload = action.get("payload", {})

        for rule_id, rule in self.RULES.items():
            if rule.violation_severity == "critical":
                if rule_id == "L0.SAFETY.NO_SECRET_LOGGING":
                    if self._contains_secret(payload):
                        violations.append(f"VIOLATION: {rule_id} - {rule.title}")

                elif rule_id == "L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD":
                    if action_type in ["self_modify", "autopoiesis"] and not action.get(
                        "human_approved"
                    ):
                        violations.append(f"VIOLATION: {rule_id} - {rule.title}")

        if violations:
            self._violations.append(
                {
                    "action": action,
                    "violations": violations,
                    "timestamp": "now",
                }
            )
            logger.warning(f"Constitutional violation detected: {violations}")
            return False, violations

        return True, []

    def _contains_secret(self, data: Dict) -> bool:
        """Check if data contains secrets."""
        secret_patterns = ["password", "token", "secret", "api_key", "credential"]
        data_str = str(data).lower()
        return any(p in data_str for p in secret_patterns)

    def get_rules(self) -> List[ConstitutionalRule]:
        """Get all constitutional rules."""
        return list(self.RULES.values())

    def log_violation(self, violation: Dict):
        """Log a constitutional violation."""
        self._violations.append(violation)

    def get_violations(self) -> List[Dict]:
        """Get all logged violations."""
        return self._violations


_constitution: Optional[DenisConstitution] = None


def get_constitution() -> DenisConstitution:
    """Get Denis Constitution singleton."""
    global _constitution
    if _constitution is None:
        _constitution = DenisConstitution()
    return _constitution


__all__ = ["DenisConstitution", "ConstitutionalRule", "get_constitution"]
