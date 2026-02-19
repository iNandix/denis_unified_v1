"""Context Harvester — Orchestrates RepoWatcher → SymbolExtractor → Neo4j."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from kernel.ghost_ide.symbol_extractor import SymbolExtractor
from kernel.ghost_ide.symbol_graph import SymbolGraph
from kernel.ghost_ide.repo_watcher import RepoWatcher

logger = logging.getLogger(__name__)

SESSION_FILE = "/tmp/denis_session_id.txt"


def get_or_create_session_id(node_id: str = "nodo1") -> str:
    """Get existing session ID or create a new one."""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return f.strip()

    from hashlib import sha256

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    session_id = sha256(f"{date_str}:{node_id}".encode()).hexdigest()[:12]

    with open(SESSION_FILE, "w") as f:
        f.write(session_id)

    return session_id


@dataclass
class SessionContext:
    """Context from the current session for IntentRouter."""

    session_id: str
    modified_paths: List[str] = field(default_factory=list)
    modified_symbols: List[str] = field(default_factory=list)
    do_not_touch_auto: List[str] = field(default_factory=list)
    context_prefilled: dict = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


class ContextHarvester:
    """Orchestrator that connects RepoWatcher → SymbolExtractor → Neo4j."""

    def __init__(
        self,
        session_id: str = None,
        node_id: str = "nodo1",
        watch_paths: List[str] = None,
        auto_start: bool = False,
    ):
        self.session_id = session_id or get_or_create_session_id(node_id)
        self.node_id = node_id
        self.watch_paths = watch_paths or []

        self._extractor = SymbolExtractor()
        self._graph: Optional[SymbolGraph] = None
        self._watcher: Optional[RepoWatcher] = None
        self._running = False
        self._lock = threading.Lock()

    def _get_graph(self) -> Optional[SymbolGraph]:
        """Get or create SymbolGraph instance."""
        if self._graph is None:
            try:
                self._graph = SymbolGraph()
                if self._graph.verify_connectivity():
                    self._graph.ensure_session(self.session_id, self.node_id)
                else:
                    self._graph = None
            except Exception as e:
                logger.warning(f"Failed to connect to Neo4j: {e}")
                self._graph = None
        return self._graph

    def start(self, blocking: bool = False):
        """Start the harvester."""
        with self._lock:
            if self._running:
                return

            self._running = True

            if self.watch_paths:
                self._watcher = RepoWatcher(
                    workspace=self.watch_paths[0] if self.watch_paths else ".",
                    debounce_seconds=1.0,
                )
                self._watcher.start()

            if blocking:
                self._run_loop()
            else:
                thread = threading.Thread(target=self._run_loop, daemon=True)
                thread.start()

            logger.info(f"ContextHarvester started — session {self.session_id}")

    def stop(self):
        """Stop the harvester."""
        with self._lock:
            self._running = False
            if self._watcher:
                self._watcher.stop()
            if self._graph:
                self._graph.close()
                self._graph = None
            logger.info(f"ContextHarvester stopped — session {self.session_id}")

    def _run_loop(self):
        """Main loop (for blocking mode)."""
        while self._running:
            import time

            time.sleep(1)

    def harvest_file(self, path: str):
        """Process a single file: extract symbols → upsert to Neo4j → link to session."""
        graph = self._get_graph()
        if graph is None:
            logger.warning(f"Neo4j not available, skipping harvest for {path}")
            return

        try:
            symbols = self._extractor.extract_from_file(path)
            if not symbols:
                return

            graph.upsert_symbols(symbols, [])

            for symbol in symbols:
                graph.link_symbol_to_session(symbol.symbol.name, symbol.file_path, self.session_id)

            logger.debug(f"Harvested {len(symbols)} symbols from {path}")

        except Exception as e:
            logger.error(f"Error harvesting {path}: {e}")

    def harvest_repo(self, root_path: str):
        """Initial harvest of entire repository."""
        root = Path(root_path)
        if not root.exists():
            logger.warning(f"Path does not exist: {root_path}")
            return

        graph = self._get_graph()
        if graph is None:
            logger.warning("Neo4j not available, skipping repo harvest")
            return

        py_files = list(root.rglob("*.py"))
        ts_files = list(root.rglob("*.ts")) + list(root.rglob("*.tsx"))

        total = 0
        for file_path in py_files + ts_files:
            try:
                symbols = self._extractor.extract_from_file(str(file_path))
                if symbols:
                    graph.upsert_symbols(symbols, [])
                    for symbol in symbols:
                        graph.link_symbol_to_session(
                            symbol.symbol.name, symbol.file_path, self.session_id
                        )
                    total += len(symbols)
            except Exception as e:
                logger.debug(f"Skipping {file_path}: {e}")

        logger.info(f"Repo harvest complete — {total} symbols indexed")

    def get_session_context(self) -> SessionContext:
        """Get current session context for IntentRouter."""
        graph = self._get_graph()

        if graph is None:
            return SessionContext(session_id=self.session_id)

        try:
            modified_paths = graph.get_today_modified_paths(self.session_id)
            session_symbols = graph.get_session_symbols(self.session_id)

            modified_symbols = [s["name"] for s in session_symbols]

            context_prefilled = {}
            for path in modified_paths:
                symbols = graph.get_path_symbols(path)
                if symbols:
                    context_prefilled[path] = symbols

            return SessionContext(
                session_id=self.session_id,
                modified_paths=modified_paths,
                modified_symbols=modified_symbols,
                do_not_touch_auto=modified_paths,
                context_prefilled=context_prefilled,
                last_updated=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.warning(f"Error getting session context: {e}")
            return SessionContext(session_id=self.session_id)

    def on_file_changed(self, path: str):
        """Callback for RepoWatcher - process changed file."""
        self.harvest_file(path)

    def _extract_symbols_safe(self, filepath: str) -> list:
        """Extract symbols from file safely."""
        try:
            return self._extractor.extract_from_file(filepath) or []
        except Exception as e:
            logger.debug(f"Failed to extract symbols from {filepath}: {e}")
            return []

    def harvest_last_commits(self, repo_path: str, n: int = 10) -> int:
        """Harvest symbols from last N commits."""
        import subprocess

        total = 0
        try:
            log = (
                subprocess.check_output(
                    ["git", "log", "--name-only", "--pretty=format:%H|%s", f"-{n}"], cwd=repo_path
                )
                .decode()
                .strip()
                .split("\n")
            )
            current_hash, current_msg = None, None
            files = []
            for line in log:
                if "|" in line and len(line.split("|")[0]) == 40:
                    if current_hash and files:
                        symbols = []
                        for f in files:
                            s = self._extract_symbols_safe(os.path.join(repo_path, f))
                            symbols.extend(s)
                        graph = self._get_graph()
                        if graph:
                            from control_plane.repo_context import RepoContext

                            repo = RepoContext(repo_path)
                            graph.upsert_commit(repo.repo_id, current_hash, current_msg, files)
                            graph.link_commit_to_symbols(
                                current_hash, [sym.symbol.name for sym in symbols]
                            )
                        total += len(symbols)
                    current_hash, current_msg = line.split("|", 1)
                    files = []
                elif line.strip() and not line.startswith(" "):
                    files.append(line.strip())
        except Exception as e:
            logger.warning(f"harvest_last_commits failed: {e}")
        return total


_harvester: Optional[ContextHarvester] = None


def get_context_harvester() -> Optional[ContextHarvester]:
    """Get singleton ContextHarvester instance."""
    return _harvester


def start_harvester(
    session_id: str = None,
    node_id: str = "nodo1",
    watch_paths: List[str] = None,
) -> ContextHarvester:
    """Start the ContextHarvester and return instance."""
    global _harvester

    _harvester = ContextHarvester(
        session_id=session_id,
        node_id=node_id,
        watch_paths=watch_paths,
    )
    _harvester.start(blocking=False)

    return _harvester


__all__ = [
    "ContextHarvester",
    "SessionContext",
    "get_context_harvester",
    "start_harvester",
    "get_or_create_session_id",
]
