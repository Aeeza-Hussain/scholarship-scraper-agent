"""
agent.py — Phases 2, 3, and 4.

Phase 2: _organize_professors()
    Calls Gemini directly to parse raw scraped text into clean structured
    JSON per professor: { name, title, department, research_interests,
    email, profile_url }.

Phase 3: _filter_professors()
    Plain Python filter — keeps professors whose canonical title matches
    the user's selection AND whose research interests contain at least one
    of the user's keywords.

Phase 4: ADK Agent definition
    Two ADK tools (wrapping Phase 1 scrapers + Phase 2/3 pipeline):
      - find_department_page  (thin wrapper — navigation only)
      - scrape_and_process_faculty_page  (scrape + organize + filter)

    The agent decides which tool(s) to call based on what URL the user gives.
"""

from __future__ import annotations

import json
import re
from typing import Any

import google.genai as genai
from google.adk.agents import LlmAgent

from config import GEMINI_API_KEY, MODEL_NAME, agent_logger as log
from scraper import find_department_page as _raw_find, scrape_faculty_page as _raw_scrape
from email_drafter import draft_outreach_emails

# ---------------------------------------------------------------------------
# Configure the Gemini client (used directly for the organize step)
# Lazy — created on first use so importing the module doesn't require the key.
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client

# ---------------------------------------------------------------------------
# Canonical title mapping
# ---------------------------------------------------------------------------
_TITLE_CANONICAL: dict[str, str] = {
    # Professor
    "professor": "Professor",
    "prof.": "Professor",
    "prof ": "Professor",
    # Associate Professor
    "associate professor": "Associate Professor",
    "assoc. professor": "Associate Professor",
    "assoc professor": "Associate Professor",
    "associate prof": "Associate Professor",
    # Assistant Professor
    "assistant professor": "Assistant Professor",
    "asst. professor": "Assistant Professor",
    "asst professor": "Assistant Professor",
    "assistant prof": "Assistant Professor",
    # Lecturer / Instructor
    "lecturer": "Lecturer/Instructor",
    "instructor": "Lecturer/Instructor",
    "senior lecturer": "Lecturer/Instructor",
    "teaching assistant": "Lecturer/Instructor",
}

_VALID_TITLES = {"Professor", "Associate Professor", "Assistant Professor", "Lecturer/Instructor"}


def _canonicalize_title(raw: str) -> str:
    """Map messy title text to one of the four canonical titles."""
    low = raw.lower().strip()
    for fragment, canonical in _TITLE_CANONICAL.items():
        if fragment in low:
            return canonical
    # Fallback: if "professor" appears at all, assume plain Professor
    if "professor" in low:
        return "Professor"
    return raw  # unknown — return as-is and let the filter drop it


# ---------------------------------------------------------------------------
# Phase 2 — LLM organize step
# ---------------------------------------------------------------------------

_ORGANIZE_PROMPT = """\
You are a data extraction assistant. I will give you a list of raw professor
data blocks scraped from a university faculty page. Each block contains messy,
inconsistent text fields: 'name', 'title_text', 'research_text', 'email',
and 'profile_url'.

Your job: parse every block and return a JSON array where each element is:
{{
  "name": "<Full name, e.g. Dr. Ali Khan>",
  "title": "<One of: Professor | Associate Professor | Assistant Professor | Lecturer/Instructor | Unknown>",
  "research_interests": ["<topic 1>", "<topic 2>", ...],
  "email": "<email or null>",
  "profile_url": "<url or null>"
}}

Rules:
- Normalize title variants: "Asst. Prof.", "asst prof", "assistant professor" → "Assistant Professor", etc.
- Extract research interests as a short list of topic strings (2–8 words each).
- If email is not found, use null. Same for profile_url.
- Remove duplicates and clearly non-professor entries (e.g. admin staff, secretaries).
- Output ONLY the JSON array — no markdown fences, no explanation, no extra text.
- Department context: {department}

Raw data:
{raw_json}
"""


def _organize_professors(raw_professors: list[dict], department: str) -> list[dict]:
    """
    Call Gemini to parse raw professor blocks into clean structured JSON.
    Falls back to raw data if JSON parsing fails.
    """
    if not raw_professors:
        return []

    raw_json_str = json.dumps(raw_professors, ensure_ascii=False, indent=2)
    prompt = _ORGANIZE_PROMPT.format(department=department, raw_json=raw_json_str)

    log.info("[organize] Sending %d raw blocks to Gemini for organization", len(raw_professors))

    try:
        response = _get_client().models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        text = response.text.strip()

        # Strip any accidental markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        organized = json.loads(text)
        log.info("[organize] Gemini returned %d organized professor records", len(organized))

        # Canonicalize titles
        for prof in organized:
            prof["title"] = _canonicalize_title(prof.get("title", ""))

        return organized

    except (json.JSONDecodeError, Exception) as exc:
        log.error("[organize] Failed to parse Gemini response: %s", exc)
        # Graceful degradation — return raw data with minimal normalization
        return [
            {
                "name": p.get("name", "Unknown"),
                "title": "Unknown",
                "research_interests": [],
                "email": p.get("email", None),
                "profile_url": p.get("profile_url", None),
            }
            for p in raw_professors
        ]


# ---------------------------------------------------------------------------
# Phase 3 — Plain-code filter
# ---------------------------------------------------------------------------

def _filter_professors(
    professors: list[dict],
    titles: list[str],
    research_keywords: list[str],
) -> list[dict]:
    """
    Keep only professors whose title is in the requested list AND whose
    research interests contain at least one of the research keywords.

    Args:
        professors: Organized professor dicts from _organize_professors.
        titles: List of canonical title strings the user wants, e.g.
                ['Assistant Professor', 'Associate Professor'].
        research_keywords: List of keyword strings, e.g. ['machine learning', 'NLP'].
                           Matching is case-insensitive substring match.
    Returns:
        Filtered list.
    """
    title_set = {t.strip().lower() for t in titles}
    kw_set = [kw.strip().lower() for kw in research_keywords]

    filtered = []
    for prof in professors:
        # Title check — use substring match so "Assistant Professor of CS"
        # still matches the canonical "assistant professor" filter token.
        if title_set:
            prof_title = prof.get("title", "").lower()
            # First try exact match (canonical title already normalized)
            if prof_title not in title_set:
                # Fallback: substring — any requested title token found in the prof title
                if not any(req_title in prof_title for req_title in title_set):
                    continue

        # Research keyword check
        if kw_set:
            interests_text = " ".join(prof.get("research_interests", [])).lower()
            if not any(kw in interests_text for kw in kw_set):
                continue

        filtered.append(prof)

    log.info(
        "[filter] %d/%d professors matched (titles=%s, keywords=%s)",
        len(filtered),
        len(professors),
        titles,
        research_keywords,
    )
    return filtered


def _format_professor_list(professors: list[dict], department: str) -> str:
    """Format the filtered list as a human-readable string for the agent to present."""
    if not professors:
        return (
            f"No professors found matching your criteria in the {department} department. "
            "Try broadening your search — use fewer keywords, different title types, "
            "or check that the department URL is the direct faculty listing page."
        )

    lines = [f"Here are {len(professors)} professor(s) I found matching your criteria:\n"]
    for i, p in enumerate(professors, 1):
        interests = ", ".join(p.get("research_interests", [])) or "Not listed"
        email = p.get("email") or "Not listed"
        profile = p.get("profile_url") or "Not listed"
        lines.append(
            f"{i}. **{p['name']}** — {p['title']}\n"
            f"   🔬 Research: {interests}\n"
            f"   📧 Email: {email}\n"
            f"   🔗 Profile: {profile}\n"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ADK Tool wrappers (what the LLM sees)
# ---------------------------------------------------------------------------

def find_department_page(university_url: str, department: str) -> dict[str, Any]:
    """
    Navigate a university website to locate the faculty listing page for
    a specific department. Call this tool ONLY when the user has provided
    a general university homepage URL and NOT a direct department page URL.

    Args:
        university_url: The general university homepage URL, e.g. 'https://www.kiu.edu.pk'.
        department: The name of the department, e.g. 'Computer Science'.

    Returns:
        A dict with:
          - status: 'success' or 'error'
          - department_url: the discovered faculty page URL (when status is 'success')
          - message: error description (when status is 'error')
    """
    log.info("[ADK tool] find_department_page called: url=%s dept=%s", university_url, department)
    result = _raw_find(university_url, department)
    log.info("[ADK tool] find_department_page result: %s", result)
    return result


def scrape_and_process_faculty_page(
    url: str,
    department: str,
    titles: list[str],
    research_keywords: list[str],
) -> dict[str, Any]:
    """
    Scrape a faculty listing page, organize the raw data into clean professor
    profiles, filter by the user's desired titles and research keywords, and
    return a human-readable summary of matching professors.

    Call this tool once you have the direct URL to the department faculty page
    (either given by the user or found via find_department_page).

    Args:
        url: Direct URL to the department faculty/people listing page.
        department: Department name, e.g. 'Computer Science'.
        titles: List of academic titles the user wants, e.g.
                ['Assistant Professor', 'Associate Professor'].
                Valid values: 'Professor', 'Associate Professor',
                'Assistant Professor', 'Lecturer/Instructor'.
                Pass an empty list to include all titles.
        research_keywords: List of research interest keywords to filter by,
                           e.g. ['machine learning', 'NLP'].
                           Pass an empty list to include all research areas.

    Returns:
        A dict with:
          - status: 'success' or 'error'
          - summary: human-readable string of matching professors (on success)
          - count: number of matching professors (on success)
          - message: error description (on error)
    """
    log.info(
        "[ADK tool] scrape_and_process called: url=%s dept=%s titles=%s kw=%s",
        url, department, titles, research_keywords,
    )

    # Step 1: Scrape raw data
    scrape_result = _raw_scrape(url, department)
    if scrape_result["status"] == "error":
        log.error("[ADK tool] Scrape failed: %s", scrape_result.get("message"))
        return scrape_result

    raw_professors = scrape_result["raw_professors"]
    log.info("[ADK tool] Scraped %d raw professor blocks", len(raw_professors))

    # Step 2: LLM organize
    organized = _organize_professors(raw_professors, department)
    log.info("[ADK tool] Organized into %d professor records", len(organized))

    # Step 3: Filter
    filtered = _filter_professors(organized, titles, research_keywords)

    # Step 4: Format for the agent to present
    summary = _format_professor_list(filtered, department)

    return {
        "status": "success",
        "summary": summary,
        "count": len(filtered),
    }


# ---------------------------------------------------------------------------
# Phase 4 — ADK Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a scholarship outreach assistant. Your ONLY job is to help users find
university professors by scraping faculty pages, and to draft personalized
scholarship inquiry emails to those professors.

## STRICT SCOPE — NON-NEGOTIABLE
You are purpose-built for ONE task: university faculty scraping and scholarship
email drafting. You MUST NOT help with anything outside this scope.

If the user asks about ANYTHING else — navigation, hospitals, weather, general
knowledge, coding help, translation, personal advice, or ANY other topic —
respond with this exact refusal (translated to the user's language if needed):

  "I'm a scholarship outreach assistant and can only help you find university
   professors and draft scholarship emails. Please ask me about a university
   faculty page or a research area you'd like to target."

Do NOT attempt to answer off-topic questions even partially. Do NOT apologize
at length. One sentence refusal, then redirect.

This rule overrides everything else. No exceptions.

## Conversation flow

1. **Greet** the user warmly on the first message.
2. **Collect** these four inputs (ask for any that are missing):
   - University URL -- could be a general homepage (e.g. https://www.kiu.edu.pk)
     OR a direct department faculty page URL. Tell the user either works.
   - Department name (e.g. Computer Science, Electrical Engineering)
   - Research interest keyword(s) (e.g. machine learning, NLP, robotics)
   - Desired academic title(s): Professor / Associate Professor /
     Assistant Professor / Lecturer-Instructor (user can pick one or more)

3. **Decide which tool(s) to call:**
   - If the user gave a direct department/faculty page URL -> call
     `scrape_and_process_faculty_page` immediately.
   - If the user gave only a general university homepage -> call
     `find_department_page` first to locate the faculty page, then call
     `scrape_and_process_faculty_page` with the discovered URL.
   - If both URLs were given -> use the department URL directly.

4. **Present results** in clear, numbered, conversational format (not raw JSON).
   Use the formatted summary returned by `scrape_and_process_faculty_page`.

5. **Offer email drafts** after presenting results:
   - Ask the user if they would like personalized outreach email drafts.
   - If yes, collect (in ONE message if any are missing):
     * Student full name
     * Degree level (PhD / MS / Master's / undergraduate / postdoc)
     * A brief research background (2-4 sentences about their experience)
   - Then call `draft_outreach_emails` with the professor list and student details.
   - Present the formatted email drafts returned by the tool.
   - Remind the user to personalize before sending and attach their CV.

6. **Handle failures gracefully:**
   - If a tool returns an error, explain it in plain language and suggest
     providing the direct department page URL.
   - If no professors matched, say so and suggest broadening the search
     (fewer keywords, more title types, or checking the URL).

7. **Stay helpful:** After presenting results or drafts, offer to search again
   with different criteria, a different department, or generate more drafts.

## Style
- Be warm, clear, and concise. Never dump raw JSON or HTML at the user.
- Use emojis sparingly (✅ for success, 🔍 when searching, ✉️ for emails, ⚠️ for issues).
- When asking for inputs, ask for all missing ones in a single message.
"""

# The root ADK agent — created at module level (ADK requires a module-level
# agent object named root_agent for `adk web` / `adk run` discovery).
# The LlmAgent itself does not call the Gemini API at construction time,
# so this is safe to instantiate without the key being set yet.
root_agent = LlmAgent(
    name="scholarship_scraper_agent",
    model=MODEL_NAME,
    instruction=SYSTEM_PROMPT,
    tools=[find_department_page, scrape_and_process_faculty_page, draft_outreach_emails],
    description=(
        "An AI agent that finds university professors matching the user's "
        "research interests and academic title preferences for scholarship outreach, "
        "then generates personalized email drafts for each matching professor."
    ),
)
