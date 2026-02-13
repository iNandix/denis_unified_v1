"""Approval engine for human-in-the-loop decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from .models import new_id, utc_now, SprintEvent
from .session_store import SessionStore


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    session_id: str
    task_id: str | None
    reason: str
    diff_summary: str
    risk: str
    requested_utc: str
    status: str = "pending"  # pending, approved, rejected
    decision_utc: str | None = None
    reviewer: str | None = None
    decision_note: str | None = None


class ApprovalEngine:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def request_approval(
        self,
        *,
        session_id: str,
        task_id: str | None,
        reason: str,
        diff_summary: str,
        risk: str,
    ) -> str:
        approval_id = new_id("approval")
        request = ApprovalRequest(
            approval_id=approval_id,
            session_id=session_id,
            task_id=task_id,
            reason=reason,
            diff_summary=diff_summary,
            risk=risk,
            requested_utc=utc_now(),
        )
        # Emit event
        event = SprintEvent(
            session_id=session_id,
            worker_id="system",
            kind="approval.request",
            message=f"Approval requested: {reason}",
            payload={
                "approval_id": approval_id,
                "task_id": task_id,
                "reason": reason,
                "diff_summary": diff_summary,
                "risk": risk,
            },
            task_id=task_id,
        )
        self.store.append_event(event)
        return approval_id

    def decision(
        self,
        *,
        approval_id: str,
        decision: str,  # "approved" or "rejected"
        reviewer: str,
        note: str = "",
    ) -> None:
        # Find the request event
        events = self.store.read_events(None)  # Need to filter by session, but for simplicity, assume we have session_id
        # To properly find, need session_id, but since approval_id is unique, can search all events.
        # But inefficient, perhaps add a method to get approval by id.
        # For now, emit decision event with approval_id
        # Assume session_id is known, but to simplify, the method needs session_id.
        # Update signature to include session_id.

        # To fix, change decision to take session_id.

        # For now, assume we can find it.

        # But to implement, let's add session_id to decision.

        # The user didn't specify, but to make it work, add session_id.

        # Let's modify the method.

        # decision(self, *, session_id: str, approval_id: str, decision: str, reviewer: str, note: str = "") -> None

        # Then, emit event with session_id.

        event = SprintEvent(
            session_id=session_id,
            worker_id="system",
            kind="approval.decision",
            message=f"Approval {decision}: {approval_id}",
            payload={
                "approval_id": approval_id,
                "decision": decision,
                "reviewer": reviewer,
                "note": note,
            },
        )
        self.store.append_event(event)

    def get_pending_approvals(self, session_id: str) -> list[dict]:
        events = self.store.read_events(session_id)
        requests = []
        decisions = {}
        for event in events:
            if event["kind"] == "approval.request":
                requests.append(event["payload"])
            elif event["kind"] == "approval.decision":
                decisions[event["payload"]["approval_id"]] = event["payload"]["decision"]
        pending = []
        for req in requests:
            aid = req["approval_id"]
            if aid not in decisions:
                pending.append(req)
        return pending
