import os
import re
import subprocess
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from kernel.ghostide.symbolgraph import SymbolGraph


@dataclass
class ChunkTemplate:
    """Template extracted from a chunk."""

    name: str
    slots: List[str]
    chunk_hash: str


@dataclass
class CodeChunk:
    """AST-based code chunk with symbols and templates."""

    path: str
    chunk_index: int
    content: str
    symbols: List[str] = field(default_factory=list)
    template_slots: List[str] = field(default_factory=list)
    hash: str = ""


class ASTChunker:
    """AST-based chunker for code files."""

    def __init__(self, max_chunk_chars: int = 2400):
        self.max_chunk_chars = max_chunk_chars

    def chunk_file(self, file_path: str) -> List[CodeChunk]:
        """Chunk a Python file by AST boundaries (classes/functions)."""
        chunks = []

        if not os.path.exists(file_path):
            return []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return []

        # Extract symbols and their positions
        symbols = self._extract_symbols(content)

        # Split by semantic boundaries
        chunk_contents = self._semantic_split(content, symbols)

        for i, chunk_content in enumerate(chunk_contents):
            chunk_hash = hashlib.sha256(chunk_content.encode()).hexdigest()[:16]
            slots = self._template_from_chunk(chunk_content)

            chunks.append(
                CodeChunk(
                    path=file_path,
                    chunk_index=i,
                    content=chunk_content,
                    symbols=[s["name"] for s in symbols if self._symbol_in_chunk(s, chunk_content)],
                    template_slots=slots,
                    hash=chunk_hash,
                )
            )

        return chunks

    def _extract_symbols(self, content: str) -> List[Dict[str, Any]]:
        """Extract functions and classes with line numbers."""
        symbols = []

        # Find function definitions
        for match in re.finditer(r"^(\s*)def (\w+)\s*\((.*?)\).*?:", content, re.MULTILINE):
            symbols.append(
                {
                    "name": match.group(2),
                    "type": "function",
                    "params": match.group(3),
                    "line": content[: match.start()].count("\n") + 1,
                }
            )

        # Find class definitions
        for match in re.finditer(r"^class (\w+)(?:\((.*?)\))?:", content, re.MULTILINE):
            symbols.append(
                {
                    "name": match.group(1),
                    "type": "class",
                    "bases": match.group(2) or "",
                    "line": content[: match.start()].count("\n") + 1,
                }
            )

        return symbols

    def _semantic_split(self, content: str, symbols: List[Dict]) -> List[str]:
        """Split content by semantic boundaries (classes/functions)."""
        if not symbols:
            # Fallback to char-based splitting
            return self._char_split(content)

        # Sort symbols by line number
        sorted_symbols = sorted(symbols, key=lambda s: s.get("line", 0))

        chunks = []
        lines = content.split("\n")

        for i, sym in enumerate(sorted_symbols):
            start_line = sym.get("line", 1) - 1
            end_line = (
                sorted_symbols[i + 1].get("line", len(lines) + 1) - 1
                if i + 1 < len(sorted_symbols)
                else len(lines)
            )

            # Collect lines for this chunk
            chunk_lines = []
            current_line = start_line

            while current_line < end_line and current_line < len(lines):
                chunk_lines.append(lines[current_line])
                current_line += 1

            chunk_text = "\n".join(chunk_lines)

            # Split if too large
            if len(chunk_text) > self.max_chunk_chars:
                subchunks = self._char_split(chunk_text)
                chunks.extend(subchunks)
            else:
                chunks.append(chunk_text)

        return chunks if chunks else [content[: self.max_chunk_chars]]

    def _char_split(self, content: str) -> List[str]:
        """Fallback char-based splitting."""
        chunks = []
        for i in range(0, len(content), self.max_chunk_chars):
            chunks.append(content[i : i + self.max_chunk_chars])
        return chunks

    def _template_from_chunk(self, chunk: str) -> List[str]:
        """Extract template slots from chunk."""
        slots = []

        # Find parameter names in function definitions
        param_matches = re.findall(r"def \w+\s*\((.*?)\):", chunk)
        for params in param_matches:
            # Extract parameter names
            for param in params.split(","):
                param = param.strip()
                if param and param != "self" and param != "cls":
                    slots.append(param)

        # Find class attribute patterns
        attr_matches = re.findall(r"self\.(\w+)", chunk)
        slots.extend(attr_matches)

        return list(set(slots))

    def _symbol_in_chunk(self, symbol: Dict, chunk: str) -> bool:
        """Check if symbol is defined in chunk."""
        return f"def {symbol['name']}" in chunk or f"class {symbol['name']}" in chunk


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
    """
    Advanced Context Harvester - Bidirectional with ProSearch integration.

    Capabilities:
    - AST-based chunking with template extraction
    - Bidirectional: harvest → graph ← search (ProSearch)
    - Dynamic chunk creation via semantic search
    - Neo4j integration for session context
    """

    def __init__(self, session_id: str, watch_paths: List[str] = None):
        self.session_id = session_id
        self.watch_paths = watch_paths or []
        self.symbol_graph = SymbolGraph()
        self.symbol_extractor = SymbolExtractor()
        self.chunker = ASTChunker()
        self.do_not_touch_auto: List[str] = []
        self.session_context: Dict[str, Any] = {}
        self._chunks: Dict[str, List[CodeChunk]] = {}
        self._templates: Dict[str, List[ChunkTemplate]] = {}

    def harvest_file(self, file_path: str) -> bool:
        """Harvest file with AST chunking and template extraction."""
        if not os.path.exists(file_path):
            print(f"[ContextHarvester] File not found: {file_path}")
            return False

        # Basic symbol extraction
        symbols = self.symbol_extractor.extract(file_path)
        for sym in symbols:
            self.symbol_graph.upsert_symbol(sym, file_path)
            self.do_not_touch_auto.append(sym)

        # Advanced: AST-based chunking
        try:
            chunks = self.chunker.chunk_file(file_path)
            self._chunks[file_path] = chunks

            # Extract templates from chunks
            templates = []
            for chunk in chunks:
                if chunk.template_slots:
                    templates.append(
                        ChunkTemplate(
                            name=chunk.symbols[0]
                            if chunk.symbols
                            else f"chunk_{chunk.chunk_index}",
                            slots=chunk.template_slots,
                            chunk_hash=chunk.hash,
                        )
                    )
            self._templates[file_path] = templates

            # Upsert chunks to Neo4j
            self._upsert_chunks_to_graph(file_path, chunks)

        except Exception as e:
            print(f"[ContextHarvester] Chunking error: {e}")

        self.session_context[file_path] = symbols
        return True

    def _upsert_chunks_to_graph(self, file_path: str, chunks: List[CodeChunk]) -> None:
        """Upsert chunks to Neo4j graph."""
        try:
            for chunk in chunks:
                self.symbol_graph.upsert_chunk(
                    path=chunk.path,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    symbols=chunk.symbols,
                    template_slots=chunk.template_slots,
                    chunk_hash=chunk.hash,
                    session_id=self.session_id,
                )
        except Exception as e:
            print(f"[ContextHarvester] Graph upsert error: {e}")

    def search_and_create_chunks(
        self, query: str, intent: str = "implement_feature", max_chunks: int = 10
    ) -> List[CodeChunk]:
        """
        Bidirectional: Use ProSearch to find relevant code and create chunks.

        This enables dynamic context building based on semantic search.
        """
        chunks = []

        try:
            from denis_unified_v1.search.pro_search import search as pro_search

            hits, _ = pro_search(query=query, limit=max_chunks, kind="code")

            for hit in hits:
                provenance = hit.provenance
                file_path = provenance.get("file_path", "")

                if file_path and os.path.exists(file_path):
                    # Re-chunk the specific file with relevance focus
                    file_chunks = self.chunker.chunk_file(file_path)

                    # Find chunks that match the query context
                    for chunk in file_chunks:
                        if self._chunk_relevant_to_query(chunk, query):
                            chunk.session_context = {
                                "search_query": query,
                                "intent": intent,
                                "relevance_score": hit.score,
                                "provenance": provenance,
                            }
                            chunks.append(chunk)

        except Exception as e:
            print(f"[ContextHarvester] ProSearch error: {e}")

        return chunks[:max_chunks]

    def _chunk_relevant_to_query(self, chunk: CodeChunk, query: str) -> bool:
        """Check if chunk is relevant to search query."""
        query_lower = query.lower()
        chunk_text = chunk.content.lower()

        # Check symbols
        for symbol in chunk.symbols:
            if symbol.lower() in query_lower:
                return True

        # Check key terms
        query_terms = query_lower.split()
        matches = sum(1 for term in query_terms if term in chunk_text)
        return matches >= min(2, len(query_terms))

    def get_session_context(self) -> Dict[str, Any]:
        """Get full session context with chunks and templates."""
        return {
            "session_id": self.session_id,
            "do_not_touch_auto": list(set(self.do_not_touch_auto)),
            "files_harvested": list(self.session_context.keys()),
            "symbol_count": len(self.do_not_touch_auto),
            "modified_paths": list(self.session_context.keys()),
            "context_prefilled": self._build_context_prefilled(),
            "chunks": self._serialize_chunks(),
            "templates": {k: [t.__dict__ for t in v] for k, v in self._templates.items()},
        }

    def _build_context_prefilled(self) -> Dict[str, Any]:
        """Build context_prefilled dict for request completion."""
        context = {}

        for file_path, chunks in self._chunks.items():
            context[file_path] = {
                "chunks": [
                    {
                        "index": c.chunk_index,
                        "content": c.content[:500],  # Truncate for context
                        "symbols": c.symbols,
                        "hash": c.hash,
                    }
                    for c in chunks
                ],
                "templates": [
                    {"name": t.name, "slots": t.slots} for t in self._templates.get(file_path, [])
                ],
            }

        return context

    def _serialize_chunks(self) -> Dict[str, Any]:
        """Serialize chunks for JSON serialization."""
        return {
            file_path: [
                {
                    "index": c.chunk_index,
                    "symbols": c.symbols,
                    "template_slots": c.template_slots,
                    "hash": c.hash,
                    "content_length": len(c.content),
                }
                for c in chunks
            ]
            for file_path, chunks in self._chunks.items()
        }

    def complete_request(
        self, intent: str, user_query: str, max_context_chunks: int = 12
    ) -> Dict[str, Any]:
        """
        Complete a request with full context from graph + ProSearch.

        This is the main entry point for request completion.
        """
        # 1. Get enriched context from ProSearch
        search_chunks = self.search_and_create_chunks(
            query=user_query, intent=intent, max_chunks=max_context_chunks
        )

        # 2. Build context_prefilled
        context_prefilled = self._build_context_prefilled()

        # 3. Add search results
        context_prefilled["_search_results"] = [
            {
                "file_path": c.path,
                "chunk_index": c.chunk_index,
                "symbols": c.symbols,
                "session_context": getattr(c, "session_context", {}),
            }
            for c in search_chunks
        ]

        # 4. Detect implicit tasks (redundancy detection)
        implicit_tasks = self._detect_implicit_tasks(user_query, search_chunks)

        return {
            "intent": intent,
            "query": user_query,
            "session_id": self.session_id,
            "context_prefilled": context_prefilled,
            "do_not_touch_auto": list(set(self.do_not_touch_auto)),
            "implicit_tasks": implicit_tasks,
            "chunks_from_search": len(search_chunks),
            "total_chunks": sum(len(c) for c in self._chunks.values()),
        }

    def _detect_implicit_tasks(self, query: str, search_chunks: List[CodeChunk]) -> List[str]:
        """Detect implicit tasks from redundancy analysis."""
        implicit = []
        query_lower = query.lower()

        # Check for common patterns
        if "test" not in query_lower and any("def test_" in c.content for c in search_chunks):
            implicit.append("Verify existing tests pass before implementation")

        if "refactor" in query_lower or "migrate" in query_lower:
            implicit.append("Backup before refactoring")
            implicit.append("Run existing tests after changes")

        if "api" in query_lower or "endpoint" in query_lower:
            implicit.append("Document API contract")

        return implicit

    async def create_chunks_from_search(self, query: str, session_id: str = None) -> Dict[str, Any]:
        """
        Bidirectional: Use ProSearch to find relevant code from web/external and create chunks.

        This creates WebChunk nodes in Neo4j.
        """
        session_id = session_id or self.session_id
        web_chunks_created = 0

        try:
            from denis_unified_v1.search.pro_search import search as pro_search

            hits, _ = pro_search(query=query, limit=10, kind="code")

            for hit in hits:
                try:
                    # Create WebChunk in Neo4j
                    content = hit.snippet_redacted
                    url = hit.provenance.get("source", "unknown")
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

                    # Upsert to Neo4j
                    self._upsert_web_chunk(
                        url=url,
                        content=content,
                        content_hash=content_hash,
                        title=hit.title,
                        tags=hit.tags,
                        query=query,
                        session_id=session_id,
                    )
                    web_chunks_created += 1

                except Exception as e:
                    print(f"[ContextHarvester] Web chunk error: {e}")

        except Exception as e:
            print(f"[ContextHarvester] ProSearch error: {e}")

        return {"query": query, "web_chunks_created": web_chunks_created, "session_id": session_id}

    def _upsert_web_chunk(
        self,
        url: str,
        content: str,
        content_hash: str,
        title: str,
        tags: List[str],
        query: str,
        session_id: str,
    ) -> bool:
        """Upsert WebChunk to Neo4j."""
        try:
            self.symbol_graph.upsert_web_chunk(
                url=url,
                content=content[:2000],
                content_hash=content_hash,
                title=title,
                tags=tags,
                query=query,
                session_id=session_id,
            )
            return True
        except Exception as e:
            print(f"[ContextHarvester] Web chunk upsert error: {e}")
            return False

    def get_session_chunks(self, session_id: str = None) -> Dict[str, Any]:
        """Get all chunks for a session (code + web)."""
        session_id = session_id or self.session_id

        # Get from Neo4j
        code_chunks = self.symbol_graph.get_chunks_by_session(session_id)
        web_chunks = self.symbol_graph.get_web_chunks(session_id)

        return {
            "session_id": session_id,
            "code_chunks": code_chunks,
            "web_chunks": web_chunks,
            "total_code": len(code_chunks),
            "total_web": len(web_chunks),
        }

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

    def harvest_repo(self, workspace: str) -> int:
        count = 0
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ("__pycache__", "venv", ".venv", "node_modules")
            ]
            for f in files:
                if f.endswith(".py"):
                    full_path = os.path.join(root, f)
                    if self.harvest_file(full_path):
                        count += 1
        return count

    def start(self, blocking: bool = True) -> None:
        import threading

        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=not blocking)
        self._running = True
        self._watch_thread.start()

    def stop(self) -> None:
        self._running = False

    def _watch_loop(self) -> None:
        import time

        while self._running:
            time.sleep(30)

    def get_session_context(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "do_not_touch_auto": list(set(self.do_not_touch_auto)),
            "files_harvested": list(self.session_context.keys()),
            "symbol_count": len(self.do_not_touch_auto),
            "modified_paths": list(self.session_context.keys()),
            "context_prefilled": {},
        }

    def close(self):
        if self.symbol_graph:
            self.symbol_graph.close()
