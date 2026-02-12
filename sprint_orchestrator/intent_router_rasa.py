"""Rasa-first intent routing with confidence gate and LLM fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any
import urllib.error
import urllib.request

from .config import SprintOrchestratorConfig
from .providers import merged_env


def _raw_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _raw_float(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


@dataclass(frozen=True)
class IntentRoute:
    source: str
    intent: str
    confidence: float
    action: str
    slots: dict[str, Any] = field(default_factory=dict)
    fallback_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class RasaIntentRouter:
    """Deterministic intent router with explicit failover path."""

    _ACTION_MAP = {
        "start_sprint": "autodispatch",
        "assign_worker": "dispatch",
        "dispatch_task": "dispatch",
        "git_status": "projects",
        "run_validation": "validate",
        "tail_logs": "tail",
        "approve_change": "note",
        "rollback": "validate",
        "show_dashboard": "dashboard",
        "mcp_tools": "mcp_tools",
    }

    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        env = merged_env(config)
        self.enabled = _raw_bool(
            env.get("DENIS_USE_RASA_GATE") or env.get("DENIS_SPRINT_RASA_ENABLED"),
            False,
        )
        self.parse_url = (
            env.get("DENIS_SPRINT_RASA_URL")
            or env.get("DENIS_RASA_URL")
            or "http://127.0.0.1:5005/model/parse"
        ).strip()
        self.timeout_sec = max(
            1.0,
            float(env.get("DENIS_SPRINT_RASA_TIMEOUT_SEC") or "5"),
        )
        self.min_confidence = _raw_float(env.get("DENIS_SPRINT_RASA_MIN_CONFIDENCE"), 0.85)
        self.fallback_provider = (env.get("DENIS_SPRINT_RASA_FALLBACK_PROVIDER") or "").strip()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "parse_url": self.parse_url,
            "timeout_sec": self.timeout_sec,
            "min_confidence": self.min_confidence,
            "fallback_provider": self.fallback_provider,
        }

    def route(self, text: str) -> IntentRoute:
        prompt = text.strip()
        if not prompt:
            return self._fallback(prompt, reason="empty_prompt")
        if not self.enabled:
            return self._fallback(prompt, reason="gate_disabled")
        if not self.parse_url:
            return self._fallback(prompt, reason="parse_url_missing")

        try:
            parsed = self.parse(prompt)
        except Exception as exc:
            return self._fallback(prompt, reason=f"rasa_error:{exc}")

        intent_data = parsed.get("intent")
        intent = str((intent_data or {}).get("name") or "").strip()
        confidence = float((intent_data or {}).get("confidence") or 0.0)
        if not intent:
            return self._fallback(prompt, reason="no_intent", raw=parsed)
        if confidence < self.min_confidence:
            return self._fallback(
                prompt,
                reason=f"low_confidence:{confidence:.3f}<{self.min_confidence:.3f}",
                raw=parsed,
            )

        action = self._ACTION_MAP.get(intent)
        if not action:
            return self._fallback(prompt, reason=f"intent_unmapped:{intent}", raw=parsed)

        slots = self._extract_slots(prompt, parsed, intent=intent)
        return IntentRoute(
            source="rasa",
            intent=intent,
            confidence=confidence,
            action=action,
            slots=slots,
            raw=parsed,
        )

    def parse(self, text: str) -> dict[str, Any]:
        payload = json.dumps({"text": text}, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            url=self.parse_url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"parse_request_failed:{exc}") from exc

        try:
            data = json.loads(raw)
        except Exception as exc:
            raise RuntimeError("invalid_json_from_rasa") from exc
        if not isinstance(data, dict):
            raise RuntimeError("unexpected_rasa_payload")
        return data

    def _fallback(
        self,
        prompt: str,
        *,
        reason: str,
        raw: dict[str, Any] | None = None,
    ) -> IntentRoute:
        slots = {"prompt": prompt}
        if self.fallback_provider:
            slots["provider"] = self.fallback_provider
        return IntentRoute(
            source="fallback",
            intent="fallback",
            confidence=0.0,
            action="dispatch",
            slots=slots,
            fallback_reason=reason,
            raw=raw or {},
        )

    def _extract_slots(
        self,
        prompt: str,
        parsed: dict[str, Any],
        *,
        intent: str,
    ) -> dict[str, Any]:
        slots: dict[str, Any] = {"prompt": prompt}
        entities = parsed.get("entities")
        if isinstance(entities, list):
            for item in entities:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("entity") or item.get("name") or "").strip().lower()
                value = item.get("value")
                if not key:
                    continue
                if value is None:
                    continue
                slots[key] = value

        text = prompt.lower()
        workers = slots.get("workers")
        if workers is None:
            match = re.search(r"\b([1-4])\s*(workers?|agentes?)\b", text)
            if match:
                slots["workers"] = int(match.group(1))

        if "worker_id" not in slots:
            match = re.search(r"\bworker[-_ ]?([1-4])\b", text)
            if match:
                slots["worker_id"] = f"worker-{match.group(1)}"

        if intent in {"run_validation", "rollback"}:
            if "target" not in slots:
                if "pentest" in text:
                    slots["target"] = "gate-pentest"
                elif "smoke" in text:
                    slots["target"] = "autopoiesis-smoke"
                elif "review" in text:
                    slots["target"] = "review-pack"
                else:
                    slots["target"] = "preflight"

        if intent == "tail_logs":
            if "follow" in text or "vivo" in text or "live" in text:
                slots["follow"] = True
            if "validation" in text:
                slots["kind"] = "validation"
            if "terminal" in text:
                slots["kind"] = "terminal"

        return slots
