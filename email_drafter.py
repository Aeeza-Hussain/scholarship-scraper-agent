"""
email_drafter.py — Phase 5: Personalized outreach email generation.

Uses Gemini to draft a unique, personalized scholarship inquiry email for each
matched professor. Each draft is tailored to:
  - The professor's name, title, and specific research interests.
  - The student's name, degree level (PhD / MS / undergraduate), and research
    background summary.

Entry point:
    draft_outreach_emails(professors, student_name, degree_level, student_background)
        -> {"status": "success", "drafts": [...], "formatted": "<human-readable string>"}
        -> {"status": "error", "message": "..."}
"""

from __future__ import annotations

import json
import re
from typing import Any

import google.genai as genai

from config import GEMINI_API_KEY, MODEL_NAME, agent_logger as log

# ---------------------------------------------------------------------------
# Lazy Gemini client
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
_DRAFT_PROMPT = """\
You are an expert academic writing assistant helping a student apply for a
research scholarship / PhD / MS position.

## Student Profile
- Name: {student_name}
- Degree level seeking: {degree_level}
- Research background: {student_background}

## Task
Write a short, professional, and highly personalized cold-outreach email to
EACH professor in the list below. The email should:

1. Open with a warm, specific reference to the professor's actual research
   interests (use the exact topics listed -- do NOT use generic phrases like
   "your impressive research").
2. Clearly state what the student is seeking (a position / scholarship / lab
   placement for {degree_level}).
3. Briefly mention 1-2 relevant aspects of the student's background that
   align with the professor's work.
4. End with a polite, low-pressure call to action (e.g. asking for a brief
   Zoom call or whether openings exist).
5. Keep each email between 150-220 words. No attachments mentioned.
6. Use a professional subject line starting with "[Inquiry]".

Return a JSON array -- one object per professor -- with the structure:
[
  {{
    "professor_name": "<name>",
    "to_email": "<email or null>",
    "subject": "<subject line>",
    "body": "<full email body, with \\n for line breaks>"
  }},
  ...
]

Output ONLY the JSON array -- no markdown fences, no commentary.

## Professors
{professors_json}
"""


# ---------------------------------------------------------------------------
# Main tool function
# ---------------------------------------------------------------------------
def draft_outreach_emails(
    professors: list[dict],
    student_name: str,
    degree_level: str,
    student_background: str,
) -> dict[str, Any]:
    """
    Generate personalized scholarship outreach email drafts for a list of
    professors using Gemini.

    Call this tool AFTER presenting the filtered professor results and
    collecting the student's details.

    Args:
        professors: List of professor dicts with keys: name, title,
                    research_interests (list), email, profile_url.
                    These are the filtered results from scrape_and_process_faculty_page.
        student_name: The student's full name, e.g. 'Ali Khan'.
        degree_level: One of 'PhD', 'MS', "Master's", 'undergraduate', 'postdoc'.
        student_background: A brief description of the student's research
                            background and relevant skills, e.g.
                            'I have 2 years of experience in NLP, specifically
                            transformer fine-tuning and low-resource languages.
                            My thesis was on Urdu sentiment analysis.'

    Returns:
        A dict with:
          - status: 'success' or 'error'
          - drafts: list of dicts with keys professor_name, to_email,
                    subject, body (on success)
          - formatted: human-readable string with all drafts (on success)
          - count: number of drafts generated (on success)
          - message: error description (on error)
    """
    if not professors:
        return {
            "status": "error",
            "message": "No professors provided. Run the faculty search first.",
        }

    if not student_name.strip():
        return {"status": "error", "message": "student_name cannot be empty."}

    if not student_background.strip():
        return {
            "status": "error",
            "message": (
                "student_background cannot be empty -- provide a brief"
                " description of your research."
            ),
        }

    # Cap to avoid context overflow on large faculty lists
    professors_to_draft = professors[:20]
    if len(professors) > 20:
        log.warning(
            "[email_drafter] Truncated to 20 professors (received %d)",
            len(professors),
        )

    # Strip out verbose fields we don't need for drafting to keep prompt compact
    professors_json_str = json.dumps(
        [
            {
                "name": p.get("name", "Unknown"),
                "title": p.get("title", ""),
                "research_interests": p.get("research_interests", []),
                "email": p.get("email") or None,
            }
            for p in professors_to_draft
        ],
        ensure_ascii=False,
        indent=2,
    )

    prompt = _DRAFT_PROMPT.format(
        student_name=student_name,
        degree_level=degree_level,
        student_background=student_background,
        professors_json=professors_json_str,
    )

    log.info(
        "[email_drafter] Generating drafts for %d professor(s) | student=%s | level=%s",
        len(professors_to_draft),
        student_name,
        degree_level,
    )

    try:
        response = _get_client().models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        text = response.text.strip()

        # Strip accidental markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        drafts = json.loads(text)
        log.info("[email_drafter] Gemini returned %d draft(s)", len(drafts))

        formatted = _format_drafts(drafts)

        return {
            "status": "success",
            "drafts": drafts,
            "formatted": formatted,
            "count": len(drafts),
        }

    except (json.JSONDecodeError, Exception) as exc:
        log.error("[email_drafter] Failed to parse Gemini response: %s", exc)
        return {
            "status": "error",
            "message": (
                "Failed to generate email drafts. The Gemini response was"
                f" malformed or an error occurred: {exc}"
            ),
        }


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------
def _format_drafts(drafts: list[dict]) -> str:
    """Format drafts as a human-readable string for the agent to present."""
    if not drafts:
        return "No email drafts were generated."

    lines = [f"[EMAIL]  Here are {len(drafts)} personalized email draft(s):\n"]
    sep = "-" * 60

    for i, draft in enumerate(drafts, 1):
        professor_name = draft.get("professor_name", "Unknown Professor")
        to_email = draft.get("to_email") or "Email not found -- check profile"
        subject = draft.get("subject", "(no subject)")
        body = draft.get("body", "(no body)")

        lines.append(sep)
        lines.append(f"Draft {i} -- {professor_name}")
        lines.append(sep)
        lines.append(f"To:      {to_email}")
        lines.append(f"Subject: {subject}")
        lines.append("")
        lines.append(body)
        lines.append("")

    lines.append(sep)
    lines.append(
        "Tip: Review and personalize each draft before sending. Attach your CV"
        " and any relevant publication or project links."
    )

    return "\n".join(lines)
