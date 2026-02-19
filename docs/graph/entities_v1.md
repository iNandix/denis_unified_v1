# Graph Entities v1 (Operational SSoT)

This is the minimal operational model materialized from `event_v1`.

## Nodes
### Component
- `id`
- `version?`
- `freshness_ts`
- `status` (`ok|degraded|unknown`)
- `error_rate_window?` (optional counters)
- `last_ok_ts`, `last_err_ts`

### Provider
- `id` (openai|anthropic|local|...)
- `kind` (chat|scraper|...)

### FeatureFlag
- `id`
- `value`
- `updated_ts`

### Run
- `id = sha256(conversation_id + turn_id)`
- `conversation_id`
- `turn_id` (trace_id in v1)
- `trace_id`
- `status` (`running|ok|degraded`)
- `latency_ms?`
- `picked_provider?`
- `fallbacks_count?`
- `ts`

### Step
- `id = sha256(run_id + name)`
- `run_id`
- `name` (`pro_search|scrape|rag_build|...`)
- `status` (`running|success|failed|stale`)
- `latency_ms?`
- `ts`
- `order`

### Artifact
- `id = hash_sha256`
- `kind` (`evidence_pack|context_pack|decision_summary|...`)
- `counts_json` (stringified dict; no large text)
- `ts`

### Source
- `id = host|repo`
- `kind` (`host|domain|repo`)
- `last_seen_ts`
- `error_rate_window?`

## Edges
- `(Run)-[:HAS_STEP {order}]->(Step)`
- `(Step)-[:PRODUCED]->(Artifact)`
- `(Artifact)-[:FROM_SOURCE]->(Source)`
- `(Run)-[:USED_PROVIDER {role:selected|fallback}]->(Provider)`
- `(Component)-[:GATED_BY]->(FeatureFlag)`
- `(Component)-[:DEPENDS_ON]->(Component)`

