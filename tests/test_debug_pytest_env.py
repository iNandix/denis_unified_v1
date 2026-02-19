def test_debug_pytest_env():
    import os
    import sys

    # Basic visibility when debugging CI hangs.
    print("sys.argv[0]=", sys.argv[0])
    print("sys.path[:6]=", sys.path[:6])
    print("argv_contains_pytest=", any("pytest" in (a or "") for a in sys.argv))
    print("pytest_in_sys_modules=", "pytest" in sys.modules)
    print("sitecustomize_in_sys_modules=", "sitecustomize" in sys.modules)
    if "sitecustomize" in sys.modules:
        print("sitecustomize.__file__=", getattr(sys.modules["sitecustomize"], "__file__", None))
    print("DISABLE_OBSERVABILITY=", os.getenv("DISABLE_OBSERVABILITY"))

    import api.fastapi_server as s

    print("fastapi_server.DISABLE_OBSERVABILITY=", os.getenv("DISABLE_OBSERVABILITY"))
    print("tracing_setup_done=", s.tracing_setup_done)
    print("metrics_setup_done=", s.metrics_setup_done)

    # Reproduce the PR1 test flow minimally.
    os.environ["ENV"] = "test"
    os.environ["DENIS_CONTRACT_TEST_MODE"] = "1"
    app = s.create_app()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/health")
    print("/health status=", r.status_code, r.json().get("status"))

    assert True
