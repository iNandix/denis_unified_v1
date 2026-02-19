#!/usr/bin/env python3
"""
Denis CLI - Interfaz de línea de comandos para Denis Persona.

Uso:
    python -m kernel.denis_cli "Denis, necesito automatizar X para un cliente"
"""

import asyncio
import sys
from kernel import get_denis_persona, get_unified_router


async def main():
    if len(sys.argv) < 2:
        print('Uso: denis_cli.py "tu mensaje a Denis"')
        sys.exit(1)

    prompt = sys.argv[1]
    session_id = "cli_session"

    print(f"\n🪞 Denis reflejándote...")
    print(f"   Tú: {prompt}\n")

    # Initialize Denis
    denis = get_denis_persona()
    await denis.initialize()

    # Use UnifiedRouter to orchestrate
    router = get_unified_router()
    decision = await router.route(prompt, session_id)

    print(f"🤖 Denis responde:")
    print(f"   Intent: {decision.intent}")
    print(f"   Engine: {decision.engine}")
    print(f"   Tools: {decision.primary_tool} + {', '.join(decision.secondary_tools)}")
    print(f"   Razonamiento: {decision.reasoning}")
    print(f"   Confianza: {decision.confidence:.0%}")

    # Show tool status
    status = router.get_tool_status()
    print(f"\n📊 Estado de tools:")
    for tool, info in status.items():
        emoji = "✅" if info.get("available") else "❌"
        print(f"   {emoji} {tool}")

    print("\n✨ Listo para trabajar contigo.")


if __name__ == "__main__":
    asyncio.run(main())
