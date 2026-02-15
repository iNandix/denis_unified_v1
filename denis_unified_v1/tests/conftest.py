import pytest
import asyncio
from denis_unified_v1.kernel.kernel_api import get_kernel_api, KernelRequest

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

@pytest.fixture
def kernel_api_request_factory():
    def factory(channel="chat", payload=None, intent_hint=None, safety_mode="default"):
        payload = payload or {}
        def call():
            api = get_kernel_api()
            req = KernelRequest(
                intent_hint=intent_hint,
                user_id="u1",
                group_id="g1",
                channel=channel,
                payload=payload,
                budget={"tokens": 2000, "latency_ms": 2000},
                safety_mode=safety_mode,
            )
            response = run(api.process_request(req))  # Fix: await the async process_request using run()
            return {
                "context_pack": response.context_pack,
                "route": response.route,
                "response": response.response,
                "trace": response.decision_trace.to_dict(),
            }
        return call
    return factory

@pytest.fixture
def kernel_api_ide_request(kernel_api_request_factory):
    return kernel_api_request_factory(
        channel="ide",
        payload={"intent": "refactor", "focus_files": ["denis_unified_v1/kernel/kernel_api.py"]},
        intent_hint="refactor",
        safety_mode="default",
    )

@pytest.fixture
def kernel_api_human_request(kernel_api_request_factory):
    return kernel_api_request_factory(
        channel="chat",
        payload={"intent": "chat"},
        intent_hint="chat",
        safety_mode="default",
    )
