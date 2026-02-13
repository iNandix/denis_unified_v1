#!/usr/bin/env python3
"""Test model discovery with real API keys"""

import asyncio
import os
import sys
from pathlib import Path

# Setup paths
base_dir = Path("/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

# Load .env
env_file = Path("/media/jotah/SSD_denis/.env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v.strip('"').strip("'"))

# Import provider_loader directly using importlib
import importlib.util

spec = importlib.util.spec_from_file_location(
    "provider_loader", str(base_dir / "inference" / "provider_loader.py")
)
provider_loader = importlib.util.module_from_spec(spec)

# Need to also load dependencies
# This is getting complex, let's try a simpler approach: execute test within the project


async def test():
    print("\n" + "=" * 60)
    print("MODEL DISCOVERY TEST")
    print("=" * 60)

    try:
        # We need to import from the parent directory to avoid __init__.py
        # Add denis_unified_v1 to path
        denis_dir = Path("/media/jotah/SSD_denis")
        if str(denis_dir) not in sys.path:
            sys.path.insert(0, str(denis_dir))

        # Now we should be able to import if we fix the imports in router.py
        # But router.py has issues. Let's test provider_loader alone by importing it directly

        spec = importlib.util.spec_from_file_location(
            "provider_loader_module", str(base_dir / "inference" / "provider_loader.py")
        )
        provider_loader_module = importlib.util.module_from_spec(spec)
        # We need to provide a fake __name__ and __loader__ to satisfy dataclass
        provider_loader_module.__name__ = "provider_loader_module"
        provider_loader_module.__loader__ = spec.loader
        spec.loader.exec_module(provider_loader_module)

        discover_provider_models = provider_loader_module.discover_provider_models

        # Test Groq
        print("\n1. Testing GROQ models...")
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            total, models = discover_provider_models("groq", groq_key)
            print(f"   Found {len(models)}/{total} models")
            free_models = [m for m in models if m.is_free]
            print(f"   Free models: {len(free_models)}")
            for m in free_models[:3]:
                print(f"     - {m.model_id}: {m.model_name}")
        else:
            print("   ❌ GROQ_API_KEY not set")

        # Test OpenRouter
        print("\n2. Testing OPENROUTER models...")
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if or_key:
            total, models = discover_provider_models("openrouter", or_key)
            print(f"   Found {len(models)}/{total} models")
            free_models = [m for m in models if m.is_free]
            print(f"   Free models: {len(free_models)}")
            for m in free_models[:3]:
                print(f"     - {m.model_id}: {m.model_name}")
        else:
            print("   ❌ OPENROUTER_API_KEY not set")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
