# Pro Search (Vector Memory) Contract (MVP)

This module is the retrieval backend used by RAG.

Python API:
- `denis_unified_v1.search.pro_search.search(query, tags?, kind?, limit?, language?, source?)`

Return:
- `(hits, warning)`

`hits[]` item:
- `chunk_id`: string
- `title`: string
- `tags[]`: string
- `kind`: string
- `score`: float (higher is better)
- `snippet_redacted`: string
- `provenance`: `{source, hash_sha256, file_path, section, parent_id, chunk_index}`

Fail-open behavior:
- If Qdrant is unavailable, the in-memory fallback still returns results for content indexed in-process.
- `warning` may include `{code:"vectorstore_degraded", msg:"qdrant_failed_over"}`.

