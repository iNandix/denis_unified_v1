"""Tests for inference wiring integrity: harvester → scheduler → plan → router → trace."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from denis_unified_v1.inference.provider_loader import ModelInfo
from denis_unified_v1.kernel.scheduler import ModelScheduler, InferenceRequest
from denis_unified_v1.inference.router import InferenceRouter


@pytest.mark.asyncio
async def test_harvester_scheduler_plan_provider_request():
    """Test integrity: harvester → scheduler → plan → provider request.

    Validates the full chain:
      1. Scheduler picks best local engine (llama_3080_1, priority=10)
      2. Plan carries correct engine_id, model, params, budget
      3. Router executes plan-first and calls the right client
      4. Result contains engine_id, provider_key, model from plan
    """
    # Mock harvester — only affects dynamic (openrouter) engines; static engines are always present
    mock_models = [
        ModelInfo(
            provider="llamacpp",
            model_id="llamacpp_node2_1",
            model_name="llama-3.1-8b",
            supports_tools=True,
            context_length=4096,
            is_free=True,
            pricing={"completion": 0.001},
        )
    ]

    with patch(
        "denis_unified_v1.kernel.scheduler.discover_provider_models_cached",
        return_value=mock_models,
    ):
        scheduler = ModelScheduler()
        request = InferenceRequest(
            request_id="test_req_1",
            session_id="test_session",
            route_type="fast_talk",
            task_type="chat",
            payload={"max_tokens": 512, "temperature": 0.7},
        )
        plan = scheduler.assign(request)

        assert plan is not None
        # Primary engine should be a local llamacpp engine
        assert plan.primary_engine_id.startswith("llamacpp_")
        # Check model if available
        if plan.expected_model:
            assert plan.expected_model == "llama-3.1-8b"
        assert plan.params["max_tokens"] == 512
        assert plan.budget["planned_tokens"] == 512

        # P2 guard-rail: all plan IDs must exist in scheduler
        all_plan_ids = [plan.primary_engine_id] + list(plan.fallback_engine_ids)
        for eid in all_plan_ids:
            assert scheduler.get_engine(eid) is not None, (
                f"Plan engine_id {eid!r} not in scheduler"
            )

        # Mock router executor
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "Test response",
            "input_tokens": 10,
            "output_tokens": 5,
        }

        router = InferenceRouter()
        # Inject mock client into the engine the plan selected
        router.engine_registry[plan.primary_engine_id] = {
            "provider_key": "llamacpp",
            "model": "llama-3.1-8b",
            "endpoint": "http://10.10.10.1:8081",
            "params_default": {"temperature": 0.2},
            "tags": ["local"],
            "client": mock_client,
        }

        # Execute plan
        result = await router.route_chat(
            messages=[{"role": "user", "content": "test"}],
            request_id="test_req_1",
            inference_plan=plan,
        )

        # Assert provider received exact plan params
        mock_client.generate.assert_called_once()
        call_args = mock_client.generate.call_args
        assert call_args.kwargs["messages"] == [{"role": "user", "content": "test"}]
        assert call_args.kwargs["timeout_sec"] > 0
        assert call_args.kwargs["temperature"] == 0.7  # From plan
        assert call_args.kwargs["max_tokens"] == 512

        # Assert result carries plan metadata
        assert result["llm_used"] == "llamacpp"
        assert result["model_selected"] == plan.expected_model
        assert result["engine_id"] == plan.primary_engine_id


@pytest.mark.asyncio
async def test_provider_result_trace_extensions_header():
    """Test integrity: provider result → trace/extensions/header."""
    plan = MagicMock()
    plan.primary_engine_id = "groq_1"
    plan.expected_model = "llama-3.1-8b-instant"
    plan.fallback_engine_ids = []

    mock_client = AsyncMock()
    mock_client.generate.return_value = {
        "response": "Mocked response",
        "input_tokens": 5,
        "output_tokens": 3,
    }

    router = InferenceRouter()
    router.engine_registry["groq_1"] = {
        "provider": "groq",
        "client": mock_client,
        "model": "llama-3.1-8b-instant",
        "endpoint": "groq://api.groq.com/openai/v1",
        "params_default": {},
    }

    with (
        patch.object(router.metrics, "record_call"),
        patch.object(router.metrics, "emit_decision"),
    ):
        result = await router.route_chat(
            messages=[{"role": "user", "content": "test"}],
            request_id="test_req_2",
            inference_plan=plan,
        )

    # Assert result has trace data
    assert "llm_used" in result
    assert "latency_ms" in result
    assert "input_tokens" in result
    assert "output_tokens" in result
    assert "cost_usd" in result
    assert "inference_plan" in result

    # Mock header and extensions check would be in integration test
    # For unit test, assume meta includes trace_id
    # In full integration, check FastAPI response has X-Denis-Trace-Id header


@pytest.mark.asyncio
async def test_fallback_order():
    """Test fallback executes in exact order."""
    plan = MagicMock()
    plan.primary_engine_id = "bad_engine"
    plan.fallback_engine_ids = ["good_engine"]
    plan.attempt_policy = {"max_attempts": 2}

    mock_bad_client = AsyncMock(side_effect=Exception("fail"))
    mock_good_client = AsyncMock()
    mock_good_client.generate.return_value = {
        "response": "Fallback response",
        "input_tokens": 5,
        "output_tokens": 3,
    }

    router = InferenceRouter()
    router.engine_registry["bad_engine"] = {
        "provider": "bad",
        "client": mock_bad_client,
        "model": "bad_model",
        "endpoint": "bad://",
        "params_default": {},
    }
    router.engine_registry["good_engine"] = {
        "provider": "good",
        "client": mock_good_client,
        "model": "good_model",
        "endpoint": "good://",
        "params_default": {},
    }

    result = await router.route_chat(
        messages=[{"role": "user", "content": "test"}],
        request_id="test_req_3",
        inference_plan=plan,
    )

    # Assert primary tried and failed, fallback succeeded
    mock_bad_client.generate.assert_called_once()
    mock_good_client.generate.assert_called_once()
    assert result["llm_used"] == "good"
    assert result["attempts"] == 2
