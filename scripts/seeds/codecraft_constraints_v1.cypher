// =============================================================================
// CODECRAFT CONSTRAINTS & INDEXES
// =============================================================================

// Unique constraints
CREATE CONSTRAINT codecraft_chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;

CREATE CONSTRAINT codecraft_template_id IF NOT EXISTS
FOR (t:Template) REQUIRE t.template_id IS UNIQUE;

CREATE CONSTRAINT codecraft_policy_id IF NOT EXISTS
FOR (p:Policy) REQUIRE p.policy_id IS UNIQUE;

CREATE CONSTRAINT codecraft_snippet_id IF NOT EXISTS
FOR (sn:Snippet) REQUIRE sn.snippet_id IS UNIQUE;

CREATE CONSTRAINT codecraft_artifact_id IF NOT EXISTS
FOR (a:Artifact) REQUIRE a.artifact_id IS UNIQUE;

CREATE CONSTRAINT codecraft_source_id IF NOT EXISTS
FOR (src:Source) REQUIRE src.id IS UNIQUE;

CREATE CONSTRAINT codecraft_specialty_id IF NOT EXISTS
FOR (cs:CodeSpecialty) REQUIRE cs.id IS UNIQUE;

CREATE CONSTRAINT codecraft_toolchain_step_id IF NOT EXISTS
FOR (ts:ToolchainStep) REQUIRE ts.step_id IS UNIQUE;

// Indexes for performance
CREATE INDEX codecraft_chunk_kind IF NOT EXISTS
FOR (c:Chunk) ON (c.kind);

CREATE INDEX codecraft_chunk_lang IF NOT EXISTS
FOR (c:Chunk) ON (c.lang);

CREATE INDEX codecraft_chunk_tags IF NOT EXISTS
FOR (c:Chunk) ON (c.tags);

CREATE INDEX codecraft_chunk_quality IF NOT EXISTS
FOR (c:Chunk) ON (c.quality_grade);

CREATE INDEX codecraft_snippet_lang IF NOT EXISTS
FOR (sn:Snippet) ON (sn.lang);

CREATE INDEX codecraft_snippet_signature IF NOT EXISTS
FOR (sn:Snippet) ON (sn.signature);

CREATE INDEX codecraft_snippet_hash IF NOT EXISTS
FOR (sn:Snippet) ON (sn.content_hash);

CREATE INDEX codecraft_artifact_source IF NOT EXISTS
FOR (a:Artifact) ON (a.source_id);

CREATE INDEX codecraft_license IF NOT EXISTS
FOR (l:License) ON (l.spdx_id);

RETURN 'Codecraft constraints and indexes created';
