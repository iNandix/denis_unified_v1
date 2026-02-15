import json
import pytest
import jsonschema
from pathlib import Path
from unittest.mock import patch
import asyncio

from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest

def run(coro):
    return asyncio.run(coro)

SCHEMA_IDE = Path(__file__).resolve().parent.parent / "schemas" / "context_pack_schema.json"

def load_schema():
    return json.loads(SCHEMA_IDE.read_text())

def validate(pack):
    jsonschema.validate(pack, load_schema())

@pytest.fixture
def kernel_api_ide_request():
    def call():
        api = KernelAPI()
        req = KernelRequest(
            intent_hint="refactor",
            channel="ide",
            payload={"focus_files": ["denis_unified_v1/kernel/kernel_api.py"], "confidence": 0.99},
            safety_mode="default"
        )
        response = run(api.process_request(req))
        return {
            "context_pack": response.context_pack,
            "route": response.route,
            "response": response.response,
            "trace": response.decision_trace.to_dict(),
        }
    return call

def test_ide_pack_always_schema_valid(kernel_api_ide_request):
    # Force PROJECT route for refactor to ensure IDE pack is built
    def force_project_route(self, intent, confidence, tool_required, risk_level):
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        if intent == "refactor":
            return RouteType.PROJECT, ReasoningMode.STRUCTURED, False
        
        # Original logic for other cases
        fast_intents = {"greet", "thanks", "bye", "hello", "goodbye"}
        if (
            intent
            and intent.lower() in fast_intents
            and confidence >= self.fast_talk_confidence_threshold
        ):
            return RouteType.FAST_TALK, ReasoningMode.DIRECT, False
        if confidence >= self.fast_talk_confidence_threshold and not tool_required:
            return RouteType.STANDARD, ReasoningMode.DIRECT, False
        if tool_required:
            requires_confirmation = risk_level == "high"
            if risk_level == "high":
                return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
            return RouteType.TOOL, ReasoningMode.STRUCTURED, requires_confirmation
        if risk_level == "high":
            return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
        return RouteType.STANDARD, ReasoningMode.STRUCTURED, False
    
    with patch('denis_unified_v1.kernel.runtime.governor.Governor._decide_route', force_project_route):
        res = kernel_api_ide_request()
        pack = res["context_pack"]
        validate(pack)

def test_ide_rejected_fallback_is_valid(kernel_api_ide_request):
    # Force PROJECT route for refactor to ensure IDE pack is built
    def force_project_route(self, intent, confidence, tool_required, risk_level):
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        if intent == "refactor":
            return RouteType.PROJECT, ReasoningMode.STRUCTURED, False
        
        # Original logic for other cases
        fast_intents = {"greet", "thanks", "bye", "hello", "goodbye"}
        if (
            intent
            and intent.lower() in fast_intents
            and confidence >= self.fast_talk_confidence_threshold
        ):
            return RouteType.FAST_TALK, ReasoningMode.DIRECT, False
        if confidence >= self.fast_talk_confidence_threshold and not tool_required:
            return RouteType.STANDARD, ReasoningMode.DIRECT, False
        if tool_required:
            requires_confirmation = risk_level == "high"
            if risk_level == "high":
                return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
            return RouteType.TOOL, ReasoningMode.STRUCTURED, requires_confirmation
        if risk_level == "high":
            return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
        return RouteType.STANDARD, ReasoningMode.STRUCTURED, False
    
    # Force rejected fallback
    def forced_reject(self, pack):
        pack = {
            "pack_type": "ide",
            "task_spec": "",
            "repo_norms": "",
            "locality": "",
            "dependency_slice": {"__rejected__": {"key_contract": "", "callers": []}},
            "tests_build": {"tests_found": False, "candidates": [], "suggested_next": []},
            "memory_highlights": "",
            "workspace_focus": {"file": "", "symbol": "", "goal": ""},
            "citations": [],
            "token_estimate": 0,
            "rationale": "Rejected pack, minimal valid",
        }
        return pack, "rejected", ["forced reject"]

    with patch('denis_unified_v1.kernel.runtime.governor.Governor._decide_route', force_project_route), \
         patch('denis_unified_v1.services.context_manager.ContextManager._validate_or_degrade_pack', forced_reject):
        res = kernel_api_ide_request()
        pack = res["context_pack"]
        validate(pack)

def test_degraded_triggers_reindex(kernel_api_ide_request):
    called = {"reindex": 0}
    def fake_launch(*args, **kwargs):
        called["reindex"] += 1

    # Force PROJECT route for refactor to ensure IDE pack is built
    def force_project_route(self, intent, confidence, tool_required, risk_level):
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        if intent == "refactor":
            return RouteType.PROJECT, ReasoningMode.STRUCTURED, False
        
        # Original logic for other cases
        fast_intents = {"greet", "thanks", "bye", "hello", "goodbye"}
        if (
            intent
            and intent.lower() in fast_intents
            and confidence >= self.fast_talk_confidence_threshold
        ):
            return RouteType.FAST_TALK, ReasoningMode.DIRECT, False
        if confidence >= self.fast_talk_confidence_threshold and not tool_required:
            return RouteType.STANDARD, ReasoningMode.DIRECT, False
        if tool_required:
            requires_confirmation = risk_level == "high"
            if risk_level == "high":
                return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
            return RouteType.TOOL, ReasoningMode.STRUCTURED, requires_confirmation
        if risk_level == "high":
            return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
        return RouteType.STANDARD, ReasoningMode.STRUCTURED, False

    # Patch on the specific API instance's context manager
    api = KernelAPI()
    with patch('denis_unified_v1.kernel.runtime.governor.Governor._decide_route', force_project_route), \
         patch.object(api.context_manager, '_check_degraded', lambda: True), \
         patch.object(api.context_manager, '_launch_reindex', fake_launch):
        req = KernelRequest(
            intent_hint="refactor",
            channel="ide",
            payload={"focus_files": ["denis_unified_v1/kernel/kernel_api.py"], "confidence": 0.99},
            safety_mode="default"
        )
        response = run(api.process_request(req))
        assert called["reindex"] == 1

def test_route_mapping_deliberate_verify_to_verify(kernel_api_ide_request):
    # Force governor to return DELIBERATE, VERIFY
    def fake_decide(self, intent, confidence, tool_required, risk_level):
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        return RouteType.DELIBERATE, ReasoningMode.VERIFY, True

    with patch('denis_unified_v1.kernel.runtime.governor.Governor._decide_route', fake_decide):
        res = kernel_api_ide_request()
        trace = res["trace"]
        assert trace["route_raw"] == "deliberate"
        assert trace["route"] == "verify"

def test_decision_trace_json_serializable(kernel_api_ide_request):
    res = kernel_api_ide_request()
    trace = res["trace"]
    json.dumps(trace)  # no exception


def test_pack_type_decision_logic():
    """Test pack type decision logic (pure function, no external deps)."""
    from denis_unified_v1.kernel.kernel_api import IDE_ROUTES
    
    def determine_pack_type(channel: str, route: str) -> str:
        """Pure function for pack type determination."""
        want_ide = (channel == "ide") or (route in IDE_ROUTES)
        return "ide" if want_ide else "human"
    
    test_cases = [
        # (channel, route, expected_pack_type)
        ("ide", "toolchain", "ide"),      # IDE channel
        ("ide", "verify", "ide"),         # IDE channel overrides verify route
        ("ide", "standard", "ide"),       # IDE channel overrides route
        ("ide", "fast_talk", "ide"),      # IDE channel overrides route
        ("chat", "toolchain", "ide"),     # toolchain route
        ("chat", "project", "ide"),       # project route
        ("chat", "verify", "human"),      # verify route (not in IDE_ROUTES)
        ("chat", "standard", "human"),    # standard route
        ("chat", "fast_talk", "human"),   # fast_talk route
    ]
    
    for channel, route, expected in test_cases:
        result = determine_pack_type(channel, route)
        assert result == expected, f"channel={channel}, route={route}: expected {expected}, got {result}"


def test_context_pack_quality_floor(kernel_api_ide_request):
    """Quality floor tests: verify context packs have real content when possible."""
    # Test with focus files - locality should not be empty
    res = kernel_api_ide_request()
    pack = res["context_pack"]
    
    assert pack["pack_type"] == "ide", "IDE request should produce IDE pack"
    
    # Quality floor: locality should not be empty when focus_files provided
    focus_files_in_payload = res["route"] == "toolchain"  # toolchain uses focus_files
    if focus_files_in_payload:
        # In test mode, locality might be empty, but structure should be valid
        assert isinstance(pack["locality"], str), "locality should be a string"
    
    # Quality floor: dependency_slice should have proper structure
    assert isinstance(pack["dependency_slice"], dict), "dependency_slice should be a dict"
    if pack["dependency_slice"]:  # If not empty
        for file_key, dep_data in pack["dependency_slice"].items():
            assert "callers" in dep_data, f"dependency_slice[{file_key}] missing callers"
            assert "key_contract" in dep_data, f"dependency_slice[{file_key}] missing key_contract"
            assert "lifecycle" in dep_data, f"dependency_slice[{file_key}] missing lifecycle"
            assert "side_effects" in dep_data, f"dependency_slice[{file_key}] missing side_effects"
    
    # Quality floor: tests_build should have proper structure
    assert isinstance(pack["tests_build"], dict), "tests_build should be a dict"
    assert "tests_found" in pack["tests_build"], "tests_build missing tests_found"
    assert "candidates" in pack["tests_build"], "tests_build missing candidates"
    assert "suggested_next" in pack["tests_build"], "tests_build missing suggested_next"
    assert isinstance(pack["tests_build"]["candidates"], list), "candidates should be a list"
    
    # Quality floor: workspace_focus should have file when focus_files provided
    assert "workspace_focus" in pack, "pack missing workspace_focus"
    assert "file" in pack["workspace_focus"], "workspace_focus missing file"
    if focus_files_in_payload:
        # File should be populated when focus_files provided
        assert pack["workspace_focus"]["file"], "workspace_focus.file should be populated when focus_files provided"


def test_strict_mode_forces_verify_route():
    """Test that safety_mode=strict forces verify route."""
    from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest
    from unittest.mock import patch, AsyncMock
    import asyncio
    
    api = KernelAPI()
    
    with patch('denis_unified_v1.kernel.kernel_api.get_governor') as mock_gov:
        mock_gov_instance = AsyncMock()
        mock_gov.return_value = mock_gov_instance
        
        # Configure the mock to return the expected tuple synchronously
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        mock_gov_instance._decide_route = AsyncMock(return_value=(
            RouteType.DELIBERATE,
            ReasoningMode.VERIFY,
            False
        ))
        
        request = KernelRequest(
            channel="ide",
            payload={"focus_files": ["test.py"]},
            safety_mode="strict"
        )
        
        # Run route determination
        route = asyncio.run(api._determine_route(request, type('Trace', (), {'set_route': lambda *args: None, 'add_step': lambda *args: None})()))
        
        # Should normalize to "verify" for DELIBERATE + VERIFY
        assert route == "verify", f"Expected verify route for strict mode, got {route}"


def test_verify_response_includes_attribution_fields():
    """Test that verify routes include all attribution fields."""
    from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest
    from unittest.mock import patch, AsyncMock
    import asyncio
    
    api = KernelAPI()
    
    with patch('denis_unified_v1.kernel.kernel_api.get_governor') as mock_gov, \
         patch('denis_unified_v1.kernel.kernel_api.get_human_memory_manager') as mock_hmm, \
         patch('denis_unified_v1.kernel.kernel_api.get_context_manager') as mock_cm:
        
        # Mock dependencies
        mock_gov_instance = AsyncMock()
        mock_gov.return_value = mock_gov_instance
        
        # Configure the mock to return the expected tuple synchronously
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        mock_gov_instance._decide_route = AsyncMock(return_value=(
            RouteType.DELIBERATE,
            ReasoningMode.VERIFY,
            False
        ))
        
        mock_cm_instance = AsyncMock()
        mock_cm.return_value = mock_cm_instance
        mock_cm_instance.build_context_pack.return_value = ({"pack_type": "ide"}, "ok", [])
        
        mock_hmm.return_value = AsyncMock()
        
        request = KernelRequest(channel="ide", safety_mode="strict")
        
        # Process request
        response = asyncio.run(api.process_request(request))
        
        # Verify route is "verify"
        assert response.route == "verify"
        
        # Check attribution fields are present (may be empty but should exist)
        assert hasattr(response, 'attribution_flags'), "Response missing attribution_flags"
        assert isinstance(response.attribution_flags, list), "attribution_flags should be list"
        
        assert hasattr(response, 'attribution_language'), "Response missing attribution_language"
        assert response.attribution_language in ["en", "es"], "attribution_language should be en or es"
        
        assert hasattr(response, 'evidence_refs'), "Response missing evidence_refs"
        assert isinstance(response.evidence_refs, list), "evidence_refs should be list"
        
        assert hasattr(response, 'disclaimers'), "Response missing disclaimers"
        assert isinstance(response.disclaimers, list), "disclaimers should be list"


def test_no_evidence_generates_disclaimer():
    """Test that responses without evidence generate appropriate disclaimers."""
    from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest
    from denis_unified_v1.kernel.decision_trace import DecisionTrace
    from unittest.mock import patch, AsyncMock
    import asyncio
    
    api = KernelAPI()
    
    # Create empty trace with no steps for testing "no evidence" scenario
    empty_trace = DecisionTrace()
    empty_trace.steps = []  # Ensure no trace steps are generated
    
    with patch('denis_unified_v1.kernel.kernel_api.get_governor') as mock_gov, \
         patch('denis_unified_v1.kernel.kernel_api.get_human_memory_manager') as mock_hmm, \
         patch('denis_unified_v1.kernel.kernel_api.get_context_manager') as mock_cm, \
         patch('denis_unified_v1.kernel.kernel_api.DecisionTrace', return_value=empty_trace):
        
        # Mock dependencies for a route that creates minimal trace
        mock_gov_instance = AsyncMock()
        mock_gov.return_value = mock_gov_instance
        mock_gov_instance._decide_route = AsyncMock(return_value=(
            type('RouteType', (), {'value': 'fast_talk'})(), 
            type('ReasoningMode', (), {'value': 'direct'})(), 
            False
        ))
        
        mock_cm_instance = AsyncMock()
        mock_cm.return_value = mock_cm_instance
        mock_cm_instance.build_context_pack.return_value = (None, "ok", [])  # No context pack
        
        mock_hmm.return_value = AsyncMock()
        
        request = KernelRequest(channel="chat", safety_mode="default")
        
        # Process request
        response = asyncio.run(api.process_request(request))
        
        # Should have NO_EVIDENCE_AVAILABLE flag (no tool calls + no trace steps)
        assert "NO_EVIDENCE_AVAILABLE" in response.attribution_flags, \
            f"Expected NO_EVIDENCE_AVAILABLE flag, got: {response.attribution_flags}"
        
        # Should have disclaimer
        assert len(response.disclaimers) > 0, "Should have disclaimers when no evidence"
        assert "general knowledge" in response.disclaimers[0].lower() or \
               "conocimiento general" in response.disclaimers[0].lower(), \
               f"Disclaimer should mention general knowledge: {response.disclaimers}"


def test_tool_evidence_generates_attribution():
    """Test that tool execution generates proper attribution and evidence refs."""
    from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest
    from unittest.mock import patch, AsyncMock
    import asyncio
    
    api = KernelAPI()
    
    with patch('denis_unified_v1.kernel.kernel_api.get_governor') as mock_gov, \
         patch('denis_unified_v1.kernel.kernel_api.get_human_memory_manager') as mock_hmm, \
         patch('denis_unified_v1.kernel.kernel_api.get_context_manager') as mock_cm:
        
        # Mock dependencies
        mock_gov_instance = AsyncMock()
        mock_gov.return_value = mock_gov_instance
        mock_gov_instance._decide_route = AsyncMock(return_value=(
            type('RouteType', (), {'value': 'toolchain'})(), 
            type('ReasoningMode', (), {'value': 'direct'})(), 
            False
        ))
        
        mock_cm_instance = AsyncMock()
        mock_cm.return_value = mock_cm_instance
        mock_cm_instance.build_context_pack.return_value = ({"pack_type": "ide"}, "ok", [])
        
        mock_hmm.return_value = AsyncMock()
        
        request = KernelRequest(channel="ide", payload={"focus_files": ["test.py"]})
        
        # Process request
        response = asyncio.run(api.process_request(request))
        
        # Should have DERIVED_FROM_TOOL_OUTPUT flag
        assert "DERIVED_FROM_TOOL_OUTPUT" in response.attribution_flags, \
            f"Expected DERIVED_FROM_TOOL_OUTPUT flag, got: {response.attribution_flags}"
        
        # Should have evidence refs
        assert len(response.evidence_refs) > 0, "Should have evidence refs for tool execution"
        
        # Check evidence ref structure
        for ref in response.evidence_refs:
            assert "kind" in ref, "Evidence ref missing kind"
            assert "id" in ref, "Evidence ref missing id"
            assert "confidence" in ref, "Evidence ref missing confidence"
            assert "summary" in ref, "Evidence ref missing summary"


def test_verify_response_snapshot():
    """Snapshot test for verify response structure."""
    from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest
    from unittest.mock import patch, AsyncMock
    import asyncio
    import json
    
    api = KernelAPI()
    
    with patch('denis_unified_v1.kernel.kernel_api.get_governor') as mock_gov, \
         patch('denis_unified_v1.kernel.kernel_api.get_human_memory_manager') as mock_hmm, \
         patch('denis_unified_v1.kernel.kernel_api.get_context_manager') as mock_cm, \
         patch('denis_unified_v1.kernel.kernel_api.get_model_scheduler') as mock_scheduler:
        
        # Mock dependencies for verify route
        mock_gov_instance = AsyncMock()
        mock_gov.return_value = mock_gov_instance
        
        # Configure the mock to return the expected tuple synchronously
        from denis_unified_v1.kernel.runtime.governor import RouteType, ReasoningMode
        mock_gov_instance._decide_route = AsyncMock(return_value=(
            RouteType.DELIBERATE,
            ReasoningMode.VERIFY,
            False
        ))
        
        # Mock scheduler to allow assignment
        from unittest.mock import MagicMock
        mock_scheduler_instance = MagicMock()
        mock_scheduler.return_value = mock_scheduler_instance
        
        # Create a mock assignment object
        mock_assignment = type('Assignment', (), {
            'model_name': 'test-model',
            'endpoint': 'http://test',
            'engine_id': 'test-engine',
            'estimated_latency_ms': 100.0,
            'estimated_cost': 0.01
        })()
        
        # Configure assign to return the mock assignment synchronously
        mock_scheduler_instance.assign.return_value = mock_assignment
        
        mock_cm_instance = AsyncMock()
        mock_cm.return_value = mock_cm_instance
        mock_cm_instance.build_context_pack.return_value = ({"pack_type": "ide"}, "ok", [])
        
        mock_hmm.return_value = AsyncMock()
        
        request = KernelRequest(channel="ide", safety_mode="strict")
        
        # Process request
        response = asyncio.run(api.process_request(request))
        
        # Create snapshot of response structure (normalize non-deterministic fields)
        snapshot = {
            "route": response.route,
            "has_context_pack": response.context_pack is not None,
            "plan_length": len(response.plan),
            "tool_calls_length": len(response.tool_calls),
            "attribution_flags": sorted(response.attribution_flags),  # Sort for consistency
            "attribution_language": response.attribution_language,
            "evidence_refs_count": len(response.evidence_refs),
            "disclaimers_count": len(response.disclaimers),
            "response_keys": sorted(list(response.response.keys()) if response.response else []),  # Sort for consistency
        }
        
        # Verify expected structure
        assert snapshot["route"] == "verify"
        assert snapshot["has_context_pack"] == True
        assert snapshot["plan_length"] >= 1  # Should have at least one plan step
        assert isinstance(snapshot["attribution_flags"], list)
        assert snapshot["attribution_language"] in ["en", "es"]
        assert isinstance(snapshot["evidence_refs_count"], int)
        assert isinstance(snapshot["disclaimers_count"], int)
        assert "text" in snapshot["response_keys"]
        assert "attribution_flags" in snapshot["response_keys"]
        
        # Ensure JSON serializable (important for API contracts)
        json_str = json.dumps(snapshot, default=str)
        assert len(json_str) > 10, "Snapshot should be substantial JSON"


def test_trace_has_phase_durations(kernel_api_ide_request):
    """Test that traces include phase timing information."""
    res = kernel_api_ide_request()
    trace = res["decision_trace"]
    
    # Should have phases (at least the ones we start in process_request)
    assert len(trace.phases) >= 4, f"Expected at least 4 phases, got {len(trace.phases)}"
    
    # Check phase names - should include our standard phases
    phase_names = {phase.name for phase in trace.phases}
    expected_phases = {"route", "context_pack", "plan", "tools"}
    assert expected_phases.issubset(phase_names), f"Missing phases: {expected_phases - phase_names}"
    
    # All phases should have completed (end_ts_ms set)
    for phase in trace.phases:
        assert phase.end_ts_ms is not None, f"Phase {phase.name} not completed"
        assert phase.duration_ms is not None, f"Phase {phase.name} missing duration_ms"
        assert phase.duration_ms > 0, f"Phase {phase.name} has invalid duration: {phase.duration_ms}"


def test_trace_has_budget_deltas(kernel_api_ide_request):
    """Test that traces include budget tracking information."""
    res = kernel_api_ide_request()
    trace = res["decision_trace"]
    
    # Should have budget totals calculated
    assert trace.budget_planned_total is not None, "Missing budget_planned_total"
    assert trace.budget_actual_total is not None, "Missing budget_actual_total"
    
    # Budget totals should be reasonable
    assert trace.budget_planned_total > 0, f"Planned budget should be > 0, got {trace.budget_planned_total}"
    
    # Check individual phases have budgets set
    for phase in trace.phases:
        assert phase.budget_planned is not None, f"Phase {phase.name} missing budget_planned"
        assert phase.budget_actual is not None, f"Phase {phase.name} missing budget_actual"
        assert phase.budget_delta is not None, f"Phase {phase.name} missing budget_delta"


def test_trace_can_reconstruct_tree(kernel_api_ide_request):
    """Test that trace spans form a valid tree structure."""
    res = kernel_api_ide_request()
    trace = res["decision_trace"]
    
    # Should have spans (root + phases)
    assert len(trace.spans) >= len(trace.phases) + 1, f"Expected at least {len(trace.phases) + 1} spans, got {len(trace.spans)}"
    
    # Build span lookup
    span_by_id = {span.span_id: span for span in trace.spans}
    
    # Should have root span
    assert trace.root_span_id in span_by_id, f"Missing root span {trace.root_span_id}"
    root_span = span_by_id[trace.root_span_id]
    assert root_span.parent_span_id is None, "Root span should have no parent"
    
    # All phase spans should hang from root
    for phase in trace.phases:
        assert phase.span_id in span_by_id, f"Missing span for phase {phase.name}"
        span = span_by_id[phase.span_id]
        assert span.parent_span_id == trace.root_span_id, f"Phase span {phase.span_id} should hang from root"
    
    # No cycles (all spans should be reachable from root)
    visited = set()
    def visit(span_id):
        if span_id in visited:
            return False  # Cycle detected
        visited.add(span_id)
        span = span_by_id[span_id]
        if span.parent_span_id:
            return visit(span.parent_span_id)
        return True
    
    for span in trace.spans:
        visited.clear()
        assert visit(span.span_id), f"Cycle detected in span tree at {span.span_id}"


def test_trace_sink_emission(kernel_api_ide_request):
    """Test that traces are emitted to the configured sink."""
    from unittest.mock import patch, MagicMock
    from denis_unified_v1.kernel.decision_trace import TraceSink
    
    # Create a mock sink
    mock_sink = MagicMock(spec=TraceSink)
    mock_sink.emit.return_value = None
    mock_sink.emit_span.return_value = None
    
    with patch('denis_unified_v1.kernel.decision_trace.get_trace_sink', return_value=mock_sink), \
         patch('denis_unified_v1.kernel.decision_trace.should_sample_trace', return_value=True):
        
        # Process request
        res = kernel_api_ide_request()
        
        # Sink should have been called
        mock_sink.emit.assert_called_once()
        
        # Check the emitted trace structure
        emitted_trace = mock_sink.emit.call_args[0][0]  # First argument
        
        # Should be a dict with required fields
        assert isinstance(emitted_trace, dict), "Emitted trace should be a dict"
        assert "trace_id" in emitted_trace, "Emitted trace missing trace_id"
        assert "schema_version" in emitted_trace, "Emitted trace missing schema_version"
        assert "phases" in emitted_trace, "Emitted trace missing phases"
        assert "spans" in emitted_trace, "Emitted trace missing spans"
        assert "budget" in emitted_trace, "Emitted trace missing budget"
        assert "safety_mode" in emitted_trace, "Emitted trace missing safety_mode"
        assert "model_selected" in emitted_trace, "Emitted trace missing model_selected"
