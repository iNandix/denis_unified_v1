#!/usr/bin/env python3
"""
Workspace Indexer for Context OS.

Scans repo, extracts symbols, imports, dependencies, tests.
Stores in Neo4j graph and Qdrant vectors.

MVP: Python-focused with tree-sitter/ast, ripgrep for imports.
"""

import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set, Any
from uuid import uuid4

import qdrant_client
from neo4j import GraphDatabase
from qdrant_client.http import models

# Connections
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

class WorkspaceIndexer:
    """Indexes workspace for Context OS."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.qdrant_client = qdrant_client.QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

        # Create Qdrant collections
        self.qdrant_client.recreate_collection(
            collection_name="symbols",
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),  # Assume embedding size
        )
        self.qdrant_client.recreate_collection(
            collection_name="chunks",
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
        )

    def index_workspace(self):
        """Full index of workspace."""
        symbols = self._extract_symbols()
        imports = self._extract_imports()
        dependencies = self._build_dependencies(symbols, imports)
        tests = self._map_tests()

        self._store_in_neo4j(symbols, dependencies, tests)
        self._store_in_qdrant(symbols)

    def _extract_symbols(self) -> Dict[str, Dict[str, Any]]:
        """Extract symbols using AST for Python."""
        symbols = {}
        for py_file in self.repo_path.rglob("*.py"):
            if "test" in str(py_file) or "venv" in str(py_file):
                continue
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        symbol_id = str(uuid4())
                        symbols[symbol_id] = {
                            "name": node.name,
                            "type": "function" if isinstance(node, ast.FunctionDef) else "class",
                            "file": str(py_file.relative_to(self.repo_path)),
                            "line": node.lineno,
                            "code": ast.get_source_segment(open(py_file).read(), node) or "",
                        }
            except Exception as e:
                print(f"Error parsing {py_file}: {e}")
        return symbols

    def _extract_imports(self) -> Dict[str, List[str]]:
        """Extract imports using ripgrep."""
        imports = {}
        # Simple regex for Python imports
        import_pattern = re.compile(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))')
        for py_file in self.repo_path.rglob("*.py"):
            if "test" in str(py_file) or "venv" in str(py_file):
                continue
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                matches = import_pattern.findall(content)
                imports[str(py_file.relative_to(self.repo_path))] = [m[0] or m[1] for m in matches]
            except Exception as e:
                print(f"Error reading {py_file}: {e}")
        return imports

    def _build_dependencies(self, symbols: Dict, imports: Dict) -> Dict[str, Set[str]]:
        """Build dependency graph."""
        dependencies = {}
        for symbol_id, sym in symbols.items():
            file_deps = set()
            if sym["file"] in imports:
                file_deps.update(imports[sym["file"]])
            # Add calls/references if needed (simplified)
            dependencies[symbol_id] = file_deps
        return dependencies

    def _map_tests(self) -> Dict[str, List[str]]:
        """Map symbols to tests."""
        test_map = {}
        for test_file in self.repo_path.rglob("test_*.py"):
            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    content = f.read()
                # Simple: find function names tested
                funcs = re.findall(r'def test_(\w+)', content)
                test_map[str(test_file.relative_to(self.repo_path))] = funcs
            except Exception as e:
                print(f"Error reading {test_file}: {e}")
        return test_map

    def _store_in_neo4j(self, symbols: Dict, dependencies: Dict, tests: Dict):
        """Store in Neo4j."""
        with self.neo4j_driver.session() as session:
            # Clear old
            session.run("MATCH (n:Symbol) DETACH DELETE n")

            # Add symbols and relations
            for symbol_id, sym in symbols.items():
                session.run("""
                CREATE (s:Symbol {symbol_id: $id, name: $name, type: $type, file: $file, line: $line})
                """, {"id": symbol_id, "name": sym["name"], "type": sym["type"], "file": sym["file"], "line": sym["line"]})

                for dep in dependencies.get(symbol_id, []):
                    session.run("""
                    MATCH (s:Symbol {symbol_id: $id})
                    MERGE (d:Dependency {name: $dep})
                    CREATE (s)-[:DEPENDS_ON]->(d)
                    """, {"id": symbol_id, "dep": dep})

            # Add tests
            for test_file, funcs in tests.items():
                session.run("""
                CREATE (t:Test {file: $file, functions: $funcs})
                """, {"file": test_file, "funcs": funcs})

    def _store_in_qdrant(self, symbols: Dict):
        """Store embeddings in Qdrant (dummy embeddings for MVP)."""
        # Assume embedding function (replace with real like sentence-transformers)
        def embed(text: str) -> List[float]:
            # Dummy: hash-based vector
            import hashlib
            h = hashlib.md5(text.encode()).digest()
            return [int(b) / 255.0 for b in h] * (384 // 16)  # Pad to 384

        points = []
        for symbol_id, sym in symbols.items():
            vector = embed(sym["code"])
            points.append(models.PointStruct(
                id=symbol_id,
                vector=vector,
                payload={"name": sym["name"], "file": sym["file"]},
            ))
        self.qdrant_client.upsert(collection_name="symbols", points=points)

if __name__ == "__main__":
    indexer = WorkspaceIndexer("/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
    indexer.index_workspace()
