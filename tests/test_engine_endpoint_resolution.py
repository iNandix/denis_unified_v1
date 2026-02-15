import pytest

from denis_unified_v1.inference.router import InferenceRouter
from denis_unified_v1.inference.llamacpp_client import LlamaCppClient
from denis_unified_v1.inference.legacy_core_client import LegacyCoreClient


def test_router_resolves_llamacpp_engine_to_endpoint_client():
    """
    Smoke: router -> engine_id -> endpoint correct (no silent legacy).

    This does NOT perform network calls. It verifies that for provider_key=llamacpp,
    the router instantiates a per-engine LlamaCppClient(endpoint) rather than using legacy_core.
    """
    router = InferenceRouter()

    engine_id = "llamacpp_node2_1"
    expected_endpoint = "http://10.10.10.2:8081"

    # Ensure engine exists in registry
    assert engine_id in router.engine_registry, "expected engine_id present in router.engine_registry"

    entry = router.engine_registry[engine_id]
    assert entry.get("provider_key") == "llamacpp"
    assert entry.get("endpoint") == expected_endpoint

    client = entry.get("client")
    assert isinstance(client, LlamaCppClient), "llamacpp engines must use LlamaCppClient(endpoint)"
    assert client.endpoint == expected_endpoint.rstrip("/")

    # legacy_core must be a separate client (not aliasing llamacpp)
    assert "legacy_core" in router.clients
    assert isinstance(router.clients["legacy_core"], LegacyCoreClient)
