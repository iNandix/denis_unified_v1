"""qcli integration for sprint_orchestrator.

Provides code intelligence (search, crossref, context) using qcli core.
Wraps qcli as a library to avoid subprocess overhead.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add qcli core to path - assume denis_protocol/src exists relative to project root
# Se inicializará lazy para evitar import failures si qcli no está instalado


class QCLIIntegration:
    """Singleton wrapper for qcli functionality."""

    _instance: QCLIIntegration | None = None
    _searcher: Any = None  # UnifiedSearcher type (lazy import)
    _indexer: Any = None  # CodeIndexer type
    _initialized: bool = False

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self._setup_python_path()

    def _setup_python_path(self) -> None:
        """Add denis_protocol/src to sys.path if not already there."""
        # Buscamos el path relativo desde project_root
        possible_src = self.project_root / "denis_protocol" / "src"
        if possible_src.exists() and str(possible_src) not in sys.path:
            sys.path.insert(0, str(possible_src))
        # También buscar en rutas absolutas conocidas
        alt_src = Path("/media/jotah/SSD_denis/denis_protocol/src")
        if alt_src.exists() and str(alt_src) not in sys.path:
            sys.path.insert(0, str(alt_src))

    def _lazy_import(self) -> None:
        """Import qcli modules on first use."""
        if self._initialized:
            return
        try:
            from denis_protocol.qcli.core.searcher import UnifiedSearcher
            from denis_protocol.qcli.core.indexer import CodeIndexer
            from denis_protocol.qcli.core.project import ProjectContext

            self._searcher = UnifiedSearcher
            self._indexer = CodeIndexer
            self._ProjectContext = ProjectContext
            self._initialized = True
        except ImportError as e:
            raise RuntimeError(f"qcli core not available: {e}") from e

    def get_searcher(self, session_id: str | None = None) -> Any:
        """Get or create a UnifiedSearcher instance.

        If session_id provided, might return cached searcher for that session.
        For now, creates new instance per call.
        """
        self._lazy_import()
        # TODO: Implement session-based caching
        return self._searcher(project_root=self.project_root)

    def get_indexer(self) -> Any:
        """Get a CodeIndexer instance."""
        self._lazy_import()
        return self._indexer()

    def search(
        self, query: str, limit: int = 20, session_id: str | None = None
    ) -> dict[str, Any]:
        """Perform adaptive search."""
        searcher = self.get_searcher(session_id)
        return searcher.search(query, limit=limit)

    def crossref(
        self, symbol: str, file: str | None = None, session_id: str | None = None
    ) -> dict[str, Any]:
        """Get cross-references for a symbol."""
        searcher = self.get_searcher(session_id)
        return searcher.get_cross_references(symbol, file)

    def context(self) -> dict[str, Any]:
        """Get project context."""
        self._lazy_import()
        ctx = self._ProjectContext(self.project_root)
        return ctx.to_dict()

    def index_project(self, paths: list[Path] | None = None) -> dict[str, Any]:
        """Index files in the project."""
        indexer = self.get_indexer()
        if paths:
            results = []
            for p in paths:
                if p.exists():
                    try:
                        syms = indexer.index_file(p)
                        results.append({"file": str(p), "symbols": len(syms)})
                    except Exception as e:
                        results.append({"file": str(p), "error": str(e)})
            return {"indexed": results, "total": len(results)}
        else:
            # Index entire project root
            root = self.project_root
            count = 0
            for suffix in indexer.parsers.keys():
                for f in root.rglob(f"*{suffix}"):
                    try:
                        indexer.index_file(f)
                        count += 1
                    except Exception:
                        pass
            return {"root": str(root), "files_indexed": count}

    def get_contracts_info(self) -> dict[str, Any]:
        """Get information about Pydantic contracts in the project.

        Scans contracts/ directory and returns summary.
        """
        contracts_dir = self.project_root / "contracts"
        if not contracts_dir.exists():
            return {"contracts_dir_exists": False}
        models = []
        for py_file in contracts_dir.rglob("*.py"):
            # Simple extraction - could be improved with AST
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            # Look for classes inheriting from BaseModel
            import re

            for match in re.finditer(r"class\s+(\w+).*?BaseModel", content):
                models.append(
                    {
                        "file": str(py_file.relative_to(self.project_root)),
                        "model": match.group(1),
                    }
                )
        return {
            "contracts_dir": str(contracts_dir),
            "models": models,
            "count": len(models),
        }


# Singleton accessor
def get_qcli(project_root: Path | None = None) -> QCLIIntegration:
    if QCLIIntegration._instance is None:
        QCLIIntegration._instance = QCLIIntegration(project_root)
    return QCLIIntegration._instance
