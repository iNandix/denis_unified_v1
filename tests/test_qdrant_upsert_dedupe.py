from __future__ import annotations


def test_qdrant_upsert_dedupe_same_content_one_point(tmp_path, monkeypatch):
    # Use mock/in-memory vectorstore (no qdrant dependency).
    monkeypatch.setenv("VECTORSTORE_ENABLED", "0")
    monkeypatch.setenv("INDEXING_ENABLED", "1")
    monkeypatch.setenv("QDRANT_COLLECTION_DEFAULT", "denis_chunks_v1")

    from denis_unified_v1.vectorstore.qdrant_client import get_vectorstore, reset_vectorstore_for_tests
    from denis_unified_v1.indexing.indexing_bus import get_indexing_bus, IndexPiece

    reset_vectorstore_for_tests()
    store = get_vectorstore()
    bus = get_indexing_bus()

    piece = IndexPiece(
        kind="runbook",
        title="T1",
        content="hello world",
        tags=["a"],
        source="manual",
        trace_id="t1",
        conversation_id="c1",
    )
    r1 = bus.upsert_piece(piece)
    r2 = bus.upsert_piece(piece)  # same content => dedupe id
    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r1["hash_sha256"] == r2["hash_sha256"]

    # Only one point exists in mock store for the single chunk.
    col = store.collection_default
    assert col in store._mock  # type: ignore[attr-defined]
    assert len(store._mock[col]) == 1  # type: ignore[attr-defined]

