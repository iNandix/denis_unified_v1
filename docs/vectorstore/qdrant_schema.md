# Qdrant Schema (MVP)

This repo uses a fail-open vector memory layer for semantic retrieval.

## Env
- `VECTORSTORE_ENABLED=1` enables Qdrant (otherwise in-memory fallback).
- `QDRANT_URL` (default `http://127.0.0.1:6333`)
- `QDRANT_API_KEY` (optional, treated as secret; never logged)
- `QDRANT_COLLECTION_DEFAULT` (default `denis_chunks_v1`)
- `QDRANT_VECTOR_SIZE` (default `384`)

## Collections
### `denis_chunks_v1`
Stores durable "pieces" as chunked, redacted snippets.

Payload fields (minimum):
- `id` (deterministic for dedupe)
- `kind`: `chunk|template|scrape|top2|runbook|fixpack|decision_summary|...`
- `title`
- `tags` (array)
- `source`: `repo|manual|scraper|agent|...`
- `created_at`, `updated_at` (ISO)
- `trace_id` (nullable)
- `conversation_id` (nullable)
- `provider` (nullable)
- `hash_sha256` (dedupe key)
- `language`, `file_path`, `section` (nullable)
- `parent_id`, `chunk_index`
- `safety`: `{redacted:true, pii_risk:"low|med|high"}`
- `text_redacted`: redacted chunk text (may be truncated when `pii_risk=high`)

## Dedupe
`hash_sha256` is computed over canonicalized redacted content. The point id is deterministic:
`<hash_sha256>:<chunk_index>`.

