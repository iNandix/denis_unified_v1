"""Repo Context — Git repository information without Denis imports."""

import hashlib
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

SESSION_FILE = "/tmp/denis_session_id.txt"


def get_or_create_session_id(node_id: str = "nodo1") -> str:
    """Get session ID from /tmp or create new one."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as f:
                return f.read().strip()
        except Exception:
            pass

    repo_ctx = RepoContext()
    session_id = repo_ctx.get_session_id(node_id)

    try:
        with open(SESSION_FILE, "w") as f:
            f.write(session_id)
    except Exception:
        pass

    return session_id


def clear_session_id() -> None:
    """Clear session ID file."""
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception:
        pass


class RepoContext:
    """Git repository context information."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()
        self.git_root = self._find_git_root(self.cwd)
        self.repo_id = self._get_repo_id()
        self.repo_name = self._get_repo_name()
        self.branch = self._get_branch()

    def _find_git_root(self, cwd: str) -> str:
        """Find .git directory by walking up from cwd."""
        current = Path(cwd).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return str(parent)
        return cwd

    def _run_git(self, args: List[str]) -> str:
        """Run git command and return stdout."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.git_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_repo_id(self) -> str:
        """Get deterministic repo ID from remote or path."""
        remote = self._run_git(["remote", "get-url", "origin"])
        if not remote:
            remote = self.git_root
        return hashlib.sha256(remote.encode()).hexdigest()[:12]

    def _get_branch(self) -> str:
        """Get current branch name."""
        branch = self._run_git(["branch", "--show-current"])
        return branch or "unknown"

    def _get_repo_name(self) -> str:
        """Get repo name from remote URL or directory."""
        remote = self._run_git(["remote", "get-url", "origin"])
        if remote:
            name = remote.split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name
        return os.path.basename(self.git_root)

    def _get_last_commits(self, n: int = 5) -> List[Dict[str, str]]:
        """Get last N commits."""
        output = self._run_git(["log", f"-{n}", "--oneline"])
        if not output:
            return []
        commits = []
        for line in output.split("\n"):
            if line:
                parts = line.split(" ", 1)
                commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})
        return commits

    def get_session_id(self, node_id: str = "nodo1") -> str:
        """Generate deterministic session ID for today."""
        data = f"{date.today().isoformat()}+{node_id}+{self.repo_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        """Return dict representation."""
        return {
            "repo_id": self.repo_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "git_root": self.git_root,
            "session_id": get_or_create_session_id(),
        }


__all__ = ["RepoContext", "get_or_create_session_id", "clear_session_id", "SESSION_FILE"]
