from __future__ import annotations


def test_rag_context_builder_no_hits_fail_open(monkeypatch):
    monkeypatch.setenv("VECTORSTORE_ENABLED", "0")
    monkeypatch.setenv("RAG_ENABLED", "1")
    monkeypatch.setenv("INDEXING_ENABLED", "0")

    from denis_unified_v1.vectorstore.qdrant_client import reset_vectorstore_for_tests
    from denis_unified_v1.rag.context_builder import build_rag_context_pack

    reset_vectorstore_for_tests()
    pack = build_rag_context_pack(user_text="nothing", trace_id="t", conversation_id="c")
    assert pack.query == "nothing"
    assert pack.chunks == []
    assert pack.citations == []


def test_rag_context_builder_with_hits(monkeypatch):
    monkeypatch.setenv("VECTORSTORE_ENABLED", "0")
    monkeypatch.setenv("INDEXING_ENABLED", "1")
    monkeypatch.setenv("RAG_ENABLED", "1")
    monkeypatch.setenv("QDRANT_COLLECTION_DEFAULT", "denis_chunks_v1")

    from denis_unified_v1.vectorstore.qdrant_client import reset_vectorstore_for_tests
    from denis_unified_v1.indexing.indexing_bus import get_indexing_bus, IndexPiece
    from denis_unified_v1.rag.context_builder import build_rag_context_pack

    reset_vectorstore_for_tests()
    bus = get_indexing_bus()
    bus.upsert_piece(
        IndexPiece(
            kind="runbook",
            title="RB1",
            content="how to restart service safely",
            tags=["ops"],
            source="runbook",
        )
    )

    pack = build_rag_context_pack(user_text="restart service", trace_id="t", conversation_id="c")
    assert pack.query
    assert len(pack.chunks) >= 1
    assert len(pack.citations) >= 1
    assert "chunk_id" in pack.chunks[0]

