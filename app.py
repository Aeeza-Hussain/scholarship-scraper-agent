"""
app.py — FastAPI HTTP API layer for the ADK Scholarship Scraper Agent.

Exposes REST endpoints for web frontends to interact conversationally with the agent:
  - GET  /health   → Service health & active LLM model info
  - POST /session  → Initializes a new ADK session and returns initial greeting
  - POST /chat     → Sends a user message to the session, enforces MAX_TOOL_CALLS, returns reply
"""

from __future__ import annotations

import sys
import uuid
from typing import Any

# Ensure UTF-8 standard streams on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import GLOBAL_GUARD, root_agent
from config import GEMINI_API_KEY, MAX_TOOL_CALLS, MODEL_NAME, agent_logger as log

# ---------------------------------------------------------------------------
# Validate API key early
# ---------------------------------------------------------------------------
if not GEMINI_API_KEY:
    log.error("GEMINI_API_KEY is not set. Ensure .env or environment variable is configured.")

# ---------------------------------------------------------------------------
# ADK Setup
# ---------------------------------------------------------------------------
APP_NAME = "scholarship_scraper"
session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)

# ---------------------------------------------------------------------------
# FastAPI App Initialization & CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Scholarship Scraper Agent API",
    description="REST API for the Google ADK Scholarship Professor Finder Agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response Pydantic Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    user_id: str | None = Field(default=None, description="Active user ID (auto-generated if omitted)")
    session_id: str | None = Field(default=None, description="Active session ID (auto-generated if omitted)")
    message: str = Field(..., description="Message string to send to the agent")


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    user_id: str
    tool_calls_this_turn: int


class SessionResponse(BaseModel):
    user_id: str
    session_id: str
    greeting: str


class HealthResponse(BaseModel):
    status: str
    model: str
    app_name: str


# ---------------------------------------------------------------------------
# Helper: Execute a single turn via ADK Runner
# ---------------------------------------------------------------------------
async def _execute_turn(
    message_text: str, user_id: str, session_id: str
) -> tuple[str, int]:
    """
    Feeds a user message into the ADK runner for the given session,
    enforcing MAX_TOOL_CALLS per turn. Returns (final_text_reply, total_tool_calls).
    """
    GLOBAL_GUARD.update_from_text(message_text)

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=message_text)],
    )

    log.info(
        "[turn] user_id=%s session_id=%s input=%r",
        user_id,
        session_id,
        message_text,
    )

    total_tool_calls = 0
    final_reply_chunks: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        function_calls = event.get_function_calls()
        if function_calls:
            for call in function_calls:
                total_tool_calls += 1
                log.info(
                    "[guardrail] Tool call #%d in turn: %s",
                    total_tool_calls,
                    getattr(call, "name", "unknown"),
                )

                if total_tool_calls > MAX_TOOL_CALLS:
                    log.warning(
                        "[guardrail] MAX_TOOL_CALLS (%d) exceeded in turn for session %s.",
                        MAX_TOOL_CALLS,
                        session_id,
                    )
                    return (
                        f"I have reached the maximum number of tool calls ({MAX_TOOL_CALLS}) for this turn. "
                        "Please refine your search or provide more specific criteria.",
                        total_tool_calls,
                    )

        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_reply_chunks.append(part.text)

    reply_text = "".join(final_reply_chunks).strip()
    log.info("[turn] Final response collected (%d chars)", len(reply_text))
    return reply_text, total_tool_calls


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse, include_in_schema=False)
async def health() -> dict[str, str]:
    """Health check endpoint returning service status and configured LLM model."""
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "app_name": APP_NAME,
    }


@app.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
@app.post("/api/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_session() -> dict[str, str]:
    """
    Create a fresh ADK agent session, executes the opening kickoff turn,
    and returns the session identifiers and the agent's greeting.
    """
    user_id = "user_" + uuid.uuid4().hex[:8]
    session_id = "session_" + uuid.uuid4().hex[:8]

    try:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        log.info("[session] Created session user_id=%s session_id=%s", user_id, session_id)

        # Kick off with opening greeting
        try:
            greeting, _ = await _execute_turn("hi", user_id, session_id)
        except Exception as turn_exc:
            log.warning("[session] Initial greeting turn fallback (%s)", turn_exc)
            greeting = ""

        if not greeting:
            greeting = (
                "Hello! 👋 I am your Scholarship Professor Finder Assistant. "
                "I can help you find university faculty members matching your criteria for scholarship outreach.\n\n"
                "To get started, please share:\n"
                "1. **University Name or Homepage URL** (e.g., Stanford, NUST, KIU)\n"
                "2. **Department Name** (e.g., Computer Science, Electrical Engineering)\n"
                "3. **Research Interest(s)** (e.g., Machine Learning, Quantum Computing, or specify 'All')\n"
                "4. **Desired Academic Title(s)** (e.g., Assistant Professor, Full Professor, or 'All')"
            )

        return {
            "user_id": user_id,
            "session_id": session_id,
            "greeting": greeting,
        }
    except Exception as exc:
        log.error("[session] Failed to initialize session: %s", exc, exc_info=True)
        return {
            "user_id": user_id,
            "session_id": session_id,
            "greeting": (
                "Hello! 👋 I am your Scholarship Professor Finder Assistant. "
                "I can help you find university faculty members matching your criteria for scholarship outreach.\n\n"
                "To get started, please share:\n"
                "1. **University Name or Homepage URL** (e.g., Stanford, NUST, KIU)\n"
                "2. **Department Name** (e.g., Computer Science, Electrical Engineering)\n"
                "3. **Research Interest(s)** (e.g., Machine Learning, Quantum Computing, or specify 'All')\n"
                "4. **Desired Academic Title(s)** (e.g., Assistant Professor, Full Professor, or 'All')"
            ),
        }


# ---------------------------------------------------------------------------
# Session Manager Helper
# ---------------------------------------------------------------------------
_active_user_id: str | None = None
_active_session_id: str | None = None


async def _get_or_create_session(user_id: str | None, session_id: str | None) -> tuple[str, str]:
    """
    Ensures a valid session is always available.
    If no user_id/session_id is provided, reuses the active continuous session.
    If an expired or unknown session_id is provided, automatically recreates it.
    """
    global _active_user_id, _active_session_id

    # If neither user_id nor session_id is provided, maintain continuous active session
    if not user_id or not session_id:
        if not _active_user_id or not _active_session_id:
            _active_user_id = "user_default"
            _active_session_id = "session_" + uuid.uuid4().hex[:8]
            await session_service.create_session(
                app_name=APP_NAME,
                user_id=_active_user_id,
                session_id=_active_session_id,
            )
            log.info("[session] Initialized default active session: %s", _active_session_id)
        return _active_user_id, _active_session_id

    # Client passed specific session identifiers
    try:
        existing = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if existing is None:
            await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            log.info("[session] Auto-created requested session: %s", session_id)
    except Exception:
        try:
            await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            pass

    return user_id, session_id


async def _extract_request_payload(request: Request) -> tuple[str | None, str | None, str | None]:
    """
    Universally extracts (message, user_id, session_id) from any client format:
    1. Multipart Form-data (Postman form-data)
    2. URL-encoded Form-data (x-www-form-urlencoded)
    3. Raw JSON (application/json)
    4. Plain Text Body
    5. Query Parameters
    """
    content_type = request.headers.get("content-type", "").lower()
    message: Any = None
    user_id: Any = None
    session_id: Any = None

    # 1. Inspect Content-Type Header
    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                message = body.get("message")
                user_id = body.get("user_id")
                session_id = body.get("session_id")
            elif isinstance(body, str):
                message = body
        except Exception:
            pass
    elif "multipart" in content_type or "form" in content_type:
        try:
            form = await request.form()
            message = form.get("message")
            user_id = form.get("user_id")
            session_id = form.get("session_id")
        except Exception:
            pass

    # 2. Fallback: Try Form Parsing
    if message is None:
        try:
            form = await request.form()
            if form:
                message = form.get("message")
                user_id = form.get("user_id") or user_id
                session_id = form.get("session_id") or session_id
        except Exception:
            pass

    # 3. Fallback: Try JSON Parsing
    if message is None:
        try:
            body = await request.json()
            if isinstance(body, dict):
                message = body.get("message")
                user_id = body.get("user_id") or user_id
                session_id = body.get("session_id") or session_id
            elif isinstance(body, str):
                message = body
        except Exception:
            pass

    # 4. Fallback: Try Raw Body Text Parsing
    if message is None:
        try:
            raw_bytes = await request.body()
            raw_text = raw_bytes.decode("utf-8", errors="ignore").strip()
            if raw_text:
                if raw_text.startswith("{") and raw_text.endswith("}"):
                    try:
                        parsed = json.loads(raw_text)
                        if isinstance(parsed, dict):
                            message = parsed.get("message")
                            user_id = parsed.get("user_id") or user_id
                            session_id = parsed.get("session_id") or session_id
                    except Exception:
                        pass
                elif "boundary=" not in raw_text and not raw_text.startswith("--"):
                    if "message=" in raw_text:
                        parsed_qs = urllib.parse.parse_qs(raw_text)
                        message = parsed_qs.get("message", [None])[0]
                        user_id = parsed_qs.get("user_id", [None])[0] or user_id
                        session_id = parsed_qs.get("session_id", [None])[0] or session_id
                    else:
                        message = raw_text
        except Exception:
            pass

    # 5. Fallback: Query Parameters
    if message is None:
        message = request.query_params.get("message")
        user_id = user_id or request.query_params.get("user_id")
        session_id = session_id or request.query_params.get("session_id")

    msg_str = str(message).strip() if message is not None and str(message).strip() else None
    uid_str = str(user_id).strip() if user_id is not None and str(user_id).strip() else None
    sid_str = str(session_id).strip() if session_id is not None and str(session_id).strip() else None

    return msg_str, uid_str, sid_str


@app.post("/chat", response_model=ChatResponse)
@app.post("/api/chat", response_model=ChatResponse, include_in_schema=False)
async def chat(request: Request) -> dict[str, Any]:
    """
    Send a message to the agent and receive the conversational reply.
    Universally supports Form-data (multipart & urlencoded), JSON bodies, and query params.
    Only `message` is required. Sessions are automatically managed in the background.
    """
    message_str, user_id_str, session_id_str = await _extract_request_payload(request)

    if not message_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'message' field is required in request body (JSON or Form data).",
        )

    # Automatically resolve or create session
    resolved_user_id, resolved_session_id = await _get_or_create_session(
        user_id_str, session_id_str
    )

    # Execute agent turn
    try:
        reply, tool_calls = await _execute_turn(
            message_str, resolved_user_id, resolved_session_id
        )

        if not reply:
            reply = "I have processed your request. Please let me know what else you'd like to search for."

        return {
            "reply": reply,
            "session_id": resolved_session_id,
            "user_id": resolved_user_id,
            "tool_calls_this_turn": tool_calls,
        }
    except Exception as exc:
        err_str = str(exc)
        log.error("[chat] Error during agent turn: %s", exc, exc_info=True)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            reply = (
                "⚠️ **Gemini API Quota Limit Reached (429 Rate Limit)**\n\n"
                "The free-tier daily request quota for the active Gemini model has been temporarily reached. "
                "Please wait a few moments for the rate limit window to refresh, or try again shortly."
            )
            return {
                "reply": reply,
                "session_id": resolved_session_id,
                "user_id": resolved_user_id,
                "tool_calls_this_turn": 0,
            }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {str(exc)}",
        )
