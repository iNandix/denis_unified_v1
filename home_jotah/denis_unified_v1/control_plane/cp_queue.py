"""CP Queue — Persistent queue for ContextPacks."""

import json
import os
from pathlib import Path
from typing import List, Optional

from control_plane.models import ContextPack


class CPQueue:
    """Persistent queue for ContextPacks."""

    def __init__(self, path: str = "/tmp/denis_cp_queue.json"):
        self.path = path
        self._queue: List[ContextPack] = []
        self._load()

    def _load(self) -> None:
        """Load queue from disk."""
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                    self._queue = [ContextPack.from_dict(d) for d in data]
            except Exception:
                self._queue = []

    def _save(self) -> None:
        """Save queue to disk."""
        data = [cp.to_dict() for cp in self._queue]
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def push(self, cp: ContextPack) -> None:
        """Add ContextPack to queue."""
        if len(self._queue) >= 5:
            self._queue.pop(0)
        self._queue.append(cp)
        self._save()

    def pop(self) -> Optional[ContextPack]:
        """Remove and return first ContextPack."""
        if not self._queue:
            return None
        cp = self._queue.pop(0)
        self._save()
        return cp

    def peek(self) -> Optional[ContextPack]:
        """Return first ContextPack without removing."""
        if self._queue:
            return self._queue[0]
        return None

    def list_pending(self) -> List[ContextPack]:
        """Return copy of queue."""
        return list(self._queue)

    def mark_approved(self, cp_id: str, notes: str = "") -> bool:
        """Mark a ContextPack as approved."""
        for cp in self._queue:
            if cp.cp_id == cp_id:
                cp.human_validated = True
                cp.notes = notes
                self._save()
                return True
        return False

    def mark_rejected(self, cp_id: str, reason: str = "") -> bool:
        """Remove a ContextPack from queue."""
        for i, cp in enumerate(self._queue):
            if cp.cp_id == cp_id:
                self._queue.pop(i)
                self._save()
                return True
        return False

    def purge_expired(self) -> int:
        """Remove expired ContextPacks."""
        original = len(self._queue)
        self._queue = [cp for cp in self._queue if not cp.is_expired()]
        removed = original - len(self._queue)
        if removed > 0:
            self._save()
        return removed

    @staticmethod
    def cleanup_temp_files(max_age_hours: int = 24) -> int:
        """Clean up old temp CP files."""
        import glob
        import time

        temp_patterns = [
            "/tmp/denis_cp_*.json",
            "/tmp/denis_agent_result.json",
        ]

        removed = 0
        now = time.time()
        max_seconds = max_age_hours * 3600

        for pattern in temp_patterns:
            for filepath in glob.glob(pattern):
                try:
                    if os.path.isfile(filepath):
                        age = now - os.path.getmtime(filepath)
                        if age > max_seconds:
                            os.remove(filepath)
                            removed += 1
                except Exception:
                    pass

        return removed


def get_cp_queue() -> CPQueue:
    """Get singleton CPQueue instance."""
    if not hasattr(get_cp_queue, "_instance"):
        get_cp_queue._instance = CPQueue()
    return get_cp_queue._instance


__all__ = ["CPQueue", "get_cp_queue"]
