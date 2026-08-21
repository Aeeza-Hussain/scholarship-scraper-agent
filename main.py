"""
main.py — Phase 4: Conversation loop.

Runs the ADK agent in a CLI chat loop using:
  - InMemorySessionService  (conversation history kept in RAM)
  - Runner                  (orchestrates agent ↔ LLM ↔ tools)
  - asyncio                 (ADK is async-first)

Guardrails (Phase 5):
  - MAX_TOOL_CALLS per turn: if the agent makes more tool calls than
    expected in a single turn, we warn and break out of the event loop.
  - Graceful keyboard interrupt and exit commands.

Usage:
    python main.py

Environment:
    Set GEMINI_API_KEY before running:
        $env:GEMINI_API_KEY = "your-key-here"    # PowerShell
        export GEMINI_API_KEY="your-key-here"     # bash
    Or create a .env file with: GEMINI_API_KEY=your-key-here
"""

from __future__ import annotations

import asyncio
import sys
import uuid

# Ensure UTF-8 output on Windows (avoids UnicodeEncodeError with emoji)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent
from config import GEMINI_API_KEY, MAX_TOOL_CALLS, agent_logger as log

# ---------------------------------------------------------------------------
# Validate API key early so the user gets a clear error message
# ---------------------------------------------------------------------------
if not GEMINI_API_KEY:
    print(
        "\n❌  GEMINI_API_KEY is not set.\n"
        "    Create a .env file in this directory with:\n"
        "        GEMINI_API_KEY=your-key-here\n"
        "    Or set the environment variable before running.\n"
    )
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# ADK setup
# ---------------------------------------------------------------------------
APP_NAME = "scholarship_scraper"
session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


# ---------------------------------------------------------------------------
# Core conversation function
# ---------------------------------------------------------------------------

async def run_agent_turn(user_input: str, user_id: str, session_id: str) -> str:
    """
    Send one user message to the agent and collect the final response text.
    Enforces MAX_TOOL_CALLS guardrail per turn.

    Returns the agent's final reply as a string.
    """
    content = types.Content(
        role="user",
        parts=[types.Part(text=user_input)],
    )

    tool_call_count = 0
    final_response = ""

    log.info("[turn] user_id=%s  session_id=%s  input=%r", user_id, session_id, user_input[:120])

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        # Count tool calls for the guardrail
        if hasattr(event, "tool_call") and event.tool_call:
            tool_call_count += 1
            log.info(
                "[guardrail] Tool call #%d in this turn: %s",
                tool_call_count,
                getattr(event.tool_call, "name", "unknown"),
            )
            if tool_call_count > MAX_TOOL_CALLS:
                log.warning(
                    "[guardrail] MAX_TOOL_CALLS (%d) exceeded — breaking out of event loop",
                    MAX_TOOL_CALLS,
                )
                final_response = (
                    "⚠️ I seem to be going in circles trying to fetch that page. "
                    "Could you try providing the direct faculty listing URL instead?"
                )
                break

        # Capture the final text response
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response = event.content.parts[0].text or ""
                log.info("[turn] Final response collected (%d chars)", len(final_response))

    return final_response.strip()


# ---------------------------------------------------------------------------
# Main conversation loop
# ---------------------------------------------------------------------------

async def main() -> None:
    user_id = "user_" + uuid.uuid4().hex[:8]
    session_id = "session_" + uuid.uuid4().hex[:8]

    # Create the session
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    log.info("Session started: user_id=%s  session_id=%s", user_id, session_id)

    print("\n" + "=" * 60)
    print("  🎓  Scholarship Professor Finder  ")
    print("=" * 60)
    print("  Type 'exit' or 'quit' to end the session.")
    print("=" * 60 + "\n")

    # Kick off the conversation with a greeting trigger
    opening = await run_agent_turn("hi", user_id, session_id)
    print(f"Agent: {opening}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSession ended. Goodbye! 👋")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye", "goodbye"}:
            print("\nAgent: Thanks for using the scholarship scraper! Good luck with your outreach. 🎓\n")
            break

        print("\n🔍 Searching...\n")

        try:
            response = await run_agent_turn(user_input, user_id, session_id)
        except Exception as exc:
            log.error("[main] Unexpected error during agent turn: %s", exc, exc_info=True)
            response = (
                "⚠️ Something went wrong on my end. Please try again, "
                "or check the logs/ directory for details."
            )

        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
