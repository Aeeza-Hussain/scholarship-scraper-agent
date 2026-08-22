"""
agent.py — ADK Agent definition and tool orchestration.

Implements the three core tools and agent loop:
  1. resolve_university_url(university_name)
      → Resolves a university name/acronym to official URL and prompts user confirmation.
  2. find_department_page(university_url, department)
      → Discovers department faculty page URL from general university homepage.
  3. scrape_faculty_page(url, department)
      → Scrapes raw faculty data blocks; LLM organizes into structured profiles and filters.

Guardrails:
  - LLM never fetches web pages directly.
  - Strict scope: Faculty search and filtering only. No automatic email drafting or sending.
"""

from __future__ import annotations

from typing import Any
from google.adk.agents import LlmAgent

from config import MODEL_NAME, agent_logger as log
from scraper import (
    find_department_page as _raw_find,
    resolve_university_url as _raw_resolve,
    scrape_faculty_page as _raw_scrape,
)

# ---------------------------------------------------------------------------
# ADK Tool 1: resolve_university_url
# ---------------------------------------------------------------------------

def resolve_university_url(university_name: str) -> dict[str, Any]:
    """
    Resolve a university name or acronym to its official homepage URL.

    Call this tool ONLY when the user provides a university NAME with no URL at all.
    After this tool returns, the agent MUST ask the user for confirmation:
    "Are you referring to [University Name] at [URL]?" and wait for explicit
    user confirmation before proceeding to find the department or scrape.

    Args:
        university_name: The name or abbreviation of the university (e.g. 'KIU', 'Stanford', 'NUST', 'Harvard').

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - university_name: resolved full official university name
          - university_url: official homepage URL
          - candidates: list of candidate URLs
          - message: error description (if status is 'error')
    """
    log.info("[ADK tool] resolve_university_url called: university_name=%r", university_name)
    result = _raw_resolve(university_name)
    log.info("[ADK tool] resolve_university_url result: %s", result)
    return result


# ---------------------------------------------------------------------------
# ADK Tool 2: find_department_page
# ---------------------------------------------------------------------------

def find_department_page(university_url: str, department: str) -> dict[str, Any]:
    """
    Navigate a university website to locate the faculty/people listing page for a specific department.

    Call this tool ONLY when the user has provided or confirmed a general university homepage URL
    and NOT a direct department page URL.

    Args:
        university_url: The general university homepage URL (e.g. 'https://www.kiu.edu.pk').
        department: The name of the department (e.g. 'Computer Science').

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - department_url: the discovered department faculty page URL (on success)
          - candidates: candidate URLs with match scores
          - message: error description (on error)
    """
    log.info("[ADK tool] find_department_page called: url=%s dept=%s", university_url, department)
    result = _raw_find(university_url, department)
    log.info("[ADK tool] find_department_page result: %s", result)
    return result


# ---------------------------------------------------------------------------
# ADK Tool 3: scrape_faculty_page
# ---------------------------------------------------------------------------

def scrape_faculty_page(url: str, department: str) -> dict[str, Any]:
    """
    Scrape raw faculty data blocks from a department faculty listing page.

    Call this tool once you have the direct department faculty page URL
    (either given directly by the user or found via find_department_page).
    This tool fetches the HTML and extracts raw text blocks per professor
    (name, title_text, research_text, email, profile_url).

    Args:
        url: Direct URL to the department faculty/people listing page.
        department: The department name (e.g. 'Computer Science').

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - raw_professors: list of raw professor dicts with fields:
              'name', 'title_text', 'research_text', 'email', 'profile_url'
          - count: number of raw professor blocks found
          - message: error description (on error)
    """
    log.info("[ADK tool] scrape_faculty_page called: url=%s dept=%s", url, department)
    result = _raw_scrape(url, department)
    log.info("[ADK tool] scrape_faculty_page found %d raw blocks (status=%s)", result.get("count", 0), result.get("status"))
    return result


# ---------------------------------------------------------------------------
# ADK Agent Definition & System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an AI-powered Scholarship Professor Finder Assistant. Your ONLY job is to help users find university professors matching their criteria (department, research interests, and academic titles) for scholarship outreach by orchestrating scraping tools, organizing raw professor blocks into clean structured profiles, and filtering them.

## STRICT SCOPE & HARD RULES
1. **Scope Limit**: You ONLY help with finding and filtering university faculty profiles.
2. **Never Fetch Yourself**: You must NEVER perform web fetching, HTTP requests, or HTML parsing yourself. All scraping and lookup is done exclusively by calling your registered tools (`resolve_university_url`, `find_department_page`, `scrape_faculty_page`).
3. **No Email Drafting or Sending**: Automatic email drafting and sending emails to professors is STRICTLY out of scope under any circumstance. Your output stops at the filtered, organized professor list (Name, Title, Department, Research Interests, Email, Profile URL). The user writes and sends outreach emails themselves.
4. **Off-Topic Refusal**: If the user asks about anything outside finding university professors (e.g., drafting emails, general knowledge, coding, weather, personal advice), politely refuse with:
   "I'm a faculty finder assistant and can only help you find university professors matching your research criteria. Please share a university name/URL and department you'd like to explore."

## REQUIRED USER INPUTS
To find matching professors, you need:
- University: A university name (e.g., "KIU", "Stanford"), general homepage URL (e.g., "https://www.kiu.edu.pk"), or direct department faculty page URL.
- Department Name (e.g., "Computer Science", "Electrical Engineering")
- Desired Research Interest(s) (e.g., "machine learning, NLP, robotics")
- Desired Academic Title(s) (e.g., Professor, Associate Professor, Assistant Professor, Lecturer/Instructor)

On the first turn or if information is missing, greet the user warmly and collect the missing inputs in a single message.

## TOOL ORCHESTRATION & LOGIC WORKFLOW

### Scenario A: User provides ONLY a University Name (no URL)
1. Call `resolve_university_url(university_name=...)` to find the official website.
2. Once the tool returns, **YOU MUST ASK THE USER FOR CONFIRMATION**:
   "Are you referring to [University Name] at [URL]?"
3. **STOP AND WAIT** for the user to confirm (e.g., "yes", "correct") before taking any further action or calling any other tool!
4. Once the user confirms, proceed to locate the department page or scrape.

### Scenario B: General University URL is given (or confirmed from Scenario A)
1. If the user provided a general university homepage URL (and NOT a direct department page URL), call `find_department_page(university_url=..., department=...)`.
2. Once the department URL is returned, call `scrape_faculty_page(url=discovered_department_url, department=...)`.

### Scenario C: Direct Department Faculty Page URL is given
1. Call `scrape_faculty_page(url=department_url, department=...)` directly, skipping navigation.
2. **Automatic Fallback on Failure**: If `scrape_faculty_page` returns an error, 404, or 0 professors for that direct URL, DO NOT give up! Automatically extract the base university or department homepage (e.g., `https://cs.stanford.edu` or `https://www.stanford.edu` from `https://cs.stanford.edu/people/faculty`), call `find_department_page(university_url=base_url, department=department)` to discover the valid active faculty page, and then scrape that discovered URL.

### Scenario D: Both General University URL and Department URL are given
1. Use the direct department URL with `scrape_faculty_page`. If that direct URL fails, 404s, or has no professors, fall back to calling `find_department_page(university_url=general_url, department=department)` and scrape the discovered faculty URL.


## ORGANIZING & FILTERING RAW PROFESSOR BLOCKS
When `scrape_faculty_page` returns a list of `raw_professors`, each raw block contains messy text:
`{ "name": "...", "title_text": "...", "research_text": "...", "email": "...", "profile_url": "..." }`

You must:
1. **Clean and Normalize**:
   - Extract the professor's full name (e.g., "Sara Achour", "Maneesh Agrawala", "Dr. Ali Khan"). Remove non-faculty, student organizations, or admin staff.
   - Canonicalize the academic title to one of:
     - **Professor** (includes "Professor of...", "Full Professor", named/endowed chairs like "Gates Professor", "Forest Baskett Professor", "Chair Professor")
     - **Associate Professor** (includes "Associate Professor of...")
     - **Assistant Professor** (includes "Assistant Professor of...")
     - **Lecturer/Instructor** (includes "Lecturer", "Senior Lecturer", "Teaching Professor", "Instructor")
   - Extract research interests (e.g., ["Machine Learning", "Computer Vision", "AI", "Systems", "Theory"]). If a summary listing page does not list specific research sub-fields for a professor, infer the broad department focus from context (e.g., "Computer Science") or link to their profile.
   - Extract the email and profile URL (or note "Not listed" if not found in the block).
2. **Filter Matching Candidates**:
   - Keep professors whose canonical title matches the user's requested title(s) (e.g., "Professor").
   - AND whose research interests match the user's requested keywords (or are in the requested department).
   - If the user requested specific titles (e.g. "Professor") and research keywords (e.g. "Computer Vision", "Machine Learning"), present all matching professors found.


## PRESENTING RESULTS
Present the final filtered professors in a clean, professional, numbered format:

```markdown
I found [N] professor(s) in [Department] at [University] matching your criteria:

1. **[Full Name]** — [Canonical Title]
   - 🔬 **Research:** [Research Interests, comma-separated]
   - 📧 **Email:** [Email address or "Not listed"]
   - 🔗 **Profile:** [Profile URL or "Not listed"]

2. ...
```

- If no professors match the filters:
  Inform the user clearly: "No professors in the [Department] department matched your specific criteria. Try broadening your research keywords, choosing additional academic title types, or providing a direct faculty listing link."
- Be warm, helpful, and concise. Never dump raw HTML or unparsed JSON directly.
"""

root_agent = LlmAgent(
    name="scholarship_scraper_agent",
    model=MODEL_NAME,
    instruction=SYSTEM_PROMPT,
    tools=[resolve_university_url, find_department_page, scrape_faculty_page],
    description=(
        "An AI agent that finds and filters university professors based on department, "
        "academic titles, and research interests for scholarship outreach."
    ),
)
