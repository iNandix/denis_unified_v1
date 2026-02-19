#!/usr/bin/env python3
"""Denis Control Plane CLI."""

import argparse
import json
import os
import sys
from pathlib import Path

CP_QUEUE_FILE = "/tmp/denis_cp_queue.json"
CP_HISTORY_FILE = "/tmp/denis_cp_history.json"


def load_queue():
    """Load CP queue from disk."""
    if not os.path.exists(CP_QUEUE_FILE):
        return []
    try:
        with open(CP_QUEUE_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_queue(queue):
    """Save CP queue to disk."""
    with open(CP_QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def load_history():
    """Load CP history from disk."""
    if not os.path.exists(CP_HISTORY_FILE):
        return []
    try:
        with open(CP_HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    """Save CP history to disk."""
    with open(CP_HISTORY_FILE, "w") as f:
        json.dump(history[-50:], f, indent=2)


def cmd_status(args):
    """Show CP queue status."""
    queue = load_queue()
    history = load_history()

    print("=" * 50)
    print("Denis Control Plane - Status")
    print("=" * 50)

    print(f"\n📋 Cola de aprobación: {len(queue)} CP(s)")
    for i, cp in enumerate(queue, 1):
        status = "✅" if cp.get("human_validated") else "⏳"
        print(f"  {i}. [{status}] {cp.get('cp_id', 'N/A')} - {cp.get('intent', 'N/A')}")
        print(f"     Repo: {cp.get('repo_name', 'N/A')} · {cp.get('branch', 'N/A')}")
        print(f"     Mission: {cp.get('mission', 'N/A')[:60]}...")

    print(f"\n📜 Historial: {len(history)} acción(es) reciente(s)")
    for h in history[-5:]:
        icon = "✅" if h.get("action") == "approved" else "❌"
        print(
            f"  {icon} {h.get('cp_id', 'N/A')} - {h.get('action', 'N/A')} by {h.get('validated_by', 'system')}"
        )

    print("\n" + "=" * 50)


def cmd_approve(args):
    """Approve a CP by ID."""
    queue = load_queue()
    history = load_history()

    cp_id = args.cp_id
    found = None
    for cp in queue:
        if cp.get("cp_id") == cp_id or cp_id in cp.get("cp_id", ""):
            found = cp
            break

    if not found:
        print(f"❌ CP '{cp_id}' no encontrado")
        return 1

    found["human_validated"] = True
    found["notes"] = args.notes or "Approved via CLI"
    found["validated_by"] = "cli"

    queue = [c for c in queue if c.get("cp_id") != found["cp_id"]]
    save_queue(queue)

    history.append(
        {
            "cp_id": found["cp_id"],
            "action": "approved",
            "validated_by": "cli",
            "notes": found["notes"],
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
    )
    save_history(history)

    print(f"✅ CP {found['cp_id']} aprobado")
    return 0


def cmd_reject(args):
    """Reject a CP by ID."""
    queue = load_queue()
    history = load_history()

    cp_id = args.cp_id
    found = None
    for cp in queue:
        if cp.get("cp_id") == cp_id or cp_id in cp.get("cp_id", ""):
            found = cp
            break

    if not found:
        print(f"❌ CP '{cp_id}' no encontrado")
        return 1

    queue = [c for c in queue if c.get("cp_id") != found["cp_id"]]
    save_queue(queue)

    history.append(
        {
            "cp_id": found["cp_id"],
            "action": "rejected",
            "validated_by": "cli",
            "reason": args.reason or "Rejected via CLI",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
    )
    save_history(history)

    print(f"❌ CP {found['cp_id']} rechazado")
    return 0


def cmd_history(args):
    """Show CP approval history."""
    history = load_history()
    limit = args.limit or 10

    print(f"📜 Últimas {min(limit, len(history))} acción(es):")
    for h in history[-limit:]:
        icon = "✅" if h.get("action") == "approved" else "❌"
        print(f"  {icon} {h.get('cp_id', 'N/A')} - {h.get('action', 'N/A')}")
        print(f"     By: {h.get('validated_by', 'system')} | {h.get('timestamp', '')}")

    return 0


def cmd_health(args):
    """Show CP health status."""
    queue = load_queue()
    history = load_history()

    pending = len(queue)
    approved = sum(1 for h in history if h.get("action") == "approved")
    rejected = sum(1 for h in history if h.get("action") == "rejected")

    health = {
        "status": "ok" if pending < 5 else "warning",
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "total": len(history),
        "success_rate": round(approved / len(history) * 100, 1) if history else 100.0,
    }

    print(json.dumps(health, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(prog="denis_cp", description="Denis Control Plane CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    subparsers.add_parser("status", help="Show CP queue status")
    subparsers.add_parser("health", help="Show CP health status")

    p_approve = subparsers.add_parser("approve", help="Approve a CP")
    p_approve.add_argument("cp_id", help="CP ID to approve")
    p_approve.add_argument("--notes", help="Approval notes")

    p_reject = subparsers.add_parser("reject", help="Reject a CP")
    p_reject.add_argument("cp_id", help="CP ID to reject")
    p_reject.add_argument("--reason", help="Rejection reason")

    p_history = subparsers.add_parser("history", help="Show approval history")
    p_history.add_argument("--limit", type=int, help="Number of entries to show")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "status": cmd_status,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "history": cmd_history,
        "health": cmd_health,
    }

    return commands.get(args.command, lambda _: parser.print_help())(args)


if __name__ == "__main__":
    sys.exit(main())
