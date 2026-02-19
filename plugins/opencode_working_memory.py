#!/usr/bin/env python3
"""
OpenCode Working Memory Plugin - LRU hot files + protected slots + LSP diagnostics.
Production-ready zero-config plugin.
"""

import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional
from threading import Lock
import hashlib
import time


class WorkingMemory:
    """LRU cache for hot files with protected slots for errors/decisions."""

    def __init__(self, max_files: int = 15):
        self.hot_files: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_files = max_files
        self._lock = Lock()
        self._errors: List[Dict[str, Any]] = []
        self._decisions: List[Dict[str, Any]] = []
        self._git_diffs: List[Dict[str, Any]] = []
        self._access_times: Dict[str, float] = {}

    def add_file(self, filepath: str, content: str = "", lsp_data: Optional[Dict] = None) -> None:
        """Add file to working memory (LRU eviction if needed)."""
        with self._lock:
            if filepath in self.hot_files:
                self.hot_files.move_to_end(filepath)
            else:
                if len(self.hot_files) >= self.max_files:
                    oldest = next(iter(self.hot_files))
                    del self.hot_files[oldest]
                self.hot_files[filepath] = {
                    "content": content,
                    "lsp": lsp_data or {},
                    "added_at": time.time(),
                    "hash": hashlib.md5(content.encode()).hexdigest()[:8] if content else "",
                }
            self._access_times[filepath] = time.time()

    def get_file(self, filepath: str) -> Optional[Dict]:
        """Get file from working memory."""
        with self._lock:
            if filepath in self.hot_files:
                self.hot_files.move_to_end(filepath)
                self._access_times[filepath] = time.time()
                return self.hot_files[filepath]
        return None

    def remove_file(self, filepath: str) -> bool:
        """Remove file from working memory."""
        with self._lock:
            if filepath in self.hot_files:
                del self.hot_files[filepath]
                self._access_times.pop(filepath, None)
                return True
        return False

    def add_error(self, error: Dict[str, Any]) -> None:
        """Add error to protected slot (max 10)."""
        with self._lock:
            self._errors.append({**error, "timestamp": time.time()})
            if len(self._errors) > 10:
                self._errors = self._errors[-10:]

    def add_decision(self, decision: Dict[str, Any]) -> None:
        """Add decision to protected slot (max 20)."""
        with self._lock:
            self._decisions.append({**decision, "timestamp": time.time()})
            if len(self._decisions) > 20:
                self._decisions = self._decisions[-20:]

    def add_git_diff(self, diff: Dict[str, Any]) -> None:
        """Add git diff to protected slot (last 3)."""
        with self._lock:
            self._git_diffs.append({**diff, "timestamp": time.time()})
            if len(self._git_diffs) > 3:
                self._git_diffs = self._git_diffs[-3:]

    def get_context(self) -> Dict[str, Any]:
        """Get full context for injection into prompts."""
        with self._lock:
            return {
                "hot_files": list(self.hot_files.keys()),
                "hot_files_count": len(self.hot_files),
                "errors": self._errors.copy(),
                "decisions": self._decisions.copy(),
                "git_diffs_last_3": self._git_diffs.copy(),
                "total_errors": len(self._errors),
                "total_decisions": len(self._decisions),
            }

    def clear(self) -> None:
        """Clear all working memory."""
        with self._lock:
            self.hot_files.clear()
            self._errors.clear()
            self._decisions.clear()
            self._git_diffs.clear()
            self._access_times.clear()


_working_memory_instance: Optional[WorkingMemory] = None
_instance_lock = Lock()


def get_working_memory(max_files: int = 15) -> WorkingMemory:
    """Get singleton working memory instance."""
    global _working_memory_instance
    if _working_memory_instance is None:
        with _instance_lock:
            if _working_memory_instance is None:
                _working_memory_instance = WorkingMemory(max_files)
    return _working_memory_instance


def inject_context() -> str:
    """Generate context JSON for prompt injection."""
    wm = get_working_memory()
    return json.dumps(wm.get_context(), indent=2)


def clear_working_memory() -> None:
    """Clear working memory."""
    wm = get_working_memory()
    wm.clear()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OpenCode Working Memory Plugin")
    parser.add_argument("--install", action="store_true", help="Install plugin to OpenCode config")
    parser.add_argument("--clear", action="store_true", help="Clear working memory")
    parser.add_argument("--show", action="store_true", help="Show current context")
    parser.add_argument("--add-file", type=str, help="Add file to working memory")
    parser.add_argument("--add-error", type=str, help="Add error to protected slot")
    parser.add_argument("--add-decision", type=str, help="Add decision to protected slot")
    parser.add_argument("--max-files", type=int, default=15, help="Max hot files (default 15)")

    args = parser.parse_args()

    if args.clear:
        clear_working_memory()
        print("Working memory cleared")
    elif args.show:
        print(inject_context())
    elif args.add_file:
        filepath = args.add_file
        content = ""
        if os.path.exists(filepath):
            try:
                content = Path(filepath).read_text(encoding="utf-8", errors="ignore")[:10000]
            except Exception as e:
                print(f"Error reading file: {e}")
        get_working_memory(args.max_files).add_file(filepath, content)
        print(f"Added {filepath} to working memory")
    elif args.add_error:
        error = json.loads(args.add_error)
        get_working_memory(args.max_files).add_error(error)
        print("Error added to protected slot")
    elif args.add_decision:
        decision = json.loads(args.add_decision)
        get_working_memory(args.max_files).add_decision(decision)
        print("Decision added to protected slot")
    elif args.install:
        config_path = Path.home() / ".config" / "opencode" / "opencode.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
            config.setdefault("plugins", []).append(
                {"name": "working_memory", "path": __file__, "enabled": True}
            )
            config_path.write_text(json.dumps(config, indent=2))
            print(f"Plugin installed to {config_path}")
        else:
            print(f"Config not found at {config_path}")
            print("Creating new config...")
            config = {"plugins": [{"name": "working_memory", "path": __file__, "enabled": True}]}
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, indent=2))
            print(f"Created config at {config_path}")
    else:
        print("Working Memory Plugin for OpenCode")
        print("Usage:")
        print("  --install         Install plugin to OpenCode")
        print("  --clear           Clear working memory")
        print("  --show            Show current context")
        print("  --add-file <path> Add file to working memory")
        print("  --add-error <json> Add error to protected slot")
        print("  --add-decision <json> Add decision to protected slot")
