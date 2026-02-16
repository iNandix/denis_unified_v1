#!/usr/bin/env python3
"""
Denis Code CLI - Natural language programming assistant.

Usage:
    denis-code "edit src/app.py to add logging"
    denis-code "run tests for auth module"
    denis-code "refactor user service to use async"
    denis-code --repl
"""

import argparse
import asyncio
import logging
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional

from denis_unified_v1.actions.cli_trace import (
    cli_trace_session_start,
    cli_trace_engine,
    cli_trace_tool,
    cli_trace_plan,
    cli_trace_research,
    cli_trace_session_end,
    quick_trace,
)
from denis_unified_v1.actions.engine_registry import select_engine_for_intent
from denis_unified_v1.actions.tool_approval import check_tool_approval
from denis_unified_v1.actions.tool_registry import get_tool_definition
from denis_unified_v1.actions.planner import generate_candidate_plans
from denis_unified_v1.actions.models import Intent_v1

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("denis-code")


class DenisCodeCLI:
    """Denis Code CLI - Natural language programming assistant."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or cli_trace_session_start()
        self.history = []

    def analyze_intent(self, command: str) -> str:
        """Analyze command to determine intent."""
        command_lower = command.lower()

        if any(
            kw in command_lower
            for kw in ["edit", "modify", "change", "update", "add", "remove"]
        ):
            return "code_edit"
        elif any(kw in command_lower for kw in ["test", "spec"]):
            return "run_tests"
        elif any(
            kw in command_lower for kw in ["refactor", "restructure", "reorganize"]
        ):
            return "refactor_code"
        elif any(
            kw in command_lower for kw in ["debug", "fix", "solve", "error", "bug"]
        ):
            return "debug_code"
        elif any(
            kw in command_lower
            for kw in ["explain", "what does", "how does", "document"]
        ):
            return "explain_code"
        elif any(kw in command_lower for kw in ["search", "find", "grep", "look for"]):
            return "search_code"
        elif any(kw in command_lower for kw in ["create", "new", "scaffold"]):
            return "create_file"
        elif any(kw in command_lower for kw in ["review", "audit", "check"]):
            return "code_review"
        else:
            return "general_task"

    def determine_task_heaviness(self, intent: str) -> bool:
        """Determine if task requires heavy engine."""
        heavy_intents = {
            "code_edit",
            "refactor_code",
            "debug_code",
            "create_file",
            "code_review",
        }
        return intent in heavy_intents

    async def execute_command(self, command: str) -> dict:
        """Execute a natural language command."""
        logger.info(f"Executing: {command}")

        # Analyze intent
        intent = self.analyze_intent(command)
        is_heavy = self.determine_task_heaviness(intent)

        # Trace plan selection
        cli_trace_plan(
            intent=intent,
            candidate_id=f"cli_{intent}",
            mode="SELECTED",
        )

        # Select engine
        engine_name = cli_trace_engine(
            intent=intent,
            task_heavy=is_heavy,
        )

        if not engine_name:
            return {"status": "error", "message": "No engine available"}

        logger.info(f"Using engine: {engine_name} for intent: {intent}")

        # Simulate execution (in real implementation, this would call the LLM)
        result = {
            "status": "success",
            "intent": intent,
            "engine": engine_name,
            "command": command,
            "message": f"Would {intent} using {engine_name}",
        }

        self.history.append(
            {
                "command": command,
                "intent": intent,
                "engine": engine_name,
                "result": result,
            }
        )

        return result

    def repl(self):
        """Start REPL mode."""
        print("Denis Code REPL (type 'exit' to quit)")
        print("Examples: 'edit src/app.py', 'run tests', 'explain this function'")
        print()

        while True:
            try:
                command = input("denis-code> ").strip()

                if not command:
                    continue

                if command in ["exit", "quit", "q"]:
                    break

                if command == "history":
                    for i, h in enumerate(self.history):
                        print(f"  {i + 1}. {h['command']} -> {h['intent']}")
                    continue

                if command == "help":
                    print("Commands:")
                    print("  edit <file> <description>  - Edit a file")
                    print("  run tests                  - Run tests")
                    print("  refactor <file>            - Refactor code")
                    print("  debug <file>               - Debug issues")
                    print("  explain <code>             - Explain code")
                    print("  search <pattern>           - Search code")
                    print("  history                    - Show command history")
                    print("  exit                       - Exit REPL")
                    continue

                # Execute command
                result = asyncio.run(self.execute_command(command))
                print(f"→ {result['message']}")
                print()

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                print(f"Error: {e}")

        # End session
        summary = cli_trace_session_end()
        print(f"Session ended: {summary['total_turns']} commands executed")

    def run(self, command: str):
        """Run a single command."""
        result = asyncio.run(self.execute_command(command))

        # End session
        summary = cli_trace_session_end()

        if result["status"] == "success":
            print(f"✓ {result['message']}")
            return 0
        else:
            print(f"✗ {result.get('message', 'Unknown error')}")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="Denis Code - Natural language programming assistant"
    )
    parser.add_argument(
        "command",
        nargs="?",
        help="Command to execute",
    )
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Start REPL mode",
    )
    parser.add_argument(
        "--session-id",
        help="Session ID for tracing",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize CLI
    cli = DenisCodeCLI(session_id=args.session_id)

    if args.repl:
        cli.repl()
    elif args.command:
        sys.exit(cli.run(args.command))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
