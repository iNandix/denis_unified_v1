from __future__ import annotations


def test_pro_search_returns_topk_sorted_and_filters(monkeypatch):
    monkeypatch.setenv("VECTORSTORE_ENABLED", "0")
    monkeypatch.setenv("INDEXING_ENABLED", "1")
    monkeypatch.setenv("QDRANT_COLLECTION_DEFAULT", "denis_chunks_v1")

    from denis_unified_v1.vectorstore.qdrant_client import reset_vectorstore_for_tests
    from denis_unified_v1.indexing.indexing_bus import get_indexing_bus, IndexPiece
    from denis_unified_v1.search.pro_search import search

    reset_vectorstore_for_tests()
    bus = get_indexing_bus()

    # Index two pieces: one exact match, one different.
    bus.upsert_piece(
        IndexPiece(
            kind="chunk",
            title="Exact",
            content="alpha beta",
            tags=["x"],
            source="repo",
            language="python",
        )
    )
    bus.upsert_piece(
        IndexPiece(
            kind="chunk",
            title="Other",
            content="gamma delta",
            tags=["y"],
            source="repo",
            language="python",
        )
    )

    hits, warn = search(query="alpha beta", kind="chunk", limit=2, language="python")
    assert warn == {}
    assert len(hits) >= 1
    assert hits[0].title == "Exact"
    assert hits[0].score >= hits[-1].score

    # Tag filter: only x survives.
    hits2, _ = search(query="alpha beta", kind="chunk", tags=["x"], limit=5, language="python")
    assert hits2
    assert all("x" in h.tags for h in hits2)

