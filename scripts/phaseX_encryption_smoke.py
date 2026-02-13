#!/usr/bin/env python3
"""
Phase X - Encryption Smoke Test
===============================

Tests encryption router with DATA_ENCRYPTION_KEY derivation and fail-open behavior.
Self-hosted server test that validates encryption functionality when key is available.
"""

import json
import os
import subprocess
import sys
import time
import socket

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def _http_get(base_url: str, path: str, params: dict = None, timeout: float = 2.0) -> dict:
    """Make HTTP GET request."""
    try:
        import requests
        url = f"{base_url}{path}"
        if params:
            import urllib.parse
            query = urllib.parse.urlencode(params)
            url += f"?{query}"

        resp = requests.get(url, timeout=timeout)
        return {
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "data": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        }
    except Exception as e:
        return {"error": str(e), "status_code": None}

def _http_post(base_url: str, path: str, data: dict = None, timeout: float = 2.0) -> dict:
    """Make HTTP POST request."""
    try:
        import requests
        url = f"{base_url}{path}"
        resp = requests.post(url, json=data, timeout=timeout)
        return {
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "data": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        }
    except Exception as e:
        return {"error": str(e), "status_code": None}

def wait_for_server(base_url: str, timeout_sec: int = 15) -> bool:
    """Wait for server to be ready."""
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        try:
            result = _http_get(base_url, "/health")
            if result.get("status_code") == 200:
                return True
        except:
            pass
        time.sleep(0.5)
    return False

def main():
    """Run encryption smoke test."""
    print("Running Phase X - Encryption Smoke Test...")

    # Check if cryptography is available
    try:
        import cryptography
        crypto_available = True
    except ImportError:
        crypto_available = False
        print("⚠️  cryptography not available - encryption will be skipped")

    # Check if DATA_ENCRYPTION_KEY is set
    encryption_key_set = os.getenv("DATA_ENCRYPTION_KEY") is not None
    if encryption_key_set:
        print("✅ DATA_ENCRYPTION_KEY is set")
    else:
        print("⚠️  DATA_ENCRYPTION_KEY not set - encryption will be skipped")

    artifact = {
        "timestamp_utc": _utc_now(),
        "stream": "S12_encryption",
        "cryptography_available": crypto_available,
        "encryption_key_set": encryption_key_set,
        "results": {}
    }

    # Start server
    port = _free_port()
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.fastapi_server:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]

    server = subprocess.Popen(cmd, cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        base_url = f"http://127.0.0.1:{port}"

        # Wait for server to start
        if not wait_for_server(base_url, timeout_sec=15):
            artifact["results"]["server_start"] = {"status": "failed", "error": "Server failed to start"}
            artifact["ok"] = False
        else:
            print("✅ Server started successfully")
            artifact["results"]["server_start"] = {"status": "success"}

            # Test encryption status
            print("Testing /encryption/status...")
            status_result = _http_get(base_url, "/encryption/status")

            if status_result.get("status_code") == 200:
                status_data = status_result.get("data", {})
                print(f"Status response: {status_data.get('available', 'unknown')}")

                if not encryption_key_set:
                    # Should return skippeddependency
                    expected_status = "skippeddependency"
                    actual_status = status_data.get("status")
                    if actual_status == expected_status:
                        artifact["results"]["status_no_key"] = {"status": "passed", "reason": "Correctly returned skippeddependency"}
                    else:
                        artifact["results"]["status_no_key"] = {"status": "failed", "expected": expected_status, "got": actual_status}
                else:
                    # Should return available: true
                    if status_data.get("available") is True:
                        artifact["results"]["status_with_key"] = {"status": "passed", "key_derivation": status_data.get("key_derivation")}
                    else:
                        artifact["results"]["status_with_key"] = {"status": "failed", "data": status_data}

                # Test encryption functionality if key is available
                if encryption_key_set and crypto_available:
                    print("Testing encryption functionality...")

                    # Test enable
                    enable_result = _http_post(base_url, "/encryption/enable", {"user_id": "test_user"})
                    if enable_result.get("status_code") == 200:
                        enable_data = enable_result.get("data", {})
                        if enable_data.get("enabled") is True:
                            artifact["results"]["enable"] = {"status": "passed", "user_id": enable_data.get("user_id")}
                        else:
                            artifact["results"]["enable"] = {"status": "failed", "data": enable_data}
                    else:
                        artifact["results"]["enable"] = {"status": "failed", "status_code": enable_result.get("status_code")}

                    # Test full encryption cycle
                    test_message = "Hello, encrypted world!"
                    encrypt_result = _http_post(base_url, "/encryption/encrypt", {
                        "user_id": "test_user",
                        "data": test_message
                    })

                    if encrypt_result.get("status_code") == 200:
                        encrypt_data = encrypt_result.get("data", {})
                        if encrypt_data.get("encrypted") is True:
                            encrypted_data = encrypt_data.get("data")

                            # Test decryption
                            decrypt_result = _http_post(base_url, "/encryption/decrypt", {
                                "user_id": "test_user",
                                "encrypted_data": encrypted_data
                            })

                            if decrypt_result.get("status_code") == 200:
                                decrypt_data = decrypt_result.get("data", {})
                                if decrypt_data.get("decrypted") is True:
                                    decrypted_message = decrypt_data.get("data")
                                    if decrypted_message == test_message:
                                        artifact["results"]["encryption_cycle"] = {
                                            "status": "passed",
                                            "original": test_message,
                                            "encrypted_length": len(encrypted_data),
                                            "decrypted": decrypted_message,
                                            "roundtrip_success": True
                                        }
                                    else:
                                        artifact["results"]["encryption_cycle"] = {
                                            "status": "failed",
                                            "reason": "Decrypted message doesn't match original",
                                            "original": test_message,
                                            "decrypted": decrypted_message
                                        }
                                else:
                                    artifact["results"]["encryption_cycle"] = {"status": "failed", "stage": "decrypt", "data": decrypt_data}
                            else:
                                artifact["results"]["encryption_cycle"] = {"status": "failed", "stage": "decrypt_request", "status_code": decrypt_result.get("status_code")}
                        else:
                            artifact["results"]["encryption_cycle"] = {"status": "failed", "stage": "encrypt", "data": encrypt_data}
                    else:
                        artifact["results"]["encryption_cycle"] = {"status": "failed", "stage": "encrypt_request", "status_code": encrypt_result.get("status_code")}

                    # Test /encryption/test endpoint
                    test_result = _http_get(base_url, "/encryption/test", {"user_id": "test_user"})
                    if test_result.get("status_code") == 200:
                        test_data = test_result.get("data", {})
                        if test_data.get("test") == "passed":
                            artifact["results"]["test_endpoint"] = {"status": "passed", "roundtrip_success": test_data.get("roundtrip_success")}
                        else:
                            artifact["results"]["test_endpoint"] = {"status": "failed", "data": test_data}
                    else:
                        artifact["results"]["test_endpoint"] = {"status": "failed", "status_code": test_result.get("status_code")}
                else:
                    # Skip encryption tests
                    artifact["results"]["encryption_tests"] = {"status": "skipped", "reason": "encryption key not set or cryptography not available"}
            else:
                artifact["results"]["status_endpoint"] = {"status": "failed", "status_code": status_result.get("status_code")}

        # Determine overall success
        all_results = artifact["results"]
        failed_tests = [k for k, v in all_results.items() if isinstance(v, dict) and v.get("status") == "failed"]
        skipped_tests = [k for k, v in all_results.items() if isinstance(v, dict) and v.get("status") == "skipped"]

        if failed_tests:
            artifact["ok"] = False
            artifact["summary"] = f"Failed tests: {failed_tests}"
        elif encryption_key_set and crypto_available:
            # If key is set and crypto is available, all tests should pass
            passed_tests = [k for k, v in all_results.items() if isinstance(v, dict) and v.get("status") == "passed"]
            artifact["ok"] = len(passed_tests) > 0
            artifact["summary"] = f"Passed: {passed_tests}, Skipped: {skipped_tests}"
        else:
            # If key is not set or crypto not available, success is returning proper skippeddependency
            artifact["ok"] = True
            artifact["summary"] = f"Skipped tests (as expected): {skipped_tests}"

    except Exception as e:
        artifact["ok"] = False
        artifact["error"] = str(e)
        artifact["summary"] = "Unexpected error during test execution"
    finally:
        # Clean up server
        try:
            server.terminate()
            server.wait(timeout=5)
        except Exception:
            try:
                server.kill()
            except Exception:
                pass

    # Write artifact
    os.makedirs("artifacts/api", exist_ok=True)
    with open("artifacts/api/phaseX_encryption_smoke.json", "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    status = "PASSED" if artifact.get("ok", False) else "FAILED/SKIPPED"
    print(f"Smoke {status}")
    print(f"Summary: {artifact.get('summary', 'No summary')}")

    return 0 if artifact.get("ok", False) else 1

if __name__ == "__main__":
    sys.exit(main())
