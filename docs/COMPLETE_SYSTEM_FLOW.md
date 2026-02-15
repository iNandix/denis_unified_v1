# DENIS Unified System - Complete End-to-End Flow
# ===============================================

This document outlines the complete flow of the DENIS unified cognitive system,
from user request to execution, showing how all integrated components work together.

## Architecture Overview
```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DENIS UNIFIED SYSTEM                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    FASTAPI APPLICATION SERVER                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    OPENAI COMPATIBLE API                        │ │ │
│  │  │  ┌─────────────────────────────────────────────────────────────┐ │ │ │
│  │  │  │                  KERNEL API (Decision Engine)               │ │ │ │
│  │  │  │  ┌─────────────────────────────────────────────────────────┐ │ │ │ │
│  │  │  │  │                 GATES & AUTHORIZATION                    │ │ │ │ │
│  │  │  │  └─────────────────────────────────────────────────────────┘ │ │ │ │
│  │  │  │  ┌─────────────────────────────────────────────────────────┐ │ │ │ │
│  │  │  │  │              SPRINT MANAGER INTEGRATION                 │ │ │ │ │
│  │  │  │  └─────────────────────────────────────────────────────────┘ │ │ │ │
│  │  │  └─────────────────────────────────────────────────────────────┘ │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                       OBSERVABILITY LAYER                          │ │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │ │
│  │  │                  DECISION TRACE SYSTEM                         │ │ │ │
│  │  │  ┌─────────────────────────────────────────────────────────────┐ │ │ │ │
│  │  │  │                   TRACE SINK (JSONL)                        │ │ │ │ │
│  │  │  │  ┌─────────────────────────────────────────────────────────┐ │ │ │ │
│  │  │  │  │              SCHEMA VERSIONING                          │ │ │ │ │
│  │  │  │  └─────────────────────────────────────────────────────────┘ │ │ │ │
│  │  │  └─────────────────────────────────────────────────────────────┘ │ │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                     CONTRACT VALIDATION                            │ │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │ │
│  │  │                RUNTIME CANARY SYSTEM                          │ │ │ │
│  │  │  ┌─────────────────────────────────────────────────────────────┐ │ │ │ │
│  │  │  │               KUBERNETES CRONJOB                           │ │ │ │ │
│  │  │  └─────────────────────────────────────────────────────────────┘ │ │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Complete Flow: User Request → Execution

### Phase 1: API Ingress & OpenAI Compatibility
```
User Request ──→ FastAPI Server ──→ OpenAI Compatible Handler
                        │                        │
                        │                        └─→ Model Selection
                        │                             └─→ DENIS Runtime
                        │
                        └─→ Health Endpoints (/status, /observability)
```

**What happens:**
1. User sends OpenAI-compatible request to `/v1/chat/completions`
2. FastAPI routes to OpenAI handler
3. Handler extracts context and creates KernelRequest
4. Request enters the Kernel API decision engine

### Phase 2: Kernel Decision Engine
```
KernelRequest ──→ KernelAPI.process_request()
                      │
                      ├─→ Action Authorizer (Gates)
                      │     └─→ Supervisor Gate Runner
                      │         └─→ Control Plane Authorization
                      │
                      ├─→ Governor (Route Decision)
                      │     └─→ deliberate/verify/legacy routing
                      │
                      ├─→ Context Manager
                      │     └─→ Context Pack Generation
                      │         └─→ Quality Floor Validation
                      │
                      └─→ Route-specific Processing
```

**Decision Flow:**
1. **Authorization**: ActionAuthorizer validates against control plane gates
2. **Routing**: Governor decides processing strategy (deliberate/verify/legacy)
3. **Context**: ContextManager builds context packs with quality floors
4. **Trace Start**: DecisionTrace begins capturing the entire flow

### Phase 3: Sprint Manager Integration (When Applicable)
```
Route Decision ──→ Sprint Manager Bridge
                     │
                     ├─→ SprintRequest Creation
                     │     └─→ Project Analysis
                     │         └─→ Code Complexity Assessment
                     │
                     ├─→ Worker Assignment
                     │     └─→ Level-based Crew Assignment
                     │         └─→ Basic/Medium/Advanced Classification
                     │
                     └─→ Task Orchestration
                         └─→ Multi-worker Coordination
```

**Sprint Flow:**
1. **Analysis**: Code level manager analyzes project complexity
2. **Assignment**: Workers assigned based on code levels and capabilities
3. **Coordination**: Sprint orchestrator manages multi-worker execution
4. **Validation**: Change guards enforce quality standards

### Phase 4: Inference & Processing
```
Context Pack ──→ Inference Engine
                   │
                   ├─→ Provider Selection
                   │     └─→ Model Capabilities Matching
                   │
                   ├─→ Prompt Engineering
                   │     └─→ Context Injection & Guards
                   │
                   ├─→ Tool Execution (if needed)
                   │     └─→ Function Calling & Validation
                   │
                   └─→ Response Generation
                       └─→ Quality Filtering
```

**Processing Flow:**
1. **Selection**: Provider loader selects appropriate inference model
2. **Engineering**: Prompts enhanced with context and safety guards
3. **Execution**: Tools called with validation when required
4. **Generation**: Response created with quality filtering

### Phase 5: Observability & Tracing
```
All Operations ──→ DecisionTrace System
                     │
                     ├─→ Phase Tracking
                     │     └─→ Budget Monitoring (planned/actual)
                     │
                     ├─→ Span Tree Construction
                     │     └─→ Parent-Child Relationships
                     │
                     ├─→ Quality Metrics
                     │     └─→ Code Quality, Performance, Security
                     │
                     └─→ Trace Persistence
                         └─→ JSONL Sink with Schema Versioning
```

**Observability Flow:**
1. **Phases**: Each processing phase tracked with duration/budget
2. **Spans**: Hierarchical span tree reconstructed from phases
3. **Metrics**: Quality, performance, and security metrics collected
4. **Persistence**: Traces written to JSONL with version compatibility

### Phase 6: Response Formatting & Extensions
```
Inference Result ──→ Response Formatter
                       │
                       ├─→ OpenAI Compatibility
                       │     └─→ Standard Chat Completion Format
                       │
                       ├─→ Vendor Extensions
                       │     └─→ denis.ai Namespace (conditional)
                       │         └─→ Attribution, Evidence, Disclaimers
                       │
                       └─→ Correlation Headers
                           └─→ X-Denis-Trace-Id (optional)
```

**Response Flow:**
1. **Compatibility**: Response formatted to OpenAI standard
2. **Extensions**: DENIS-specific data in namespaced extensions (only when present)
3. **Correlation**: Optional headers for end-to-end tracing
4. **Safety**: No breaking changes to existing OpenAI integrations

### Phase 7: Contract Validation (Runtime)
```
Response ──→ Contract Canary (every 5min)
              │
              ├─→ OpenAI Shape Validation
              │     └─→ Required Fields, Types, Structure
              │
              ├─→ SLO Compliance
              │     └─→ Latency P95 < 5s, Budget Drift < 1000
              │
              ├─→ Evidence Availability
              │     └─→ Tool-requested responses have evidence
              │
              └─→ Alert Generation
                  └─→ HARD_FAIL → Rollback, WARN → Alert
```

**Validation Flow:**
1. **Shape**: Contract validation ensures API compatibility
2. **Performance**: SLO monitoring for latency and resource usage
3. **Quality**: Evidence validation for tool-using requests
4. **Alerts**: HARD_FAIL triggers automated rollback procedures

## Component Integration Points

### 1. Sprint Manager ↔ DENIS Agent
```
DENIS Agent ──→ SprintManager.create_sprint()
                └─→ Intelligent Orchestration
                    └─→ Worker Assignment & Validation
                        └─→ Task Completion & Sync
```

### 2. Kernel API ↔ Observability
```
KernelAPI ──→ DecisionTrace.start_phase()
             └─→ Budget Tracking
                 └─→ Span Construction
                     └─→ JSONL Persistence
```

### 3. Authorization ↔ Processing
```
ActionAuthorizer ──→ authorize() → DecisionMode
                     └─→ Gate Enforcement
                         └─→ Quality Gates Integration
```

### 4. Context Manager ↔ Quality
```
ContextManager ──→ build_context_pack()
                   └─→ Quality Floor Validation
                       └─→ Evidence Requirements
```

## Data Flow Summary

### Input Processing:
1. **User Request** → OpenAI Compatible API
2. **Route Decision** → Governor (deliberate/verify/legacy)
3. **Context Building** → Context Pack with Quality Floors
4. **Authorization** → Control Plane Gates
5. **Sprint Integration** → Worker Orchestration (when applicable)

### Execution:
1. **Provider Selection** → Model Capabilities Matching
2. **Prompt Engineering** → Context Injection + Safety Guards
3. **Tool Execution** → Function Calling with Validation
4. **Response Generation** → Quality Filtering

### Observability:
1. **Trace Capture** → All phases, budgets, spans
2. **Quality Metrics** → Code, performance, security scores
3. **Schema Versioning** → Backward compatibility
4. **Persistence** → JSONL with migration support

### Validation:
1. **Contract Checks** → API compatibility every 5 minutes
2. **SLO Monitoring** → Performance and quality thresholds
3. **Evidence Validation** → Tool responses have backing
4. **Automated Alerts** → HARD_FAIL triggers rollback

## Success Metrics

- **Contract Compliance**: 100% OpenAI compatibility
- **Latency SLO**: P95 < 5 seconds
- **Evidence Coverage**: >80% for tool-requiring prompts
- **Budget Accuracy**: Absolute drift <1000 tokens
- **Quality Gates**: All supervisor gates passing
- **Trace Completeness**: 100% phase/span coverage

This complete flow ensures the DENIS unified system provides reliable, observable, and contract-compliant AI assistance with full operational visibility and automated quality assurance.

## Failure Modes & Degradations

| Failure Scenario | Degradation Behavior | User Impact | Operational Signal |
|------------------|---------------------|-------------|-------------------|
| **Neo4j Unavailable** | Context packs use test fixtures + reduced dependency analysis | Responses may have lower quality but remain functional | `context_pack_v1.rationale` contains "test mode" |
| **Tool Execution Fails** | Verify route activated, responses marked with disclaimers | Users get safer but potentially less helpful responses | `attribution_flags` contains `TOOL_EXECUTION_FAILED` |
| **Budget Exceeded** | Automatic fallback to cheaper provider or truncated response | Responses may be shorter or use different model | `budget.delta_total` > 1000, trace shows provider switch |
| **Contract Validation Fails** | System continues but flags incompatibility | API responses may drift from OpenAI spec | Canary reports `overall_status: "FAIL"` |
| **Trace Sink Unavailable** | Processing continues, traces buffered/dropped | Observability reduced but functionality intact | `/observability` endpoint shows `trace_sink: "degraded"` |
| **Sprint Manager Offline** | Single-worker mode, reduced orchestration | Complex tasks handled sequentially | `integrated_state.enriched_assignments` shows single worker |
| **Evidence Generation Fails** | Strict mode disclaimers, confidence scores reduced | Users warned about unverifiable information | `evidence_refs[].confidence < 0.3` |
| **Quality Gates Blocked** | Request rejected with explanation | Users get clear error messages | HTTP 403 with gate violation details |

### Degradation Hierarchy
1. **Silent Degradations**: Quality reductions (Neo4j, traces) - Monitor metrics
2. **User-Visible Degradations**: Response changes (tools, budget) - Check attribution flags
3. **Blocking Degradations**: Request rejection (gates) - Alert on error rates

## Contracts & Schemas

### Stable Contracts
- **OpenAI Chat Completions API**: 100% compatible, no breaking changes
- **HTTP Response Codes**: Standard REST semantics maintained
- **Authentication**: Bearer token format preserved

### Versioned Schemas
- **decision_trace_v1**: Trace persistence format with migration support
- **context_pack_v1**: Context pack structure for quality floors
- **kernel_response_v1**: Internal response format (not externally exposed)

### Contract Tests
- **OpenAI Shape Validation**: `tests/test_openai_contract.py`
- **Runtime Canary**: `scripts/contract_canary.py` (runs every 5min in prod)
- **Schema Migration**: Automatic backward compatibility

## Operational Signals

### Canary Monitoring
- **overall_status**: "PASS" = system healthy, "FAIL" = hard failure detected
- **hard_failures**: Empty = good, populated = immediate investigation needed
- **warnings**: Monitor trends, may indicate emerging issues

#### Viewing Canary Failures
```bash
# Get canary job logs
kubectl logs -n denis-prod job/denis-contract-canary

# Check canary job status
kubectl get jobs -n denis-prod

# View detailed canary report (if S3 upload enabled)
aws s3 cp s3://denis-canary-reports/$(date +%Y-%m-%d)/report.json -
```

#### HARD_FAIL vs WARN Actions
- **HARD_FAIL** (immediate rollback): 
  - `kubectl rollout undo deployment/denis-api` (rollback to previous version)
  - Notify SRE team immediately
  - Block deployments until root cause resolved
- **WARN** (monitor & investigate): 
  - Add to weekly incident review
  - Check if WARN rate increasing
  - No deployment blocks unless pattern emerges

### Trace Analysis
- **phase.duration_ms**: > 5000ms = performance issue
- **budget.delta_total**: > 1000 = resource inefficiency
- **span_tree**: Missing spans = observability gaps
- **schema_version**: Ensure backward compatibility

### Attribution Flags (Red Flags)
- **TOOL_EXECUTION_FAILED**: Tool reliability issues
- **SAFETY_MODE_STRICT_APPLIED + NO_EVIDENCE_AVAILABLE**: High-risk response
- **DERIVED_FROM_TOOL_OUTPUT**: Normal for tool-using requests
- **ASSUMPTION_MADE**: Verify route activated, check evidence quality

### Budget Drift Patterns
- **Ratio > 2.0**: Model selection or prompt engineering issues
- **Absolute > 1000**: Potential resource leaks or inefficient processing
- **Consistent negative delta**: Under-budgeting in planning

## Sprint Manager Role

### Responsibilities
- **Code Level Analysis**: Classify files as basic/medium/advanced complexity
- **Worker Assignment**: Match tasks to appropriate specialized crews
- **Validation Pipeline**: Enforce quality gates based on code complexity
- **Git-Graph Synchronization**: Maintain alignment between code and knowledge graph
- **Change Guard**: Prevent introduction of violations (TODOs, stubs, etc.)

### Non-Responsibilities
- **Direct Code Generation**: Delegates to DENIS agent workers
- **Real-time Inference**: Focuses on planning and orchestration
- **User Interaction**: CLI-only, no direct API exposure
- **Deployment**: Planning only, execution handled by workers

### Artifacts Produced
- **sprint.json**: Session state, assignments, progress tracking
- **DecisionTrace**: Planning phase traces with budget tracking
- **Validation Reports**: Pre/post-commit quality assessments
- **Git Commits**: Structured commits from validated worker tasks

### Integration in 7-Phase Flow
- **Phase 3**: Sprint Manager analyzes project and assigns workers
- **Phase 4**: Individual workers execute via DENIS agent
- **Phase 5**: Planning traces captured, budget tracked
- **Phase 6**: Validation results influence response disclaimers
- **Phase 7**: Contract canary validates orchestration outcomes

The Sprint Manager transforms complex development tasks into orchestrated, quality-assured execution while maintaining full traceability and safety guarantees.
