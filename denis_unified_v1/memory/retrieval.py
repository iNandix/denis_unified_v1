"""Memory retrieval with semantic search and context injection."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from denis_unified_v1.feature_flags import load_feature_flags
from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()

# Optional: sentence-transformers for embeddings
try:
    from sentence_transformers import SentenceTransformer

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    SentenceTransformer = None


class MemoryRetrieval:
    """Advanced memory retrieval with semantic search."""

    def __init__(
        self,
        redis: RedisBackend,
        neo4j: Neo4jBackend,
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self.redis = redis
        self.neo4j = neo4j
        self.flags = load_feature_flags()

        # Initialize embedding model if available
        self.embedder = None
        if EMBEDDINGS_AVAILABLE:
            try:
                self.embedder = SentenceTransformer(embedding_model)
            except Exception:
                pass

    async def retrieve_context(
        self,
        *,
        text: str,
        user_id: str | None = None,
        session_id: str | None = None,
        intent: str | None = None,
        max_items: int = 8,
        max_chars: int = 1500,
    ) -> dict[str, Any]:
        """Retrieve relevant memory context for a query."""
        with tracer.start_as_current_span("memory.retrieve_context") as span:
            span.set_attribute("text_length", len(text))
            span.set_attribute("user_id", user_id or "none")
            span.set_attribute("max_items", max_items)

            if not self.flags.phase9_memory_read_enabled:
                return {"status": "disabled", "items": []}

            context_items = []

            # 1. Working memory (session context)
            if session_id:
                working = await self._get_working_memory(session_id)
                if working:
                    context_items.append({
                        "type": "working",
                        "source": "session_context",
                        "data": working,
                        "relevance": 1.0,
                    })

            # 2. Facts (user-specific)
            if user_id:
                facts = await self._get_user_facts(user_id, max_items=3)
                for fact in facts:
                    context_items.append({
                        "type": "fact",
                        "source": "semantic_memory",
                        "data": fact,
                        "relevance": fact.get("confidence", 0.5),
                    })

            # 3. Preferences (user-specific)
            if user_id:
                prefs = await self._get_user_preferences(user_id, max_items=3)
                for pref in prefs:
                    context_items.append({
                        "type": "preference",
                        "source": "semantic_memory",
                        "data": pref,
                        "relevance": pref.get("confidence", 0.5),
                    })

            # 4. Semantic search (if embeddings available)
            if self.embedder and user_id:
                semantic_items = await self._semantic_search(text, user_id, top_k=3)
                context_items.extend(semantic_items)

            # 5. Recent conversations (episodic)
            if user_id:
                recent_convs = await self._get_recent_conversations(user_id, max_items=2)
                for conv in recent_convs:
                    context_items.append({
                        "type": "episodic",
                        "source": "conversation_history",
                        "data": conv,
                        "relevance": 0.6,
                    })

            # Sort by relevance
            context_items.sort(key=lambda x: x["relevance"], reverse=True)

            # Limit by max_items and max_chars
            context_items = context_items[:max_items]
            context_items = self._truncate_to_chars(context_items, max_chars)

            span.set_attribute("items_retrieved", len(context_items))

            return {
                "status": "ok",
                "items": context_items,
                "total_chars": sum(len(json.dumps(item)) for item in context_items),
            }

    async def _get_working_memory(self, session_id: str) -> dict | None:
        """Get working memory for session."""
        raw = self.redis.get(f"memory:working:session:{session_id}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def _get_user_facts(self, user_id: str, max_items: int = 5) -> list[dict]:
        """Get facts for user, sorted by confidence."""
        all_facts = self.redis.hgetall_json("memory:semantic:facts")
        user_facts = [f for f in all_facts.values() if f.get("user_id") == user_id]

        # Sort by confidence * occurrences
        user_facts.sort(
            key=lambda x: x.get("confidence", 0) * x.get("occurrences", 1),
            reverse=True,
        )

        return user_facts[:max_items]

    async def _get_user_preferences(self, user_id: str, max_items: int = 5) -> list[dict]:
        """Get preferences for user, sorted by confidence."""
        all_prefs = self.redis.hgetall_json("memory:semantic:preferences")
        user_prefs = [p for p in all_prefs.values() if p.get("user_id") == user_id]

        # Sort by confidence * occurrences
        user_prefs.sort(
            key=lambda x: x.get("confidence", 0) * x.get("occurrences", 1),
            reverse=True,
        )

        return user_prefs[:max_items]

    async def _semantic_search(
        self, query: str, user_id: str, top_k: int = 3
    ) -> list[dict]:
        """Semantic search using embeddings."""
        if not self.embedder:
            return []

        # Get query embedding
        query_embedding = self.embedder.encode(query, convert_to_numpy=True)

        # Get all user conversations
        all_convs = self.redis.hgetall_json("memory:episodic:conversations")
        user_convs = [c for c in all_convs.values() if c.get("user_id") == user_id]

        if not user_convs:
            return []

        # Compute embeddings for conversations (cache these in production)
        conv_texts = []
        for conv in user_convs:
            messages = conv.get("messages", [])
            text = " ".join(m.get("content", "") for m in messages)
            conv_texts.append(text)

        if not conv_texts:
            return []

        conv_embeddings = self.embedder.encode(conv_texts, convert_to_numpy=True)

        # Compute cosine similarity
        similarities = np.dot(conv_embeddings, query_embedding) / (
            np.linalg.norm(conv_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        # Get top-k
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            if similarities[idx] > 0.3:  # Threshold
                results.append({
                    "type": "semantic_match",
                    "source": "embedding_search",
                    "data": user_convs[idx],
                    "relevance": float(similarities[idx]),
                })

        return results

    async def _get_recent_conversations(
        self, user_id: str, max_items: int = 5
    ) -> list[dict]:
        """Get recent conversations for user."""
        all_convs = self.redis.hgetall_json("memory:episodic:conversations")
        user_convs = [c for c in all_convs.values() if c.get("user_id") == user_id]

        # Sort by timestamp
        user_convs.sort(key=lambda x: x.get("timestamp_utc", ""), reverse=True)

        return user_convs[:max_items]

    def _truncate_to_chars(self, items: list[dict], max_chars: int) -> list[dict]:
        """Truncate items to fit within max_chars."""
        result = []
        total_chars = 0

        for item in items:
            item_json = json.dumps(item)
            item_chars = len(item_json)

            if total_chars + item_chars <= max_chars:
                result.append(item)
                total_chars += item_chars
            else:
                break

        return result

    def format_for_prompt(self, context: dict[str, Any]) -> str:
        """Format memory context for injection into prompt."""
        if context.get("status") != "ok" or not context.get("items"):
            return ""

        lines = ["# MEMORY CONTEXT"]

        for item in context["items"]:
            item_type = item["type"]
            data = item["data"]

            if item_type == "fact":
                lines.append(
                    f"- FACT: {data.get('type')} = {data.get('value')} (confidence: {data.get('confidence', 0):.2f})"
                )

            elif item_type == "preference":
                lines.append(
                    f"- PREFERENCE: {data.get('type')} {data.get('value')} (confidence: {data.get('confidence', 0):.2f})"
                )

            elif item_type == "working":
                ctx = data.get("context", {})
                lines.append(f"- SESSION CONTEXT: {json.dumps(ctx, ensure_ascii=False)}")

            elif item_type in ("episodic", "semantic_match"):
                messages = data.get("messages", [])
                if messages:
                    summary = f"{len(messages)} messages"
                    lines.append(f"- PAST CONVERSATION: {summary}")

        return "\n".join(lines)


async def inject_memory_into_messages(
    messages: list[dict],
    retrieval: MemoryRetrieval,
    user_id: str | None = None,
    session_id: str | None = None,
) -> list[dict]:
    """Inject memory context into messages as a system message."""
    if not messages:
        return messages

    # Get last user message for context
    last_user_msg = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )

    if not last_user_msg:
        return messages

    # Retrieve context
    context = await retrieval.retrieve_context(
        text=last_user_msg.get("content", ""),
        user_id=user_id,
        session_id=session_id,
        max_items=8,
        max_chars=1500,
    )

    # Format for prompt
    memory_text = retrieval.format_for_prompt(context)

    if not memory_text:
        return messages

    # Insert as system message before last user message
    memory_message = {
        "role": "system",
        "content": memory_text,
    }

    # Find position to insert (before last user message)
    insert_pos = len(messages) - 1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            insert_pos = i
            break

    new_messages = messages[:insert_pos] + [memory_message] + messages[insert_pos:]

    return new_messages
