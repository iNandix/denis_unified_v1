"""Message Composer - Single Source of Truth for Message Enrichment.

Implements the message_composition_contract:
- Enriches messages with persona, policy, context, tool outputs
- Called ONCE before InferenceRouter
- Router does NOT modify messages
- Enforces anti-leak rules
- Generates snapshots for audit
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MessageBlock:
    """A block in the message composition."""

    block_type: str  # system_persona, developer_policy, task_state, etc.
    content: str
    order: int


@dataclass
class ComposerSnapshot:
    """Snapshot of message composition for audit."""

    request_id: str
    ts_utc: str
    original_message: str
    blocks_added: List[str]
    blocks_removed: List[str]
    final_message_hash: str
    final_message_size: int
    block_list: List[str]


class MessageComposer:
    """Single point of message enrichment.

    Context blocks order (as per contract):
    1. system_persona (voz + anti-bot rules)
    2. developer_policy (no claims w/o evidence, offline gate, tool rules)
    3. task_state (goal, constraints, acceptance)
    4. intent_summary (Intent_v1 compact)
    5. action_plan_summary (ActionPlan_v1 compact, if exists)
    6. conversation_window (recent turns)
    7. tool_outputs (as tool messages)
    8. current_user_message
    """

    SYSTEM_PERSONA = """Eres DENIS, un asistente de IA útil y directo.
Respondes de forma clara y concisa.
No incluyas información interna sobre cómo llegas a tus conclusiones.
Si no tienes suficiente información, preguntas."""

    DEVELOPER_POLICY = """POLÍTICAS DE DESARROLLO:
- No afirmes que ejecutaste código o comandos sin evidencia.
- Si estás offline, no intentes acceder a internet.
- Si no puedes ejecutar una herramienta, explica por qué.
- Siempre que ejecutes algo, reporta el resultado真实的.
- No inventes resultados de tests o comandos."""

    def __init__(self, reports_dir: Optional[Path] = None):
        self.reports_dir = reports_dir or Path(
            "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/_reports"
        )

    def compose(
        self,
        user_message: str,
        intent_result: Optional[Any] = None,
        action_plan: Optional[Any] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        tool_outputs: Optional[List[Dict[str, str]]] = None,
        task_goal: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Compose messages for inference.

        Returns a list of message dicts ready for InferenceRouter.
        """
        blocks_added = []
        messages: List[Dict[str, str]] = []

        messages.append({"role": "system", "content": self.SYSTEM_PERSONA})
        blocks_added.append("system_persona")

        messages.append({"role": "system", "content": self.DEVELOPER_POLICY})
        blocks_added.append("developer_policy")

        if task_goal or constraints:
            task_state = self._build_task_state(task_goal, constraints)
            messages.append({"role": "system", "content": task_state})
            blocks_added.append("task_state")

        if intent_result:
            intent_summary = self._build_intent_summary(intent_result)
            messages.append({"role": "system", "content": intent_summary})
            blocks_added.append("intent_summary")

        if action_plan:
            plan_summary = self._build_plan_summary(action_plan)
            messages.append({"role": "system", "content": plan_summary})
            blocks_added.append("action_plan_summary")

        if conversation_history:
            for msg in conversation_history[-4:]:
                messages.append(msg)
            blocks_added.append("conversation_window")

        if tool_outputs:
            for output in tool_outputs:
                messages.append(
                    {
                        "role": "tool" if "tool" in output else "assistant",
                        "content": output.get("content", str(output)),
                        "tool_call_id": output.get("tool_call_id"),
                    }
                )
            blocks_added.append("tool_outputs")

        messages.append({"role": "user", "content": user_message})

        final_content = "\n".join(m["content"] for m in messages)
        snapshot = ComposerSnapshot(
            request_id="",
            ts_utc=datetime.now(timezone.utc).isoformat(),
            original_message=user_message,
            blocks_added=blocks_added,
            blocks_removed=[],
            final_message_hash=hashlib.sha256(final_content.encode()).hexdigest()[:16],
            final_message_size=len(final_content),
            block_list=blocks_added,
        )

        return messages, snapshot

    def _build_task_state(
        self, goal: Optional[str], constraints: Optional[Dict[str, Any]]
    ) -> str:
        """Build task state block."""
        parts = ["## Estado de la Tarea"]
        if goal:
            parts.append(f"Objetivo: {goal}")
        if constraints:
            if constraints.get("offline_mode"):
                parts.append("Modo: Offline (sin internet)")
            if constraints.get("read_only"):
                parts.append("Modo: Solo lectura")
            if constraints.get("max_steps"):
                parts.append(f"Límite de pasos: {constraints['max_steps']}")
        return "\n".join(parts)

    def _build_intent_summary(self, intent_result: Any) -> str:
        """Build intent summary block."""
        parts = ["## Intención Detectada"]

        if hasattr(intent_result, "intent"):
            parts.append(
                f"Intent: {intent_result.intent.value if hasattr(intent_result.intent, 'value') else intent_result.intent}"
            )

        if hasattr(intent_result, "confidence_band"):
            parts.append(f"Confianza: {intent_result.confidence_band}")

        if hasattr(intent_result, "tone") and intent_result.tone:
            tone = (
                intent_result.tone.value
                if hasattr(intent_result.tone, "value")
                else intent_result.tone
            )
            parts.append(f"Tono: {tone}")

        if (
            hasattr(intent_result, "acceptance_criteria")
            and intent_result.acceptance_criteria
        ):
            parts.append("Criterios de aceptación:")
            for criterion in intent_result.acceptance_criteria[:3]:
                parts.append(f"  - {criterion}")

        return "\n".join(parts)

    def _build_plan_summary(self, action_plan: Any) -> str:
        """Build action plan summary block."""
        parts = ["## Plan de Acción"]

        if hasattr(action_plan, "candidate_id"):
            parts.append(f"Plan: {action_plan.candidate_id}")

        if hasattr(action_plan, "steps"):
            parts.append(f"Pasos: {len(action_plan.steps)}")
            for i, step in enumerate(action_plan.steps[:3], 1):
                if hasattr(step, "description"):
                    parts.append(f"  {i}. {step.description}")

        if hasattr(action_plan, "is_mutating"):
            parts.append(f"Mutativo: {'Sí' if action_plan.is_mutating else 'No'}")

        return "\n".join(parts)

    def detect_double_system(self, messages: List[Dict[str, str]]) -> bool:
        """Detect if there are duplicate system prompts."""
        system_count = sum(1 for m in messages if m.get("role") == "system")
        return system_count > 2

    def save_snapshot(
        self,
        snapshot: ComposerSnapshot,
        request_id: str,
    ) -> Path:
        """Save composition snapshot to _reports."""
        ts = (
            datetime.now(timezone.utc)
            .isoformat()
            .replace(":", "")
            .replace("-", "")
            .replace("T", "_")
        )
        filename = f"{ts}_{request_id}_composer_snapshot.json"
        path = self.reports_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(
                {
                    "request_id": request_id,
                    "ts_utc": snapshot.ts_utc,
                    "original_message_length": len(snapshot.original_message),
                    "blocks_added": snapshot.blocks_added,
                    "blocks_removed": snapshot.blocks_removed,
                    "final_message_hash": snapshot.final_message_hash,
                    "final_message_size": snapshot.final_message_size,
                    "block_list": snapshot.block_list,
                },
                f,
                indent=2,
            )

        return path


def save_router_input_snapshot(
    messages: List[Dict[str, str]],
    reports_dir: Path,
    request_id: str,
) -> Path:
    """Save router input messages snapshot."""
    ts = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace(":", "")
        .replace("-", "")
        .replace("T", "_")
    )
    filename = f"{ts}_{request_id}_router_input_messages_snapshot.json"
    path = reports_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    content_hash = hashlib.sha256(
        json.dumps(messages, sort_keys=True).encode()
    ).hexdigest()[:16]

    snapshot = {
        "request_id": request_id,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "message_count": len(messages),
        "content_hash": content_hash,
        "block_types": [m.get("role") for m in messages],
    }

    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)

    return path
