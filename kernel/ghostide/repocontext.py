import hashlib
import os
import subprocess
from dataclasses import dataclass


@dataclass
class RepoContext:
    repo_id: str
    repo_name: str
    branch: str
    remote_url: str

    @staticmethod
    def from_workspace(workspace: str) -> "RepoContext":
        repo_id = ""
        repo_name = os.path.basename(os.path.abspath(workspace))
        branch = "main"
        remote_url = ""

        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                remote_url = result.stdout.strip()
                repo_id = hashlib.sha256(remote_url.encode()).hexdigest()[:12]
        except:
            pass

        if not repo_id:
            repo_id = hashlib.sha256(workspace.encode()).hexdigest()[:12]

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
        except:
            pass

        return RepoContext(
            repo_id=repo_id, repo_name=repo_name, branch=branch, remote_url=remote_url
        )
