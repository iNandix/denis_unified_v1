#!/usr/bin/env python3
"""
Smoke tests for Denis Kernel Human mode.

Run these to verify DoD compliance: human pack valid, anyOf, attribution flags, verify on strict, trace includes validation.
"""

import json
import pytest
import jsonschema
from pathlib import Path
from unittest.mock import patch
import asyncio

from denis_unified_v1.kernel.kernel_api import KernelAPI, KernelRequest

def run(coro):
    return asyncio.run(coro)

SCHEMA_HUMAN = Path(__file__).resolve().parent.parent / "schemas" / "context_pack_human.schema.json"

def load_schema():
    return json.loads(SCHEMA_HUMAN.read_text())

def validate(pack):
    jsonschema.validate(pack, load_schema())

@pytest.fixture
def kernel_api_human_request():
    def call():
        api = KernelAPI()
        req = KernelRequest(
            intent_hint="chat",
            channel="chat",
            payload={},
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

@pytest.fixture
def kernel_api_request_factory():
    def factory(channel="chat", payload=None, intent_hint=None, safety_mode="default"):
        payload = payload or {}
        def call():
            api = KernelAPI()
            req = KernelRequest(
                intent_hint=intent_hint,
                user_id="u1",
                group_id="g1",
                channel=channel,
                payload=payload,
                budget={"tokens": 2000, "latency_ms": 2000},
                safety_mode=safety_mode,
            )
            response = run(api.process_request(req))
            return {
                "context_pack": response.context_pack,
                "route": response.route,
                "response": response.response,
                "trace": response.decision_trace.to_dict(),
            }
        return call
    return factory

def test_human_pack_minimum_schema_valid(kernel_api_human_request):
    res = kernel_api_human_request()
    pack = res["context_pack"]
    validate(pack)

def test_human_anyof_satisfied_topic_ref(kernel_api_human_request):
    res = kernel_api_human_request()
    pack = res["context_pack"]
    assert "topic_ref" in pack
    validate(pack)

def test_human_verified_false_requires_attribution(kernel_api_human_request):
    res = kernel_api_human_request()
    pack = res["context_pack"]
    assert pack["source_note"]["verified"] is False
    assert pack["ask_style"]["do_not_assume"] is True

def test_strict_safety_routes_to_verify(kernel_api_request_factory):
    req = kernel_api_request_factory(channel="chat", payload={"intent": "claim_check"}, safety_mode="strict")
    res = req()
    trace = res["trace"]
    assert trace["route"] == "verify"

def test_trace_contains_context_pack_validation(kernel_api_human_request):
    res = kernel_api_human_request()
    trace = res["trace"]
    ctx = trace.get("context_pack", {})
    assert "status" in ctx and ctx["status"] == "ok"
    assert "context_pack_validated" in [s["name"] for s in trace["steps"]]

    print("Human pack validation test passed")
