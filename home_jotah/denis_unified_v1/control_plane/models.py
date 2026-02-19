"""Denis Control Plane — Standalone bricks for CP-G."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ContextPack:
    """Central dataclass for all CP-G operations."""

    cp_id: str
    mission: str
    model: str = "groq"
    files_to_read: List[str] = field(default_factory=list)
    files_touched: List[str] = field(default_factory=list)
    do_not_touch: List[str] = field(default_factory=list)
    implicit_tasks: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    intent: str = ""
    confidence: int = 0
    success: bool = False
    risk_level: str = "MEDIUM"
    is_checkpoint: bool = False
    constraints: List[str] = field(default_factory=list)
    repo_id: str = ""
    repo_name: str = "unknown"
    branch: str = "unknown"
    notes: str = ""
    extra_context: Dict[str, Any] = field(default_factory=dict)
    human_validated: bool = False
    validated_by: str = ""
    requires_human_approval: bool = True
    source: str = "agent_completion"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=120)
    )

    def is_expired(self) -> bool:
        """Check if the context pack has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime serialization."""
        data = asdict(self)
        data["generated_at"] = self.generated_at.isoformat()
        data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextPack":
        """Create from dictionary with datetime deserialization."""
        if isinstance(data.get("generated_at"), str):
            data["generated_at"] = datetime.fromisoformat(data["generated_at"])
        if isinstance(data.get("expires_at"), str):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)

    def to_json(self, path: str) -> None:
        """Save to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "ContextPack":
        """Load from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


__all__ = ["ContextPack"]
