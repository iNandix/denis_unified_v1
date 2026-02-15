"""Internal contract tests for artifacts (context packs, decision traces)."""

import json
import pytest
from typing import Dict, Any

from denis_unified_v1.services.context_manager import get_context_manager
from denis_unified_v1.kernel.kernel_api import KernelRequest, get_kernel_api
from denis_unified_v1.kernel.decision_trace import DecisionTrace


class TestInternalContracts:
    """Internal artifact contract stability tests."""

    @pytest.mark.contract
    def test_context_pack_contract_fixtures(self):
        """Test context pack against quality contract."""
        cm = get_context_manager()

        # Generate context pack for testing
        pack, status, errors = cm.build_context_pack(
            intent="refactor",
            focus_files=["test_file.py"],
            workspace_id="test_workspace"
        )

        # Validate schema version
        assert pack.get("schema_version") == "context_pack_v1", \
            f"Expected schema_version 'context_pack_v1', got {pack.get('schema_version')}"

        # Validate pack type
        assert pack.get("pack_type") == "ide", \
            f"Expected pack_type 'ide', got {pack.get('pack_type')}"

        # Validate required fields exist
        required_fields = [
            "task_spec", "repo_norms", "locality", "dependency_slice",
            "tests_build", "memory_highlights", "workspace_focus",
            "citations", "token_estimate", "rationale"
        ]

        for field in required_fields:
            assert field in pack, f"Missing required field: {field}"

        # Validate token_estimate is reasonable
        token_estimate = pack.get("token_estimate", 0)
        assert isinstance(token_estimate, int), "token_estimate should be int"
        assert token_estimate >= 0, f"token_estimate should be >= 0, got {token_estimate}"

        # Validate dependency_slice structure
        dep_slice = pack.get("dependency_slice", {})
        assert isinstance(dep_slice, dict), "dependency_slice should be dict"

        for file, deps in dep_slice.items():
            assert isinstance(deps, dict), f"dependency_slice['{file}'] should be dict"
            required_dep_fields = ["callers", "key_contract", "lifecycle", "side_effects"]
            for field in required_dep_fields:
                assert field in deps, f"Missing dependency field '{field}' in {file}"

        # Validate tests_build structure
        tests_build = pack.get("tests_build", {})
        assert isinstance(tests_build, dict), "tests_build should be dict"
        assert "tests_found" in tests_build, "tests_build missing 'tests_found'"
        assert "candidates" in tests_build, "tests_build missing 'candidates'"
        assert "suggested_next" in tests_build, "tests_build missing 'suggested_next'"

        # Validate workspace_focus structure
        workspace_focus = pack.get("workspace_focus", {})
        assert isinstance(workspace_focus, dict), "workspace_focus should be dict"
        required_focus_fields = ["file", "symbol", "goal"]
        for field in required_focus_fields:
            assert field in workspace_focus, f"Missing workspace_focus field '{field}'"

    @pytest.mark.contract
    def test_decision_trace_contract_fixtures(self):
        """Test decision trace against contract."""
        # Create a simple trace for testing
        trace = DecisionTrace()
        trace.set_route("deliberate", "verify", "verify")
        trace.set_safety_mode("strict")
        trace.set_model_selected("test-model")

        # Add a phase
        span_id = trace.start_phase("route", budget_planned=50)
        trace.end_phase(span_id, budget_actual=25)

        # Convert to dict for validation
        trace_dict = trace.to_dict()

        # Validate schema version
        assert trace_dict.get("schema_version") == "decision_trace_v1", \
            f"Expected schema_version 'decision_trace_v1', got {trace_dict.get('schema_version')}"

        # Validate trace ID
        assert "trace_id" in trace_dict, "Missing trace_id"
        assert isinstance(trace_dict["trace_id"], str), "trace_id should be string"

        # Validate timestamps
        assert "start_ts_ms" in trace_dict, "Missing start_ts_ms"
        assert isinstance(trace_dict["start_ts_ms"], int), "start_ts_ms should be int"
        assert trace_dict["start_ts_ms"] > 0, "start_ts_ms should be > 0"

        assert "duration_ms" in trace_dict, "Missing duration_ms"
        assert isinstance(trace_dict["duration_ms"], int), "duration_ms should be int"

        # Validate routing info
        assert "route" in trace_dict, "Missing route"
        assert "reasoning_mode" in trace_dict, "Missing reasoning_mode"

        # Validate safety and model
        assert "safety_mode" in trace_dict, "Missing safety_mode"
        assert trace_dict["safety_mode"] == "strict", "safety_mode should be 'strict'"

        assert "model_selected" in trace_dict, "Missing model_selected"
        assert trace_dict["model_selected"] == "test-model", "model_selected should be 'test-model'"

        # Validate budget structure
        assert "budget" in trace_dict, "Missing budget"
        budget = trace_dict["budget"]
        assert isinstance(budget, dict), "budget should be dict"
        assert "planned_total" in budget, "budget missing planned_total"
        assert "actual_total" in budget, "budget missing actual_total"
        assert "delta_total" in budget, "budget missing delta_total"

        # Validate phases structure
        assert "phases" in trace_dict, "Missing phases"
        phases = trace_dict["phases"]
        assert isinstance(phases, list), "phases should be list"
        assert len(phases) >= 1, "Should have at least 1 phase"

        # Validate phase structure
        phase = phases[0]
        assert isinstance(phase, dict), "phase should be dict"
        required_phase_fields = [
            "name", "span_id", "start_ts_ms", "end_ts_ms", "duration_ms",
            "budget_planned", "budget_actual", "budget_delta"
        ]
        for field in required_phase_fields:
            assert field in phase, f"Phase missing field '{field}'"

        # Validate spans structure
        assert "spans" in trace_dict, "Missing spans"
        spans = trace_dict["spans"]
        assert isinstance(spans, list), "spans should be list"
        assert len(spans) >= 2, "Should have at least root + 1 phase span"

        # Validate span structure
        for span in spans:
            assert isinstance(span, dict), "span should be dict"
            required_span_fields = [
                "span_id", "name", "start_ts_ms", "parent_span_id", "duration_ms"
            ]
            for field in required_span_fields:
                assert field in span, f"Span missing field '{field}'"

    @pytest.mark.contract
    @pytest.mark.asyncio
    async def test_kernel_response_contract_stability(self):
        """Test KernelResponse contract stability."""
        api = get_kernel_api()

        # Create a test request
        request = KernelRequest(
            intent_hint="test",
            channel="ide",
            payload={"focus_files": ["test.py"]}
        )

        # Process request (await the async call)
        response = await api.process_request(request)

        # Validate response structure
        assert hasattr(response, 'request_id'), "Response missing request_id"
        assert hasattr(response, 'route'), "Response missing route"
        assert hasattr(response, 'context_pack'), "Response missing context_pack"
        assert hasattr(response, 'plan'), "Response missing plan"
        assert hasattr(response, 'tool_calls'), "Response missing tool_calls"
        assert hasattr(response, 'response'), "Response missing response"

        # Validate verification envelope fields
        assert hasattr(response, 'attribution_flags'), "Response missing attribution_flags"
        assert isinstance(response.attribution_flags, list), "attribution_flags should be list"

        assert hasattr(response, 'attribution_language'), "Response missing attribution_language"
        assert response.attribution_language in ["en", "es"], "attribution_language should be en or es"

        assert hasattr(response, 'evidence_refs'), "Response missing evidence_refs"
        assert isinstance(response.evidence_refs, list), "evidence_refs should be list"

        assert hasattr(response, 'disclaimers'), "Response missing disclaimers"
        assert isinstance(response.disclaimers, list), "disclaimers should be list"

        # Validate response is JSON serializable
        response_dict = {
            "request_id": response.request_id,
            "route": response.route,
            "plan": response.plan,
            "tool_calls": response.tool_calls,
            "response": response.response,
            "attribution_flags": response.attribution_flags,
            "attribution_language": response.attribution_language,
            "evidence_refs": response.evidence_refs,
            "disclaimers": response.disclaimers,
        }

        # Should be JSON serializable
        json_str = json.dumps(response_dict, default=str)
        assert len(json_str) > 10, "Response should serialize to substantial JSON"

        # Should be deserializable
        deserialized = json.loads(json_str)
        assert deserialized["request_id"] == response.request_id
        assert deserialized["route"] == response.route
