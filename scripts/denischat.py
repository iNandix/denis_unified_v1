#!/usr/bin/env python3
"""DenisChat — CLI for testing conversation loop."""

import sys
import os

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from denis_unified_v1.runtime.conversation_loop import chat, clear_history


def main():
    print("=" * 50)
    print("  Denis Chat CLI")
    print("  Asistente de desarrollo IA")
    print("=" * 50)
    print("Comandos:")
    print("  /clear - Limpiar historial")
    print("  /help - Mostrar ayuda")
    print("  /exit - Salir")
    print()
    print("Escribe tu mensaje (exit/quit para salir)")
    print()

    while True:
        try:
            user_text = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n¡Hasta luego!")
            break

        if not user_text:
            continue

        if user_text.lower() in ("exit", "quit", "q", "salir"):
            print("¡Hasta luego!")
            break

        if user_text.startswith("/"):
            cmd = user_text.lower()
            if cmd == "/clear":
                clear_history()
                print("✓ Historial limpiado\n")
                continue
            elif cmd == "/help":
                print("Comandos: /clear, /help, /exit")
                continue
            elif cmd == "/history":
                from denis_unified_v1.runtime.conversation_loop import CONVERSATION_HISTORY

                print(f"Historial: {len(CONVERSATION_HISTORY)} mensajes")
                continue
            else:
                print(f"Comando desconocido: {user_text}")
                continue

        try:
            turn = chat(user_text)

            print()
            print(
                f"Denis [{turn.model} | {turn.intent} | {turn.tokens_used}tok | {turn.latency_ms:.0f}ms]"
            )
            print(f"  Repo: {turn.repo_name} [{turn.branch}]")
            print(f"  Session: {turn.session_id[:12]}...")
            print()
            print(f"  {turn.response}")
            print()

        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()
