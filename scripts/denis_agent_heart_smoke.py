#!/usr/bin/env python3
"""
DENIS Agent Heart Smoke Test
============================

Tests the core DENIS Agent Heart contract with minimal dependencies.
Tests both sync and async execution with various task types.
"""

import sys
import os
import json
import time
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from denis_agent_heart import DenisAgentHeart, run_task, run_task_async
    IMPORT_SUCCESS = True
except ImportError as e:
    IMPORT_SUCCESS = False
    IMPORT_ERROR = str(e)


def test_sync_run():
    """Test synchronous run method."""
    if not IMPORT_SUCCESS:
        return {
            "test": "sync_run",
            "success": False,
            "error": f"Import failed: {IMPORT_ERROR}",
            "duration_ms": 0
        }

    start_time = time.time()

    try:
        heart = DenisAgentHeart()

        # Test valid task
        task = {
            "type": "code_generation",
            "payload": {
                "language": "python",
                "description": "Generate a hello world function"
            },
            "context": {"user": "test_user"}
        }

        result = heart.run(task)
        duration = (time.time() - start_time) * 1000

        # Validate result structure
        required_fields = ["status", "agent_id", "task_type", "timestamp"]
        has_required_fields = all(field in result for field in required_fields)

        return {
            "test": "sync_run",
            "success": result.get("status") == "success" and has_required_fields,
            "result_status": result.get("status"),
            "has_required_fields": has_required_fields,
            "duration_ms": duration,
            "result_keys": list(result.keys())
        }

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        return {
            "test": "sync_run",
            "success": False,
            "error": str(e),
            "duration_ms": duration
        }


async def test_async_run():
    """Test asynchronous run method."""
    if not IMPORT_SUCCESS:
        return {
            "test": "async_run",
            "success": False,
            "error": f"Import failed: {IMPORT_ERROR}",
            "duration_ms": 0
        }

    start_time = time.time()

    try:
        import asyncio
        heart = DenisAgentHeart()

        # Test valid task
        task = {
            "type": "analysis",
            "payload": {
                "data": [1, 2, 3, 4, 5],
                "analysis_type": "statistical"
            }
        }

        result = await heart.run_async(task)
        duration = (time.time() - start_time) * 1000

        # Validate result structure
        required_fields = ["status", "agent_id", "task_type", "timestamp", "async_execution"]
        has_required_fields = all(field in result for field in required_fields)

        return {
            "test": "async_run",
            "success": result.get("status") == "success" and has_required_fields and result.get("async_execution"),
            "result_status": result.get("status"),
            "has_required_fields": has_required_fields,
            "async_indicator": result.get("async_execution"),
            "duration_ms": duration,
            "result_keys": list(result.keys())
        }

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        return {
            "test": "async_run",
            "success": False,
            "error": str(e),
            "duration_ms": duration
        }


def test_fail_open_behavior():
    """Test fail-open behavior with invalid inputs."""
    if not IMPORT_SUCCESS:
        return {
            "test": "fail_open",
            "success": False,
            "error": f"Import failed: {IMPORT_ERROR}",
            "duration_ms": 0
        }

    start_time = time.time()

    try:
        heart = DenisAgentHeart()

        # Test with None input
        result1 = heart.run(None)
        # Test with invalid task type
        result2 = heart.run("invalid_string")
        # Test with empty dict
        result3 = heart.run({})

        duration = (time.time() - start_time) * 1000

        # All should return valid dict structures (fail-open)
        all_valid = all(
            isinstance(r, dict) and "status" in r and "agent_id" in r and "timestamp" in r
            for r in [result1, result2, result3]
        )

        return {
            "test": "fail_open",
            "success": all_valid,
            "none_input_result": result1.get("status"),
            "string_input_result": result2.get("status"),
            "empty_dict_result": result3.get("status"),
            "duration_ms": duration
        }

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        return {
            "test": "fail_open",
            "success": False,
            "error": str(e),
            "duration_ms": duration
        }


def test_plugin_gating():
    """Test that plugins are properly gated with NOOP fallbacks."""
    if not IMPORT_SUCCESS:
        return {
            "test": "plugin_gating",
            "success": False,
            "error": f"Import failed: {IMPORT_ERROR}",
            "duration_ms": 0
        }

    start_time = time.time()

    try:
        heart = DenisAgentHeart()

        # Check that all plugins are disabled by default
        status = heart.get_status()
        plugins = status.get("plugins", {})

        all_disabled = all(not config.get("enabled", True) for config in plugins.values())

        # Test plugin enablement (should work even if plugin init fails)
        enable_result = heart.enable_plugin("fastapi")
        # Note: enable_plugin returns bool, but plugin should remain disabled if init fails

        duration = (time.time() - start_time) * 1000

        return {
            "test": "plugin_gating",
            "success": all_disabled,  # Success if all plugins are disabled by default
            "plugins_disabled_by_default": all_disabled,
            "total_plugins": len(plugins),
            "plugin_names": list(plugins.keys()),
            "fastapi_enable_attempt": enable_result,
            "duration_ms": duration
        }

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        return {
            "test": "plugin_gating",
            "success": False,
            "error": str(e),
            "duration_ms": duration
        }


def test_convenience_functions():
    """Test convenience functions run_task and run_task_async."""
    if not IMPORT_SUCCESS:
        return {
            "test": "convenience_functions",
            "success": False,
            "error": f"Import failed: {IMPORT_ERROR}",
            "duration_ms": 0
        }

    start_time = time.time()

    try:
        # Test sync convenience function
        task = {"type": "generic", "payload": {"test": True}}
        sync_result = run_task(task)

        # Test async convenience function
        async_result = None
        try:
            import asyncio
            async_result = asyncio.run(run_task_async(task))
        except ImportError:
            # Async not available, skip async test
            pass

        duration = (time.time() - start_time) * 1000

        sync_valid = (isinstance(sync_result, dict) and
                     sync_result.get("status") == "success" and
                     "agent_id" in sync_result)

        async_valid = (async_result is None or
                      (isinstance(async_result, dict) and
                       async_result.get("status") == "success" and
                       async_result.get("async_execution")))

        return {
            "test": "convenience_functions",
            "success": sync_valid and async_valid,
            "sync_function_works": sync_valid,
            "async_function_available": async_result is not None,
            "async_function_works": async_valid if async_result else None,
            "duration_ms": duration
        }

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        return {
            "test": "convenience_functions",
            "success": False,
            "error": str(e),
            "duration_ms": duration
        }


def run_all_tests():
    """Run all smoke tests."""
    print("🚀 Running DENIS Agent Heart Smoke Tests...")

    results = []

    # Run sync tests
    sync_tests = [test_sync_run, test_fail_open_behavior, test_plugin_gating, test_convenience_functions]

    for test_func in sync_tests:
        print(f"Running {test_func.__name__}...")
        result = test_func()
        results.append(result)
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"  {status}")

    # Run async test separately
    print("Running test_async_run...")
    try:
        import asyncio
        async_result = asyncio.run(test_async_run())
        results.append(async_result)
        status = "✅ PASS" if async_result["success"] else "❌ FAIL"
        print(f"  {status}")
    except ImportError:
        # Async not available
        async_result = {
            "test": "async_run",
            "success": False,
            "error": "asyncio not available",
            "duration_ms": 0
        }
        results.append(async_result)
        print("  ⚠️  SKIP (asyncio not available)")
    except Exception as e:
        # Async test failed
        async_result = {
            "test": "async_run",
            "success": False,
            "error": str(e),
            "duration_ms": 0
        }
        results.append(async_result)
        print(f"  ❌ FAIL (Exception: {e})")

    # Calculate overall results
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["success"])
    failed_tests = total_tests - passed_tests
    overall_success = failed_tests == 0

    # Create artifact
    artifact = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "component": "denis_agent_heart",
        "version": "1.0.0",
        "import_success": IMPORT_SUCCESS,
        "tests_run": total_tests,
        "tests_passed": passed_tests,
        "tests_failed": failed_tests,
        "overall_success": overall_success,
        "test_results": results,
        "system_info": {
            "python_version": sys.version,
            "platform": sys.platform,
            "working_directory": os.getcwd()
        }
    }

    # Ensure artifacts directory exists
    artifacts_dir = Path("artifacts/denis_agent_heart")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Write artifact
    artifact_file = artifacts_dir / "denis_agent_heart_smoke.json"
    with open(artifact_file, 'w', encoding='utf-8') as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Artifact written to: {artifact_file}")
    print("\n📊 Results Summary:")
    print(f"   Tests Run: {total_tests}")
    print(f"   Tests Passed: {passed_tests}")
    print(f"   Tests Failed: {failed_tests}")
    print(f"   Overall Status: {'✅ PASS' if overall_success else '❌ FAIL'}")

    if not overall_success:
        print("\n❌ Failed Tests:")
        for result in results:
            if not result["success"]:
                print(f"   - {result['test']}: {result.get('error', 'Unknown error')}")

    return overall_success


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
