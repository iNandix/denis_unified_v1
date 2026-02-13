"""
Ops Module - Config store versionado con propose/apply/rollback.

Provides:
- Versioned configuration store in Redis
- Propose/Apply/Rollback workflow
- Approval system for changes
- Configuration guardrails
- Audit trail for all changes
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum
import hashlib
import uuid

from denis_unified_v1.gates.audit import get_audit_trail, AuditEventType, AuditSeverity


class ConfigStatus(Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


class ApprovalLevel(Enum):
    NONE = "none"
    AUTO = "auto"  # Auto-approved for non-critical changes
    USER = "user"  # Requires user approval
    ADMIN = "admin"  # Requires admin approval


@dataclass
class ConfigVersion:
    """A configuration version."""

    version_id: str
    config_key: str
    config_value: Dict[str, Any]
    created_at: float
    created_by: str
    status: str
    change_summary: str
    parent_version: Optional[str] = None
    applied_at: Optional[float] = None
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None


@dataclass
class ConfigProposal:
    """A configuration change proposal."""

    proposal_id: str
    config_key: str
    new_value: Dict[str, Any]
    change_summary: str
    created_by: str
    created_at: float
    status: ConfigStatus
    required_approval_level: ApprovalLevel
    approvals: List[Dict[str, str]] = field(default_factory=list)
    rejected_by: Optional[str] = None
    rejected_at: Optional[float] = None
    rejection_reason: Optional[str] = None


@dataclass
class GuardrailRule:
    """Guardrail rule for configuration changes."""

    rule_id: str
    config_key: str
    rule_type: str  # range, enum, regex, custom
    constraint: Dict[str, Any]
    severity: str = "error"  # error, warning


class ConfigStore:
    """
    Versioned configuration store with Redis backend.
    Supports propose/apply/rollback workflow.
    """

    def __init__(self, redis_client: Any = None):
        self.redis = redis_client
        self._guardrails: Dict[str, List[GuardrailRule]] = {}
        self._pending_proposals: Dict[str, ConfigProposal] = {}

    def _get_redis(self) -> Any:
        if self.redis is None:
            try:
                import redis

                self.redis = redis.Redis.from_url(
                    "redis://localhost:6379/0", decode_responses=True
                )
            except Exception:
                return None
        return self.redis

    # === GUARDRAILS ===

    def add_guardrail(self, rule: GuardrailRule) -> None:
        """Add a guardrail rule."""
        if rule.config_key not in self._guardrails:
            self._guardrails[rule.config_key] = []
        self._guardrails[rule.config_key].append(rule)

    def validate_config(
        self,
        config_key: str,
        value: Any,
    ) -> tuple[bool, List[str]]:
        """Validate config against guardrails."""
        errors = []

        rules = self._guardrails.get(config_key, [])
        for rule in rules:
            if rule.rule_type == "range":
                min_val = rule.constraint.get("min")
                max_val = rule.constraint.get("max")
                if min_val is not None and value < min_val:
                    errors.append(f"Value {value} below minimum {min_val}")
                if max_val is not None and value > max_val:
                    errors.append(f"Value {value} above maximum {max_val}")

            elif rule.rule_type == "enum":
                allowed = rule.constraint.get("values", [])
                if value not in allowed:
                    errors.append(f"Value {value} not in allowed values: {allowed}")

            elif rule.rule_type == "regex":
                import re

                pattern = rule.constraint.get("pattern")
                if pattern and not re.match(pattern, str(value)):
                    errors.append(f"Value {value} doesn't match pattern {pattern}")

        return len(errors) == 0, errors

    # === CONFIG VERSIONING ===

    async def get_current_config(self, config_key: str) -> Optional[Dict[str, Any]]:
        """Get current active configuration."""
        redis = self._get_redis()
        if not redis:
            return None

        try:
            value = redis.get(f"config:{config_key}:current")
            if value:
                return json.loads(value)
        except Exception:
            pass

        return None

    async def set_config(
        self,
        config_key: str,
        value: Dict[str, Any],
        created_by: str = "system",
        change_summary: str = "",
    ) -> str:
        """Set configuration (direct apply, bypasses proposal)."""
        # Validate guardrails
        valid, errors = self.validate_config(config_key, value)
        if not valid:
            raise ValueError(f"Config validation failed: {errors}")

        version_id = str(uuid.uuid4())[:8]

        version = ConfigVersion(
            version_id=version_id,
            config_key=config_key,
            config_value=value,
            created_at=time.time(),
            created_by=created_by,
            status=ConfigStatus.APPLIED.value,
            change_summary=change_summary,
        )

        # Store in Redis
        redis = self._get_redis()
        if redis:
            # Save version
            redis.set(
                f"config:{config_key}:version:{version_id}",
                json.dumps(asdict(version)),
            )

            # Update current
            redis.set(
                f"config:{config_key}:current",
                json.dumps(value),
            )

            # Add to version list
            redis.lpush(f"config:{config_key}:versions", version_id)

        # Audit
        audit = get_audit_trail()
        await audit.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.INFO,
            user_id=created_by,
            class_key=config_key,
            details={"version_id": version_id, "change_summary": change_summary},
        )

        return version_id

    async def get_version_history(
        self,
        config_key: str,
        limit: int = 20,
    ) -> List[ConfigVersion]:
        """Get version history for a config key."""
        redis = self._get_redis()
        if not redis:
            return []

        try:
            version_ids = redis.lrange(f"config:{config_key}:versions", 0, limit - 1)

            versions = []
            for vid in version_ids:
                data = redis.get(f"config:{config_key}:version:{vid}")
                if data:
                    versions.append(ConfigVersion(**json.loads(data)))

            return versions
        except Exception:
            return []

    # === PROPOSAL WORKFLOW ===

    async def create_proposal(
        self,
        config_key: str,
        new_value: Dict[str, Any],
        change_summary: str,
        created_by: str,
        required_approval_level: ApprovalLevel = ApprovalLevel.USER,
    ) -> str:
        """Create a configuration change proposal."""
        # Validate guardrails
        valid, errors = self.validate_config(config_key, new_value)
        if not valid:
            raise ValueError(f"Config validation failed: {errors}")

        proposal_id = str(uuid.uuid4())[:8]

        proposal = ConfigProposal(
            proposal_id=proposal_id,
            config_key=config_key,
            new_value=new_value,
            change_summary=change_summary,
            created_by=created_by,
            created_at=time.time(),
            status=ConfigStatus.PENDING_APPROVAL.value,
            required_approval_level=required_approval_level,
        )

        # Store in Redis
        redis = self._get_redis()
        if redis:
            redis.set(
                f"config:proposal:{proposal_id}",
                json.dumps(asdict(proposal)),
            )
            redis.lpush("config:proposals:list", proposal_id)

        self._pending_proposals[proposal_id] = proposal

        # Audit
        audit = get_audit_trail()
        await audit.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.WARNING,
            user_id=created_by,
            class_key=config_key,
            details={
                "proposal_id": proposal_id,
                "change_summary": change_summary,
                "approval_level": required_approval_level.value,
            },
        )

        return proposal_id

    async def approve_proposal(
        self,
        proposal_id: str,
        approved_by: str,
    ) -> bool:
        """Approve a proposal."""
        proposal = await self._get_proposal(proposal_id)
        if not proposal:
            return False

        if proposal.status != ConfigStatus.PENDING_APPROVAL.value:
            return False

        # Auto-approve check
        if proposal.required_approval_level == ApprovalLevel.AUTO:
            proposal.status = ConfigStatus.APPROVED.value
        else:
            proposal.approvals.append(
                {
                    "by": approved_by,
                    "at": time.time(),
                }
            )

            # Check if enough approvals
            if len(proposal.approvals) >= 1:
                proposal.status = ConfigStatus.APPROVED.value

        if proposal.status == ConfigStatus.APPROVED.value:
            proposal.approved_by = approved_by
            proposal.approved_at = time.time()

        await self._save_proposal(proposal)
        return True

    async def reject_proposal(
        self,
        proposal_id: str,
        rejected_by: str,
        reason: str,
    ) -> bool:
        """Reject a proposal."""
        proposal = await self._get_proposal(proposal_id)
        if not proposal:
            return False

        proposal.status = ConfigStatus.REJECTED.value
        proposal.rejected_by = rejected_by
        proposal.rejected_at = time.time()
        proposal.rejection_reason = reason

        await self._save_proposal(proposal)

        # Audit
        audit = get_audit_trail()
        await audit.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.WARNING,
            user_id=rejected_by,
            class_key=proposal.config_key,
            details={
                "proposal_id": proposal_id,
                "rejection_reason": reason,
            },
        )

        return True

    async def apply_proposal(self, proposal_id: str) -> Optional[str]:
        """Apply an approved proposal."""
        proposal = await self._get_proposal(proposal_id)
        if not proposal or proposal.status != ConfigStatus.APPROVED.value:
            return None

        # Apply the config
        version_id = await self.set_config(
            config_key=proposal.config_key,
            value=proposal.new_value,
            created_by=proposal.created_by,
            change_summary=proposal.change_summary,
        )

        # Update proposal status
        proposal.status = ConfigStatus.APPLIED.value
        await self._save_proposal(proposal)

        return version_id

    async def rollback(
        self,
        config_key: str,
        target_version: str,
        rolled_back_by: str,
        reason: str,
    ) -> bool:
        """Rollback configuration to a previous version."""
        redis = self._get_redis()
        if not redis:
            return False

        # Get target version
        version_data = redis.get(f"config:{config_key}:version:{target_version}")
        if not version_data:
            return False

        version = ConfigVersion(**json.loads(version_data))

        # Apply the old version
        await self.set_config(
            config_key=config_key,
            value=version.config_value,
            created_by=rolled_back_by,
            change_summary=f"Rollback to {target_version}: {reason}",
        )

        # Audit
        audit = get_audit_trail()
        await audit.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.ERROR,
            user_id=rolled_back_by,
            class_key=config_key,
            details={
                "target_version": target_version,
                "reason": reason,
            },
        )

        return True

    async def _get_proposal(self, proposal_id: str) -> Optional[ConfigProposal]:
        """Get proposal by ID."""
        if proposal_id in self._pending_proposals:
            return self._pending_proposals[proposal_id]

        redis = self._get_redis()
        if not redis:
            return None

        data = redis.get(f"config:proposal:{proposal_id}")
        if data:
            proposal = ConfigProposal(**json.loads(data))
            self._pending_proposals[proposal_id] = proposal
            return proposal

        return None

    async def _save_proposal(self, proposal: ConfigProposal) -> None:
        """Save proposal to Redis."""
        self._pending_proposals[proposal.proposal_id] = proposal

        redis = self._get_redis()
        if redis:
            redis.set(
                f"config:proposal:{proposal.proposal_id}",
                json.dumps(asdict(proposal)),
            )

    async def list_proposals(
        self,
        status: Optional[ConfigStatus] = None,
    ) -> List[ConfigProposal]:
        """List all proposals."""
        redis = self._get_redis()
        if not redis:
            return []

        try:
            proposal_ids = redis.lrange("config:proposals:list", 0, -1)

            proposals = []
            for pid in proposal_ids:
                proposal = await self._get_proposal(pid)
                if proposal and (status is None or proposal.status == status.value):
                    proposals.append(proposal)

            return proposals
        except Exception:
            return []


# Singleton
_config_store: Optional[ConfigStore] = None


def get_config_store(redis_client: Any = None) -> ConfigStore:
    """Get singleton config store."""
    global _config_store
    if _config_store is None:
        _config_store = ConfigStore(redis_client)

        # Add default guardrails
        _config_store.add_guardrail(
            GuardrailRule(
                rule_id="rate_limit_rps",
                config_key="phase10_rate_limit_rps",
                rule_type="range",
                constraint={"min": 1, "max": 100},
            )
        )

        _config_store.add_guardrail(
            GuardrailRule(
                rule_id="budget_total_ms",
                config_key="phase10_budget_total_ms",
                rule_type="range",
                constraint={"min": 1000, "max": 30000},
            )
        )

    return _config_store
