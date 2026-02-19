"""Repo Watcher — Monitor filesystem changes and trigger symbol extraction."""

import logging
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from denis_unified_v1.kernel.ghost_ide.symbol_extractor import SymbolExtractor
from denis_unified_v1.kernel.ghost_ide.symbol_graph import SymbolGraph

logger = logging.getLogger(__name__)


class SymbolUpdateEvent:
    """Event emitted when symbols are updated."""

    def __init__(self, file_path: str, symbols_count: int, relations_count: int = 0):
        self.file_path = file_path
        self.symbols_count = symbols_count
        self.relations_count = relations_count
        self.timestamp = time.time()


class RepoWatcher(FileSystemEventHandler):
    """Watch repository for code changes and extract symbols."""

    def __init__(
        self, workspace: str, debounce_seconds: float = 1.0, languages: list = None
    ):
        super().__init__()
        self.workspace = Path(workspace)
        self.debounce_seconds = debounce_seconds
        self.languages = languages or [".py", ".ts", ".tsx", ".js", ".jsx"]

        self._extractor = SymbolExtractor(
            languages=languages or ["python", "typescript"]
        )
        self._graph: Optional[SymbolGraph] = None
        self._observer: Optional[Observer] = None
        self._last_events: dict = {}

    def start(self):
        """Start watching the workspace."""
        self._graph = SymbolGraph()
        if not self._graph.verify_connectivity():
            logger.warning("Neo4j not available - symbols won't be persisted")

        self._observer = Observer()
        self._observer.schedule(self, str(self.workspace), recursive=True)
        self._observer.start()
        logger.info(f"Watching {self.workspace} for changes")

    def stop(self):
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
        if self._graph:
            self._graph.close()
        logger.info("Repo watcher stopped")

    def _should_process(self, path: str) -> bool:
        """Check if file should be processed."""
        p = Path(path)
        return p.suffix.lower() in self.languages and p.is_file()

    def _debounce(self, path: str) -> bool:
        """Check if event should be debounced."""
        now = time.time()
        last_time = self._last_events.get(path, 0)

        if now - last_time < self.debounce_seconds:
            return False

        self._last_events[path] = now
        return True

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if event.is_directory:
            return

        if not self._should_process(event.src_path):
            return

        if not self._debounce(event.src_path):
            return

        self._process_file(event.src_path)

    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if event.is_directory:
            return

        if not self._should_process(event.src_path):
            return

        time.sleep(0.5)
        self._process_file(event.src_path)

    def _process_file(self, file_path: str):
        """Extract and persist symbols from file."""
        try:
            symbols = self._extractor.extract_from_file(file_path)
            if not symbols:
                return

            relations = self._extractor.extract_relations(symbols)

            logger.info(f"Extracted {len(symbols)} symbols from {file_path}")

            if self._graph and self._graph.verify_connectivity():
                count = self._graph.upsert_symbols(symbols, relations)
                logger.info(f"Upserted {count} symbols to Neo4j")

            event = SymbolUpdateEvent(
                file_path=file_path,
                symbols_count=len(symbols),
                relations_count=len(relations),
            )

            self._emit_event(event)

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    def _emit_event(self, event: SymbolUpdateEvent):
        """Emit symbol update event."""
        logger.debug(f"Symbols updated: {event.symbols_count} from {event.file_path}")


def start_repo_watcher(workspace: str, debounce: float = 1.0) -> RepoWatcher:
    """Start repo watcher and return handler."""
    watcher = RepoWatcher(workspace=workspace, debounce_seconds=debounce)
    watcher.start()
    return watcher


__all__ = ["RepoWatcher", "SymbolUpdateEvent", "start_repo_watcher"]
