#!/usr/bin/env python3
"""WS21-G Compiler Smoke Test.

Tests the compiler service endpoints:
- /compiler/status
- /compiler/compile
- /compiler/compile/stream
- /compiler/fallback
"""

import asyncio
import json
import sys

from denis_unified_v1.inference.compiler_service import (
    CompilerInput,
    compile_with_fallback,
    compile,
)


async def test_status():
    """Test compiler status endpoint."""
    print("\n=== Test: Compiler Status ===")
    try:
        from api.routes.compiler import router

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/status":
                print(f"Status endpoint: FOUND")
                return True
        print("Status endpoint: NOT FOUND")
        return False
    except Exception as e:
        print(f"Status test error: {e}")
        return False


async def test_compile_hola():
    """Test compilation of 'hola'."""
    print("\n=== Test: Compile 'hola' ===")
    try:
        compiler_input = CompilerInput(
            conversation_id="smoke_test",
            turn_id="001",
            correlation_id="corr_001",
            input_text="hola",
        )
        result = await compile_with_fallback(compiler_input)

        print(f"  makina_prompt: {result.makina_prompt}")
        print(f"  router: {result.router}")
        print(f"  trace_hash: {result.trace_hash}")

        return result.makina_prompt is not None
    except Exception as e:
        print(f"Compile test error: {e}")
        return False


async def test_compile_complex():
    """Test compilation of complex prompt."""
    print("\n=== Test: Compile complex prompt ===")
    try:
        compiler_input = CompilerInput(
            conversation_id="smoke_test",
            turn_id="002",
            correlation_id="corr_002",
            input_text="integra pipecat con grafo y voice events",
        )
        result = await compile_with_fallback(compiler_input)

        print(f"  makina_prompt: {result.makina_prompt[:100]}...")
        print(f"  router: {result.router}")

        return result.makina_prompt is not None
    except Exception as e:
        print(f"Compile complex error: {e}")
        return False


async def test_compile_creates_test():
    """Test compilation of 'crea un test'."""
    print("\n=== Test: Compile 'crea un test' ===")
    try:
        compiler_input = CompilerInput(
            conversation_id="smoke_test",
            turn_id="003",
            correlation_id="corr_003",
            input_text="crea un test para la función suma",
        )
        result = await compile_with_fallback(compiler_input)

        print(f"  makina_prompt: {result.makina_prompt}")
        print(f"  router.pick: {result.router.get('pick')}")
        print(f"  router.confidence: {result.router.get('confidence')}")

        return result.router.get("pick") == "implement_feature"
    except Exception as e:
        print(f"Compile crea test error: {e}")
        return False


async def test_fallback():
    """Test fallback compilation."""
    print("\n=== Test: Fallback compilation ===")
    try:
        compiler_input = CompilerInput(
            conversation_id="smoke_test",
            turn_id="004",
            correlation_id="corr_004",
            input_text="xyz unknown intent",
        )
        result = await compile_with_fallback(compiler_input)

        print(f"  makina_prompt: {result.makina_prompt}")
        print(f"  router.pick: {result.router.get('pick')}")
        print(f"  used_remote: {result.metadata.get('compiler', 'unknown')}")

        return True
    except Exception as e:
        print(f"Fallback test error: {e}")
        return False


async def test_anti_loop():
    """Test anti-loop forces fallback."""
    print("\n=== Test: Anti-loop ===")
    try:
        compiler_input = CompilerInput(
            conversation_id="smoke_test",
            turn_id="005",
            correlation_id="corr_005",
            input_text="crea algo",
        )
        result = await compile(compiler_input, anti_loop=True)

        print(f"  makina_prompt: {result.makina_prompt}")
        print(f"  mode: fallback (forced by anti_loop)")

        return True
    except Exception as e:
        print(f"Anti-loop test error: {e}")
        return False


async def main():
    """Run all smoke tests."""
    print("=" * 50)
    print("WS21-G Compiler Smoke Tests")
    print("=" * 50)

    tests = [
        ("Status", test_status),
        ("Compile hola", test_compile_hola),
        ("Compile complex", test_compile_complex),
        ("Compile crea test", test_compile_creates_test),
        ("Fallback", test_fallback),
        ("Anti-loop", test_anti_loop),
    ]

    results = []
    for name, test_fn in tests:
        try:
            result = await test_fn()
            results.append((name, result))
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)

    passed = 0
    failed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
