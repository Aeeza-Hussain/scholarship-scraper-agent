"""
config.py — Shared configuration for the scholarship scraper agent.

Set your Gemini API key before running:
  Windows PowerShell:  $env:GEMINI_API_KEY = "your-key-here"
  .env file (recommended): create a .env file with GEMINI_API_KEY=your-key-here
"""

import os
import logging
import pathlib
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env if present (graceful — no error if file doesn't exist)
# ---------------------------------------------------------------------------
_ENV_FILE = pathlib.Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE)

# ---------------------------------------------------------------------------
# Gemini / ADK
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME: str = "gemini-3.5-flash-lite"

# ---------------------------------------------------------------------------
# Scraping limits
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT: int = 15        # seconds per HTTP request
MAX_PROFESSORS: int = 50         # cap raw scraped results before sending to LLM
MAX_TOOL_CALLS: int = 10         # max tool-call events per conversation turn
MAX_PROFILE_FETCHES: int = 20    # cap individual profile page fetches per search
PROFILE_FETCH_DELAY: float = 0.3 # seconds delay between profile page requests


# ---------------------------------------------------------------------------
# Playwright fallback threshold
# Visible text shorter than this (chars) → page is probably JS-rendered
# ---------------------------------------------------------------------------
MIN_CONTENT_LENGTH: int = 500

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = pathlib.Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8"),
        logging.StreamHandler(),          # also print to console
    ],
)

# Per-module loggers (import from here for consistency)
scraper_logger = logging.getLogger("scraper")
agent_logger = logging.getLogger("agent")
