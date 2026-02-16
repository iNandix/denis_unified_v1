import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from denis_unified_v1.delivery import PipecatRenderer

async def test():
    renderer = PipecatRenderer()
    delta = {"text": "Hola mundo", "timing": {}, "is_final": True}
    result = await renderer.render_delta(delta)
    print("Test result:", result)

if __name__ == "__main__":
    asyncio.run(test())