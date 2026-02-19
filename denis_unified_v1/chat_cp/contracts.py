"""Internal contracts for chat control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import uuid
from typing import Any, Literal

_ALLOWED_ROLES = {"system", "user", "assistant"}


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in _ALLOWED_ROLES:
            raise ValueError(f"invalid role: {self.role}")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("content must be a non-empty string")


@dataclass(frozen=True)
class ChatRequest:
    messages: list[ChatMessage]
    response_format: Literal["text", "json"] = "text"
    temperature: float = 0.2
    max_output_tokens: int = 512
    stream: bool = False
    trace_id: str | None = None
    metadata: dict[str, Any] | None = None
    task_profile_id: str = "control_plane_chat"

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("messages cannot be empty")
        if self.response_format not in {"text", "json"}:
            raise ValueError("response_format must be text|json")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be > 0")
        if not isinstance(self.temperature, (int, float)):
            raise ValueError("temperature must be numeric")
        if self.task_profile_id != "control_plane_chat":
            raise ValueError("task_profile_id must be control_plane_chat")

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "ChatRequest":
        raw_messages = payload.get("messages") or []
        messages = [
            ChatMessage(
                role=str(item.get("role", "user")),
                content=str(item.get("content", "")),
            )
            for item in raw_messages
        ]
        trace_id = payload.get("trace_id")
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            metadata = {"_raw": str(metadata)}
        return ChatRequest(
            messages=messages,
            response_format=str(payload.get("response_format", "text")),
            temperature=float(payload.get("temperature", 0.2)),
            max_output_tokens=int(payload.get("max_output_tokens", 512)),
            stream=bool(payload.get("stream", False)),
            trace_id=str(trace_id),
            metadata=metadata,
            task_profile_id=str(payload.get("task_profile_id", "control_plane_chat")),
        )


@dataclass(frozen=True)
class ChatError:
    code: str
    msg: str
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "msg": self.msg,
            "retryable": self.retryable,
        }


@dataclass
class ChatResponse:
    text: str | None
    json: dict[str, Any] | None
    provider: Literal["openai", "anthropic", "local", "none"]
    model: str | None
    usage: dict[str, Any] | None
    latency_ms: int
    success: bool = True
    error: ChatError | None = None
    trace_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "json": self.json,
            "provider": self.provider,
            "model": self.model,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error.as_dict() if self.error else None,
            "trace_id": self.trace_id,
        }

    @staticmethod
    def safe_json_from_text(text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
