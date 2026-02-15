from denis_unified_v1.inference.router import InferenceRouter
from denis_unified_v1.inference.llamacpp_client import LlamaCppClient
from denis_unified_v1.inference.legacy_core_client import LegacyCoreClient


def test_router_resolves_llamacpp_engine_to_endpoint_client():
    """Smoke: router -> engine_id -> endpoint consistent (no silent legacy).

    No network calls. For provider_key=llamacpp, router must instantiate a per-engine
    LlamaCppClient(endpoint) rather than using legacy_core.
    """
    router = InferenceRouter()

    engine_id = "llamacpp_node2_1"

    assert engine_id in router.engine_registry

    entry = router.engine_registry[engine_id]
    assert entry.get("provider_key") == "llamacpp"

    endpoint = entry.get("endpoint")
    assert isinstance(endpoint, str) and endpoint.strip()

    client = entry.get("client")
    assert isinstance(client, LlamaCppClient)
    assert client.endpoint == endpoint.rstrip("/")

    # legacy_core must be a separate client (not aliasing llamacpp)
    assert "legacy_core" in router.clients
    assert isinstance(router.clients["legacy_core"], LegacyCoreClient)
