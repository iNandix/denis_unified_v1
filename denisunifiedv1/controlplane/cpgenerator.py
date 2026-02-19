from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextPack:
    cp_id: str = ""
    mission: str = ""
    model: str = "llamaLocal"
    repo_id: str = ""
    repo_name: str = "unknown"
    branch: str = "main"
    human_validated: bool = False
    validated_by: str = ""
    notes: str = ""
    intent: str = ""
    files_to_read: List[str] = field(default_factory=list)
    risk_level: str = "MEDIUM"
    is_checkpoint: bool = False

    @classmethod
    def from_agent_result(cls, result: dict) -> "ContextPack":
        cp = cls(
            cp_id=result.get("intent", "unknown")[:20],
            mission=result.get("mission_completed", ""),
            model=result.get("model", "llamaLocal"),
        )
        cp.repo_id = result.get("repo_id", "")
        cp.repo_name = result.get("repo_name", "unknown")
        cp.branch = result.get("branch", "main")
        return cp

    def to_dict(self) -> dict:
        return {
            "cp_id": self.cp_id,
            "mission": self.mission,
            "model": self.model,
            "repo_id": self.repo_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "human_validated": self.human_validated,
            "validated_by": self.validated_by,
            "notes": self.notes,
            "intent": self.intent,
            "files_to_read": self.files_to_read,
            "risk_level": self.risk_level,
            "is_checkpoint": self.is_checkpoint,
        }


def generate_cp_from_result(result: dict) -> ContextPack:
    return ContextPack.from_agent_result(result)
