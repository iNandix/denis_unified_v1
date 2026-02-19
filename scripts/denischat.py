#!/usr/bin/env python3
"""DenisChat — CLI for testing conversation loop."""

import sys
import os

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from denisunifiedv1.runtime.conversationloop import chat


def main():
    print("Denis Chat CLI")
    print("=" * 40)
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

        turn = chat(user_text)

        print(
            f"\nDenis [{turn.model} | {turn.intent} | {turn.tokens_used}tok | {turn.latency_ms:.0f}ms]:"
        )
        print(f"  {turn.response}\n")


if __name__ == "__main__":
    main()
