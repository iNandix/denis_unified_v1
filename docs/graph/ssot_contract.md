# Graph SSoT Contract (GML v1)

## Principle
The Graph is the operational Source of Truth (SSoT).

- WS events (`event_v1`) are a **log/timeline**.
- Qdrant is **semantic memory** (redacted content + embeddings).
- Graph is **operational state**: what exists, what ran, what was produced, freshness/health, and minimal provenance pointers.

## What Goes Into Graph
- Entities: `Component`, `Provider`, `FeatureFlag`, `Run`, `Step`, `Artifact`, `Source`
- Relationships: run pipeline ordering, produced artifacts, minimal provenance, feature gating, component dependencies
- Operational properties only: timestamps, status, counters, hashes, ids

## What Must NOT Go Into Graph
- Long text: prompts, snippets, HTML pages, code blocks, tool outputs
- Raw chain-of-thought (CoT)
- Secrets: API keys, Bearer tokens, auth headers
- Event/UI payload fields such as `prompt`, `html`, `snippet`, `content`, `authorization`, `token`, `api_key`, `secret`, `cookie`, `session`

Guardrails:
- Graph write policy enforces `MAX_STR_LEN_GRAPH` (default 512) and drops denied keys.
- On truncation, only a hash + length metadata is kept (no full content).

## Idempotency
Materialization is idempotent:
- `mutation_id = sha256(event_id + mutation_kind + stable_key)`
- Reprocessing the same event does not duplicate nodes/edges.

## Fail-Open
If Graph is unavailable:
- Materializer records local error counters and returns.
- `/chat` continues and events/Qdrant continue (Graph materialization is non-critical).
