import os
import subprocess
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from kernel.ghostide.symbolgraph import SymbolGraph


class SymbolExtractor:
    @staticmethod
    def extract(file_path: str) -> List[str]:
        symbols = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            import re

            functions = re.findall(r"def\s+(\w+)\s*\(", content)
            classes = re.findall(r"class\s+(\w+)", content)

            symbols.extend(functions)
            symbols.extend(classes)
        except Exception as e:
            print(f"[SymbolExtractor] Error extracting from {file_path}: {e}")

        return symbols


class ContextHarvester:
    def __init__(self, session_id: str, watch_paths: List[str] = None):
        self.session_id = session_id
        self.watch_paths = watch_paths or []
        self.symbol_graph = SymbolGraph()
        self.symbol_extractor = SymbolExtractor()
        self.do_not_touch_auto: List[str] = []
        self.session_context = {}

    def harvest_file(self, file_path: str) -> bool:
        if not os.path.exists(file_path):
            print(f"[ContextHarvester] File not found: {file_path}")
            return False

        symbols = self.symbol_extractor.extract(file_path)

        for sym in symbols:
            self.symbol_graph.upsert_symbol(sym, file_path)
            self.do_not_touch_auto.append(sym)

        self.session_context[file_path] = symbols
        return True

    def harvest_last_commits(self, repo_path: str, n: int = 5) -> Dict[str, Any]:
        result = {"repo_id": None, "commits": [], "symbols_indexed": 0}

        try:
            repo_id = self._get_repo_id(repo_path)
            result["repo_id"] = repo_id

            cmd = ["git", "log", "--name-only", "--pretty=format:%H|%s", f"-n{n}"]
            output = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)

            if output.returncode != 0:
                print(f"[ContextHarvester] Git error: {output.stderr}")
                return result

            commits_data = []
            lines = output.stdout.strip().split("\n")
            current_commit = None

            for line in lines:
                if "|" in line and len(line) > 40:
                    commit_hash, message = line.split("|", 1)
                    current_commit = {"hash": commit_hash, "message": message, "files": []}
                    commits_data.append(current_commit)
                elif line.strip() and current_commit is not None:
                    current_commit["files"].append(line.strip())

            remote_url = self._get_remote_url(repo_path)
            branch = self._get_current_branch(repo_path)

            self.symbol_graph.upsert_repo(repo_id, os.path.basename(repo_path), remote_url, branch)

            for commit in commits_data:
                self.symbol_graph.upsert_commit(
                    repo_id, commit["hash"], commit["message"], commit["files"]
                )

                all_symbols = []
                for file_path in commit["files"]:
                    full_path = os.path.join(repo_path, file_path)
                    if os.path.isfile(full_path):
                        symbols = self.symbol_extractor.extract(full_path)
                        all_symbols.extend(symbols)

                if all_symbols:
                    self.symbol_graph.link_commit_to_symbols(commit["hash"], all_symbols)
                    result["symbols_indexed"] += len(all_symbols)

            result["commits"] = commits_data

        except Exception as e:
            print(f"[ContextHarvester] harvest_last_commits error: {e}")

        return result

    def _get_repo_id(self, repo_path: str) -> str:
        remote_url = self._get_remote_url(repo_path)
        if remote_url:
            return hashlib.sha256(remote_url.encode()).hexdigest()[:12]
        return hashlib.sha256(repo_path.encode()).hexdigest()[:12]

    def _get_remote_url(self, repo_path: str) -> str:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return ""

    def _get_current_branch(self, repo_path: str) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return "main"

    def get_session_context(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "do_not_touch_auto": list(set(self.do_not_touch_auto)),
            "files_harvested": list(self.session_context.keys()),
            "symbol_count": len(self.do_not_touch_auto),
        }

    def close(self):
        if self.symbol_graph:
            self.symbol_graph.close()
