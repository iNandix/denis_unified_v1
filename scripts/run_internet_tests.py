#!/usr/bin/env python3
"""Standalone test runner for internet gate tests."""

import subprocess
import sys

TESTS = {
    "test_offline": """
import denis_unified_v1.kernel.internet_health as ih_module
ih_module.get_internet_health = lambda: type('H', (), {'check': lambda s: 'DOWN'})()

from denis_unified_v1.kernel.scheduler import ModelScheduler, InferenceRequest
from denis_unified_v1.kernel.engine_registry import get_engine_registry, reset_registry
reset_registry()

scheduler = ModelScheduler()
plan = scheduler.assign(InferenceRequest(
    request_id='test', session_id='test', route_type='fast_talk',
    task_type='chat', payload={'max_tokens': 512}
))

assert plan.trace_tags.get('internet_status_at_plan') == 'DOWN', f"Got {plan.trace_tags}"
boosters = [e for e in plan.fallback_engine_ids if 'groq' in e]
assert len(boosters) == 0, f"Boosters in fallbacks: {boosters}"
print("OK")
""",
    "test_online": """
import denis_unified_v1.kernel.internet_health as ih_module
ih_module.get_internet_health = lambda: type('H', (), {'check': lambda s: 'OK'})()

from denis_unified_v1.kernel.scheduler import ModelScheduler, InferenceRequest
from denis_unified_v1.kernel.engine_registry import get_engine_registry, reset_registry
reset_registry()

scheduler = ModelScheduler()
plan = scheduler.assign(InferenceRequest(
    request_id='test', session_id='test', route_type='fast_talk',
    task_type='chat', payload={'max_tokens': 512}
))

assert plan.primary_engine_id.startswith('llamacpp_')
boosters = [e for e in plan.fallback_engine_ids if 'groq' in e]
assert len(boosters) > 0, f"No boosters in fallbacks: {plan.fallback_engine_ids}"
print("OK")
""",
}


def run_test(name, code):
    """Run a test in a fresh Python process."""
    print(f"Running {name}...", end=" ")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd="/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
        env={**subprocess.os.environ, "PYTHONPATH": "."},
    )
    if result.returncode == 0 and "OK" in result.stdout:
        print("✅ PASSED")
        return True
    else:
        print(f"❌ FAILED")
        if result.stderr:
            print(f"   stderr: {result.stderr[:200]}")
        if result.stdout:
            print(f"   stdout: {result.stdout[:200]}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Internet Gate Tests")
    print("=" * 50)

    results = {}
    for name, code in TESTS.items():
        results[name] = run_test(name, code)

    print()
    if all(results.values()):
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
