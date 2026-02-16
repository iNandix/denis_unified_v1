# PRO_SEARCH - Research OS

PRO_SEARCH is DENIS's graph-centric web research framework. It provides multi-depth, multi-mode web research with verification, synthesis, and knowledge graph storage.

## Quick Start

```python
from denis_unified_v1.actions.pro_search_executor import run_pro_search

# User-facing natural research
result = await run_pro_search(
    query="What are the latest developments in quantum computing?",
    mode="user_pure",
    depth="standard"
)
print(result.answer)
print(result.sources)

# Agent-friendly with context
result = await run_pro_search(
    query="analyze:quantum_computing market trends 2024",
    mode="hybrid",
    depth="deep"
)

# Machine-readable JSON for automation
result = await run_pro_search(
    query="quantum computing market",
    mode="machine_only",
    depth="quick"
)
print(result.answer)  # JSON output
```

## Modes

| Mode | Description | Output | Use Case |
|------|-------------|--------|----------|
| `user_pure` | Natural language for end users | Streamed text + citations | Direct user queries |
| `hybrid` | Natural + structured for denis-agent | Text + citations + internal notes | Agentic workflows |
| `machine_only` | Structured JSON for automation | JSON | Learning, automation |

## Depths

| Depth | Time Limit | Max Sources | Cross-Verification | Use Case |
|-------|------------|-------------|---------------------|----------|
| `quick` | 30s | 5 | 1 | Fast facts |
| `standard` | 3min | 15 | 2 | General research |
| `deep` | 15min | 50 | 3 | Comprehensive analysis |
| `continuous` | ∞ | ∞ | 2 | Ongoing monitoring |

## Categories

- `general` - Web search (Google, Bing, DuckDuckGo)
- `academic` - Scholarly (arXiv, Scholar, PubMed)
- `technical` - Dev resources (StackOverflow, GitHub)
- `news` - Current events (NewsAPI, Google News)
- `video` - Video platforms (YouTube, Vimeo)
- `reddit` - Social discussions

## Policies

| Policy | Description | Enforcement |
|--------|-------------|-------------|
| `deep_mode_policy` | Deep mode requires ≥3 cross-verifications | Blocks execution |
| `cost_control` | Limits cost units per request | Prefers cheap engines |
| `source_diversity` | Requires ≥3 unique domains for academic | Flags violations |
| `bias_detection` | Flags bias, requests counter-sources | Enabled by default |

## Toolchain

```
ps_01_classify    → intent_classifier     → LLM
ps_02_expand     → query_expander        → LLM
ps_03_search     → searxng_search + web_fetch → Search + Scraper
ps_04_verify     → reliability_scorer + fact_verifier → Verifier
ps_05_synthesize → llm_synthesizer       → LLM (streaming)
ps_06_store      → knowledge_graph_writer → Graph (conditional)
```

## Graph Schema

```cypher
(:Skill {skill_id: 'pro_search'})
  -[:HAS_MODE]->(:SearchMode {mode_id: 'user_pure|hybrid|machine_only'})
  -[:HAS_DEPTH]->(:SearchDepth {depth_id: 'quick|standard|deep|continuous'})
  -[:HAS_CATEGORY]->(:SearchCategory {category_id: '...'})
  -[:HAS_POLICY]->(:Policy)
  -[:HAS_STEP]->(:ToolchainStep)-[:USES_TOOL]->(:Tool)
  -[:PREFERS_ENGINE]->(:Engine)
  -[:WRITES_TO]->(:MemoryLayer)
  -[:USES_COLLECTION]->(:AtlasCollection)
  -[:ACTIVATES]->(:Intent)
```

## Intents

- `research` - General research
- `find_information` - Specific information lookup
- `learn_topic` - Learn and store in graph
- `analyze_market` - Market/competitive analysis
- `verify_fact` - Fact verification

## Configuration

Edit `skills/pro_search/seed.cypher` to modify:
- Modes, depths, categories
- Policy rules
- Toolchain steps and tools
- Engine preferences

Then apply to Neo4j:
```bash
cypher-shell -u neo4j -p <pass> < skills/pro_search/seed.cypher
```

## Testing

```bash
# Run graph-only smoke tests
pytest tests/test_pro_search_graph.py -v

# Run executor smoke tests
pytest tests/test_pro_search_executor.py -v

# Test specific aspect
pytest tests/test_pro_search_graph.py::test_pro_search_policies_configured -v
```

## Executor

The `ProSearchExecutor` class reads all configuration from Neo4j and executes the toolchain:

```python
from denis_unified_v1.actions.pro_search_executor import ProSearchExecutor, SearchRequest

executor = ProSearchExecutor()

# Load config from graph
config = executor.load_skill_config()

# Execute research
request = SearchRequest(
    query="your query",
    mode="user_pure",  # or "hybrid", "machine_only"
    depth="standard",  # or "quick", "deep", "continuous"
    category="general", # or "academic", "technical", etc.
)
result = await executor.execute(request)
```

## CLI Usage

```bash
# Basic research
denis research "What is quantum computing?"

# Deep research with specific mode
denis research "quantum computing market trends" --depth deep --mode hybrid

# JSON output for scripting
denis research "test query" --format json

# Different categories
denis research "attention mechanism" --category technical
denis research "transformer architecture" --category academic
```

Available options:
- `--mode`: user_pure, hybrid, machine_only (default: user_pure)
- `--depth`: quick, standard, deep, continuous (default: standard)
- `--category`: general, academic, technical, news, video, reddit (default: general)
- `--format`: human, json (default: human)

## Dark Web (Disabled by Default)

PRO_SEARCH includes a dark web research extension (`DarkResearch v3`) that is disabled by default. It requires:
- Explicit approval
- Audit logging (mandatory)
- Sandboxed execution (waydroid_weston)

To enable, set `dark_web.enabled: true` in manifest.yaml.
