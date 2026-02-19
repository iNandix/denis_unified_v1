import hashlib
from typing import Optional, Any
from neo4j import GraphDatabase


class SymbolGraph:
    def __init__(self, uri="bolt://127.0.0.1:7687", user="neo4j", password="neo4j"):
        self.uri = uri
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
        except Exception as e:
            print(f"[SymbolGraph] Neo4j not available: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def _run(self, query: str, params: dict = None):
        if not self.driver:
            return None
        try:
            with self.driver.session() as session:
                result = session.run(query, params or {})
                return [record for record in result]
        except Exception as e:
            print(f"[SymbolGraph] Query error: {e}")
            return None

    def upsert_hygiene_pattern(
        self, name: str, intent: str, constraints: list, tasks: list
    ) -> bool:
        query = """
        MERGE (h:HygienePattern {name: $name})
        SET h.intent=$intent, h.constraints=$constraints,
            h.tasks=$tasks, h.lastSeen=datetime()
        ON CREATE SET h.frequency=1
        """
        return (
            self._run(
                query, {"name": name, "intent": intent, "constraints": constraints, "tasks": tasks}
            )
            is not None
        )

    def increment_pattern_frequency(self, name: str) -> int:
        query = """
        MATCH (h:HygienePattern {name:$name})
        SET h.frequency = coalesce(h.frequency,0)+1,
            h.lastSeen = datetime()
        RETURN h.frequency
        """
        result = self._run(query, {"name": name})
        if result and result[0]:
            return result[0].get("h.frequency", 1)
        return 0

    def get_auto_inject_patterns(self, intent: str, constraints: list, threshold: int = 3) -> list:
        query = """
        MATCH (h:HygienePattern)
        WHERE h.intent=$intent AND h.frequency >= $threshold
        RETURN h.name, h.tasks, h.frequency
        ORDER BY h.frequency DESC
        """
        result = self._run(query, {"intent": intent, "threshold": threshold})
        if not result:
            return []
        patterns = []
        for record in result:
            patterns.append(
                {
                    "name": record.get("h.name"),
                    "tasks": record.get("h.tasks", []),
                    "frequency": record.get("h.frequency"),
                }
            )
        return patterns

    def get_all_patterns(self) -> list:
        query = """
        MATCH (h:HygienePattern)
        RETURN h.name, h.intent, h.constraints, h.tasks, h.frequency, h.lastSeen
        """
        result = self._run(query)
        if not result:
            return []
        patterns = []
        for record in result:
            patterns.append(
                {
                    "name": record.get("h.name"),
                    "intent": record.get("h.intent"),
                    "constraints": record.get("h.constraints", []),
                    "tasks": record.get("h.tasks", []),
                    "frequency": record.get("h.frequency", 0),
                    "lastSeen": record.get("h.lastSeen"),
                }
            )
        return patterns

    def upsert_repo(self, repo_id: str, name: str, remote_url: str, branch: str) -> bool:
        query = """
        MERGE (r:Repo {id: $repoId})
        SET r.name=$name, r.remote=$remote,
            r.branch=$branch, r.lastSeen=datetime()
        """
        return (
            self._run(
                query, {"repoId": repo_id, "name": name, "remote": remote_url, "branch": branch}
            )
            is not None
        )

    def upsert_commit(self, repo_id: str, commit_hash: str, message: str, files: list) -> bool:
        query = """
        MERGE (c:Commit {hash: $hash})
        SET c.message=$message, c.timestamp=datetime()
        WITH c
        MERGE (r:Repo {id: $repoId})
        MERGE (r)-[:HAS_COMMIT]->(c)
        """
        return (
            self._run(
                query, {"repoId": repo_id, "hash": commit_hash, "message": message, "files": files}
            )
            is not None
        )

    def link_commit_to_symbols(self, commit_hash: str, symbol_names: list) -> bool:
        for sym in symbol_names:
            query = """
            MATCH (c:Commit {hash: $hash})
            MATCH (s:Symbol {name: $sym})
            MERGE (c)-[:TOUCHES]->(s)
            """
            self._run(query, {"hash": commit_hash, "sym": sym})
        return True

    def get_repo_recent_symbols(self, repo_id: str, days: int = 1) -> list:
        query = """
        MATCH (r:Repo {id: $repoId})-[:HAS_COMMIT]->(c:Commit)
        WHERE c.timestamp > datetime() - duration({days: $days})
        MATCH (c)-[:TOUCHES]->(s:Symbol)
        RETURN DISTINCT s.name, s.file, c.hash, c.message
        ORDER BY c.timestamp DESC
        """
        result = self._run(query, {"repoId": repo_id, "days": days})
        if not result:
            return []
        symbols = []
        for record in result:
            symbols.append(
                {
                    "name": record.get("s.name"),
                    "file": record.get("s.file"),
                    "commit": record.get("c.hash"),
                    "message": record.get("c.message"),
                }
            )
        return symbols

    def upsert_symbol(self, name: str, file_path: str, symbol_type: str = "function") -> bool:
        query = """
        MERGE (s:Symbol {name: $name})
        SET s.file=$filePath, s.type=$symbolType, s.lastSeen=datetime()
        """
        return (
            self._run(query, {"name": name, "filePath": file_path, "symbolType": symbol_type})
            is not None
        )
