#!/usr/bin/env python3
"""
Ghost Manager for Context OS.

Manages background jobs: prefetch, shadow lint, auto-diff summarize via Celery.
"""

import os
from typing import Dict, Any, List
from celery import Celery

# Celery app
app = Celery('denis_ghost', broker=os.getenv("CELERY_BROKER", "redis://localhost:6379/0"))

class GhostManager:
    """Manages ghost workers."""

    def __init__(self):
        self.celery = app

    def launch_prefetch(self, focus_files: List[str], intent: str):
        """Launch prefetch job."""
        self.celery.send_task('ghost.prefetch', args=[focus_files, intent])

    def launch_shadow_lint(self, changed_files: List[str]):
        """Launch shadow lint."""
        self.celery.send_task('ghost.shadow_lint', args=[changed_files])

    def launch_diff_summarize(self, diff: str, workspace_id: str):
        """Launch diff summarize."""
        self.celery.send_task('ghost.diff_summarize', args=[diff, workspace_id])

# Tasks
@app.task
def prefetch(focus_files: List[str], intent: str):
    """Prefetch dependency slice."""
    from denis_unified_v1.services.context_manager import get_context_manager
    cm = get_context_manager()
    slice = cm._get_dependency_slice(focus_files)
    # Cache in Redis or something
    print(f"Prefetched: {slice}")

@app.task
def shadow_lint(changed_files: List[str]):
    """Run lint on changed files."""
    import subprocess
    for file in changed_files:
        if file.endswith('.py'):
            subprocess.run(['flake8', file], capture_output=True)
    print("Lint completed")

@app.task
def diff_summarize(diff: str, workspace_id: str):
    """Summarize diff for memory."""
    summary = f"Changes in {workspace_id}: {len(diff)} chars"
    # Store in Neo4j episodic
    from denis_unified_v1.services.human_memory_manager import get_human_memory_manager
    hmm = get_human_memory_manager()
    hmm._execute_write({"type": "episode", "payload": {"title": "Diff summary", "summary": summary}})
    print(f"Diff summarized: {summary}")

# Global
_ghost_manager: GhostManager = None

def get_ghost_manager() -> GhostManager:
    global _ghost_manager
    if _ghost_manager is None:
        _ghost_manager = GhostManager()
    return _ghost_manager
