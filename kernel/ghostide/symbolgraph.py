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

    def upsert_chunk(
        self,
        path: str,
        chunk_index: int,
        content: str,
        symbols: list,
        template_slots: list,
        chunk_hash: str,
        session_id: str = None,
    ) -> bool:
        """Upsert a code chunk to Neo4j graph."""
        query = """
        MERGE (c:Chunk {hash: $chunkHash})
        SET c.path = $path,
            c.index = $chunkIndex,
            c.content = $content,
            c.symbols = $symbols,
            c.templateSlots = $templateSlots,
            c.lastSeen = datetime()
        
        // Link to file
        WITH c
        MERGE (f:File {path: $path})
        MERGE (f)-[:HAS_CHUNK]->(c)
        
        // Link symbols to chunk
        """

        # Add symbol links
        for sym in symbols:
            query += f"""
        WITH c
        MERGE (s:Symbol {{name: '{sym}'}})
        MERGE (s)-[:IN_CHUNK]->(c)
            """

        # Link to session if provided
        if session_id:
            query += """
        WITH c
        MERGE (s:Session {id: $sessionId})
        MERGE (s)-[:MODIFIED_IN]->(c)
            """

        return (
            self._run(
                query,
                {
                    "path": path,
                    "chunkIndex": chunk_index,
                    "content": content[:2000],  # Truncate for graph
                    "symbols": symbols,
                    "templateSlots": template_slots,
                    "chunkHash": chunk_hash,
                    "sessionId": session_id,
                },
            )
            is not None
        )

    def get_chunks_by_session(self, session_id: str, limit: int = 20) -> list:
        """Get chunks modified in a session."""
        query = """
        MATCH (s:Session {id: $sessionId})-[:MODIFIED_IN]->(c:Chunk)
        RETURN c.path as path, c.index as index, c.symbols as symbols,
               c.templateSlots as templates, c.hash as hash
        ORDER BY c.index
        LIMIT $limit
        """
        result = self._run(query, {"sessionId": session_id, "limit": limit})
        if not result:
            return []
        return [
            {
                "path": r.get("path"),
                "index": r.get("index"),
                "symbols": r.get("symbols", []),
                "templates": r.get("templates", []),
                "hash": r.get("hash"),
            }
            for r in result
        ]

    def get_relevant_chunks(
        self, intent: str, session_id: str = None, max_chunks: int = 10
    ) -> list:
        """Get chunks relevant to an intent (by symbol matching)."""
        # Extract keywords from intent
        keywords = intent.lower().replace("_", " ").split()

        query = """
        MATCH (c:Chunk)
        WHERE any(sym IN c.symbols WHERE sym CONTAINS $keyword)
        """
        if session_id:
            query += """
        MATCH (s:Session {id: $sessionId})-[:MODIFIED_IN]->(c)
            """

        query += """
        RETURN c.path as path, c.index as index, c.symbols as symbols,
               c.content as content, c.templateSlots as templates
        LIMIT $maxChunks
        """

        params = {"keyword": keywords[0] if keywords else "func", "maxChunks": max_chunks}
        if session_id:
            params["sessionId"] = session_id

        result = self._run(query, params)
        if not result:
            return []
        return [
            {
                "path": r.get("path"),
                "index": r.get("index"),
                "symbols": r.get("symbols", []),
                "content": r.get("content", ""),
                "templates": r.get("templates", []),
            }
            for r in result
        ]

    def link_chunk_to_session(self, chunk_hash: str, session_id: str) -> bool:
        """Link a chunk to a session."""
        query = """
        MATCH (c:Chunk {hash: $chunkHash})
        MERGE (s:Session {id: $sessionId})
        MERGE (s)-[:MODIFIED_IN]->(c)
        SET c.lastSeen = datetime()
        """
        return self._run(query, {"chunkHash": chunk_hash, "sessionId": session_id}) is not None

    def get_template_slots(self, path: str, symbols: list) -> list:
        """Get template slots for a file and its symbols."""
        query = """
        MATCH (f:File {path: $path})-[:HAS_CHUNK]->(c:Chunk)
        WHERE any(sym IN c.symbols WHERE sym IN $symbols)
        RETURN c.templateSlots as slots, c.symbols as symbols
        """
        result = self._run(query, {"path": path, "symbols": symbols})
        if not result:
            return []
        return [{"slots": r.get("slots", []), "symbols": r.get("symbols", [])} for r in result]

    def upsert_web_chunk(
        self,
        url: str,
        content: str,
        content_hash: str,
        title: str,
        tags: list,
        query: str,
        session_id: str,
    ) -> bool:
        """Upsert a web chunk from ProSearch to Neo4j."""
        query_cypher = """
        MERGE (wc:WebChunk {hash: $contentHash})
        SET wc.url = $url, wc.content = $content, wc.title = $title,
            wc.tags = $tags, wc.lastSeen = datetime()
        WITH wc
        MERGE (s:Session {id: $sessionId})
        MERGE (s)-[:FOUND_BY_SEARCH {query: $query}]->(wc)
        """
        return (
            self._run(
                query_cypher,
                {
                    "url": url,
                    "content": content[:2000],
                    "contentHash": content_hash,
                    "title": title,
                    "tags": tags,
                    "query": query,
                    "sessionId": session_id,
                },
            )
            is not None
        )

    def get_web_chunks(self, session_id: str, limit: int = 20) -> list:
        """Get web chunks found by search for a session."""
        query = """
        MATCH (s:Session {id: $sessionId})-[r:FOUND_BY_SEARCH]->(wc:WebChunk)
        RETURN wc.url as url, wc.title as title, wc.content as content,
               wc.tags as tags, r.query as search_query
        LIMIT $limit
        """
        result = self._run(query, {"sessionId": session_id, "limit": limit})
        if not result:
            return []
        return [
            {
                "url": r.get("url"),
                "title": r.get("title"),
                "content": r.get("content", ""),
                "tags": r.get("tags", []),
                "search_query": r.get("search_query"),
            }
            for r in result
        ]

    def get_available_engines(self, intent: str = None, healthy_only: bool = True) -> list:
        """Get available engines from Neo4j for routing."""
        query = "MATCH (e:Engine) WHERE e.name IS NOT NULL"

        if healthy_only:
            query += " AND e.healthy = true"

        if intent:
            query += """
            OPTIONAL MATCH (e)-[:AVAILABLE_FOR]->(i:Intent {name: $intent})
            WITH e, i
            ORDER BY e.priority ASC
            """
        else:
            query += " ORDER BY e.priority ASC"

        query += """
        RETURN e.name as engine_id, e.model as model, e.endpoint as endpoint,
               e.priority as priority, e.healthy as healthy,
               e.vram_used_mb as vram_used, e.queue_length as queue_length,
               e.latency_ms as latency_ms
        """

        params = {"intent": intent} if intent else {}
        result = self._run(query, params)

        if not result:
            return []

        return [
            {
                "engine_id": r.get("engine_id"),
                "model": r.get("model"),
                "endpoint": r.get("endpoint"),
                "priority": r.get("priority", 100),
                "healthy": r.get("healthy", False),
                "vram_used": r.get("vram_used", 0),
                "queue_length": r.get("queue_length", 0),
                "latency_ms": r.get("latency_ms", 0),
            }
            for r in result
        ]

    def link_engine_to_intent(self, engine_id: str, intent: str) -> bool:
        """Link an engine to an intent for routing."""
        query = """
        MATCH (e:Engine {name: $engine_id})
        MERGE (i:Intent {name: $intent})
        MERGE (e)-[:AVAILABLE_FOR]->(i)
        """
        return self._run(query, {"engine_id": engine_id, "intent": intent}) is not None

    def persona_prefers_intent(self, intent: str) -> list:
        """
        Query what engines Denis prefers for a given intent.
        Returns engines ordered by preference confidence.
        """
        query = """
        MATCH (d:Persona)-[p:PREFERS {intent: $intent}]->(e:Engine)
        WHERE e.healthy = true OR e.healthy IS NULL
        RETURN e.name AS engine_id, e.model AS model, e.endpoint AS endpoint,
               p.confidence AS confidence, p.times_used AS times_used
        ORDER BY p.confidence DESC, p.times_used DESC
        LIMIT 3
        """
        result = self._run(query, {"intent": intent})
        if not result:
            return []
        return [
            {
                "engine_id": r.get("engine_id"),
                "model": r.get("model"),
                "endpoint": r.get("endpoint"),
                "confidence": r.get("confidence", 0.5),
                "times_used": r.get("times_used", 0),
            }
            for r in result
        ]

    def persona_knowledge_base(self, session_id: str) -> list:
        """
        Get Denis knowledge base for a session (symbols touched).
        """
        query = """
        MATCH (d:Persona)-[:KNOWS]-(s:Symbol)
        OPTIONAL MATCH (s)-[:IN_FILE]-(f:File)
        WHERE (d)-[:MODIFIED_IN]-(sess:Session {id: $session_id})
        RETURN DISTINCT s.name AS name, s.type AS type, s.file AS path
        LIMIT 20
        """
        result = self._run(query, {"session_id": session_id})
        if not result:
            return []
        return [
            {"name": r.get("name"), "type": r.get("type"), "path": r.get("path")} for r in result
        ]

    def update_persona_mood(self, mood_score: float) -> bool:
        """
        Update Denis mood in graph.
        mood_score: -1.0 (sad) to 1.0 (confident)
        """
        mood = "sad" if mood_score < -0.3 else "confident" if mood_score > 0.3 else "neutral"

        query = """
        MATCH (d:Persona {name: 'Denis'})
        SET d.mood = $mood, 
            d.mood_score = $score, 
            d.last_mood_update = datetime()
        """
        return self._run(query, {"mood": mood, "score": mood_score}) is not None

    def record_persona_decision(
        self, session_id: str, intent: str, engine: str, outcome: str = None
    ) -> bool:
        """
        Record a decision Denis made for learning.
        """
        query = """
        MATCH (d:Persona {name: 'Denis'})
        SET d.total_decisions = COALESCE(d.total_decisions, 0) + 1
        """
        self._run(query)

        if outcome:
            exp_query = """
            MATCH (d:Persona {name: 'Denis'})
            MERGE (exp:Experience {session_id: $sid, intent: $intent, timestamp: datetime()})
            SET exp.outcome = $outcome, exp.engine = $engine
            CREATE (d)-[:LEARNED_FROM]->(exp)
            """
            return (
                self._run(
                    exp_query,
                    {"sid": session_id, "intent": intent, "outcome": outcome, "engine": engine},
                )
                is not None
            )
        return True
