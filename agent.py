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

import pathlib
import sys
from typing import Any

# Ensure project root directory is on sys.path so config and scraper modules are always importable
_root_dir = str(pathlib.Path(__file__).resolve().parent)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

# Ensure UTF-8 output streams on Windows
if sys.stdout and getattr(sys.stdout, "encoding", None) and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and getattr(sys.stderr, "encoding", None) and sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Patch ADK AgentLoader to transparently accept both hyphenated and underscored app names in Web UI
try:
    import google.adk.cli.utils.agent_loader as _al
    if hasattr(_al, "AgentLoader") and not getattr(_al.AgentLoader, "_alias_patched", False):
        _orig_val = _al.AgentLoader._validate_agent_name
        def _patched_validate(self, agent_name: str):
            if self._is_single_agent and agent_name.replace("-", "_") == self._single_agent_name:
                return
            return _orig_val(self, agent_name)
        _al.AgentLoader._validate_agent_name = _patched_validate

        _orig_load_agent = _al.AgentLoader.load_agent
        def _patched_load_agent(self, agent_name: str):
            try:
                return _orig_load_agent(self, agent_name)
            except Exception:
                return _orig_load_agent(self, agent_name.replace("-", "_"))
        _al.AgentLoader.load_agent = _patched_load_agent
        _al.AgentLoader._alias_patched = True
except Exception:
    pass

import re
import sys
from typing import Any

from google.adk.agents import LlmAgent

from config import MODEL_NAME, agent_logger as log
from scraper import (
    find_department_page as _raw_find,
    resolve_university_url as _raw_resolve,
    scrape_faculty_page as _raw_scrape,
)

# ---------------------------------------------------------------------------
# Code-Level Guard & State Tracker
# ---------------------------------------------------------------------------

def _get_active_user_text_from_stack() -> str | None:
    """Extract active user message text from the call stack if available."""
    try:
        frame = sys._getframe()
        while frame:
            locals_dict = frame.f_locals
            if "new_message" in locals_dict:
                msg = locals_dict["new_message"]
                if hasattr(msg, "parts") and msg.parts and hasattr(msg.parts[0], "text"):
                    return msg.parts[0].text
                if isinstance(msg, str):
                    return msg
            for key in ("user_input", "message_text", "message"):
                if key in locals_dict and isinstance(locals_dict[key], str) and locals_dict[key].strip():
                    return locals_dict[key]
            frame = frame.f_back
    except Exception:
        pass
    return None


class UserCriteriaGuard:
    """
    Code-level guard that tracks which of the 4 required fields have been
    explicitly provided by the user in this conversation:
      1. University Name/URL (confirmed if resolved from name)
      2. Department Name
      3. Research Interest(s) (or explicit statement from user wanting all research areas)
      4. Desired Academic Title(s) (or explicit statement from user wanting all titles)

    Blocks find_department_page / scrape_faculty_page from executing if any required field is missing.
    """

    def __init__(self):
        self.university_name: str | None = None
        self.university_url: str | None = None
        self.university_confirmed: bool = False
        self.department: str | None = None
        self.research_interests: str | None = None
        self.academic_titles: str | None = None
        self.user_provided_fields: set[str] = set()

    def reset(self):
        self.university_name = None
        self.university_url = None
        self.university_confirmed = False
        self.department = None
        self.research_interests = None
        self.academic_titles = None
        self.user_provided_fields.clear()

    def update_from_text(self, text: str):
        if not text or not text.strip():
            return

        text_clean = text.strip()
        text_lower = text_clean.lower()

        # 1. Direct URL check
        url_match = re.search(r"https?://[^\s]+", text_clean)
        if url_match:
            self.university_url = url_match.group(0)
            self.university_confirmed = True
            self.user_provided_fields.add("university")
            self.user_provided_fields.add("university_confirmed")

        # 2. Check for university confirmation if university is set/resolved but pending confirmation
        if (self.university_name or self.university_url) and "university_confirmed" not in self.user_provided_fields:
            confirm_words = {"yes", "y", "yep", "yeah", "correct", "sure", "confirm", "right", "ok", "okay", "that's right"}
            words = set(re.findall(r"\b\w+\b", text_lower))
            if words.intersection(confirm_words):
                self.university_confirmed = True
                self.user_provided_fields.add("university_confirmed")

        # 3. Explicit "all" or "any" statements for research or academic titles
        if any(phrase in text_lower for phrase in ["all research", "any research", "all topics", "all areas", "any topic", "no preference", "all research interests"]):
            self.research_interests = "All research areas"
            self.user_provided_fields.add("research_interests")

        if any(phrase in text_lower for phrase in ["all titles", "any title", "all faculty", "all professors", "any academic title", "all academic titles"]):
            self.academic_titles = "All academic titles"
            self.user_provided_fields.add("academic_titles")

        # 4. Explicit key-value formatted patterns e.g. "Department: CS, Research: ML, Titles: All"
        dept_match = re.search(r"(?:department|dept):\s*([^,\.\n]+)", text_clean, re.IGNORECASE)
        if dept_match:
            self.department = dept_match.group(1).strip()
            self.user_provided_fields.add("department")

        res_match = re.search(r"(?:research|interests|topics):\s*([^,\.\n]+)", text_clean, re.IGNORECASE)
        if res_match:
            self.research_interests = res_match.group(1).strip()
            self.user_provided_fields.add("research_interests")

        title_match = re.search(r"(?:title|titles|academic titles):\s*([^,\.\n]+)", text_clean, re.IGNORECASE)
        if title_match:
            self.academic_titles = title_match.group(1).strip()
            self.user_provided_fields.add("academic_titles")

        # 5. Position/Comma separated inputs
        parts = [p.strip() for p in text_clean.split(",") if p.strip()]
        clean_parts = [p for p in parts if p.lower() not in {"yes", "y", "yep", "yeah", "correct", "sure", "ok", "okay"}]

        if clean_parts:
            idx = 0
            if "university" not in self.user_provided_fields and not url_match:
                self.university_name = clean_parts[0]
                self.user_provided_fields.add("university")
                idx += 1

            if idx < len(clean_parts) and "department" not in self.user_provided_fields:
                val = clean_parts[idx]
                if not self.university_name or val.lower() != self.university_name.lower():
                    self.department = val
                    self.user_provided_fields.add("department")
                    idx += 1

            if idx < len(clean_parts) and "research_interests" not in self.user_provided_fields:
                val = clean_parts[idx]
                if val.lower() in {"all", "any", "all topics", "all areas"}:
                    self.research_interests = "All research areas"
                else:
                    self.research_interests = val
                self.user_provided_fields.add("research_interests")
                idx += 1

            if idx < len(clean_parts) and "academic_titles" not in self.user_provided_fields:
                val = clean_parts[idx]
                if val.lower() in {"all", "any", "all titles", "all faculty"}:
                    self.academic_titles = "All academic titles"
                else:
                    self.academic_titles = val
                self.user_provided_fields.add("academic_titles")
                idx += 1

    def is_fully_ready(self) -> tuple[bool, list[str]]:
        missing = []
        if "university" not in self.user_provided_fields and not self.university_url and not self.university_name:
            missing.append("University Name / URL")
        if "university_confirmed" not in self.user_provided_fields and not self.university_confirmed:
            missing.append("University Confirmation (User must confirm the homepage URL)")
        if "department" not in self.user_provided_fields or not self.department:
            missing.append("Department Name")
        if "research_interests" not in self.user_provided_fields or not self.research_interests:
            missing.append("Research Interest(s) (or explicit statement from user wanting all research areas)")
        if "academic_titles" not in self.user_provided_fields or not self.academic_titles:
            missing.append("Desired Academic Title(s) (or explicit statement from user wanting all titles)")

        ready = len(missing) == 0
        return ready, missing


GLOBAL_GUARD = UserCriteriaGuard()

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
        A dict with resolved homepage info and confirmation instruction.
    """
    log.info("[ADK tool] resolve_university_url called: university_name=%r", university_name)
    user_text = _get_active_user_text_from_stack()
    if user_text:
        GLOBAL_GUARD.update_from_text(user_text)

    GLOBAL_GUARD.university_name = university_name
    GLOBAL_GUARD.user_provided_fields.add("university")

    result = _raw_resolve(university_name)
    if result.get("status") == "success" and result.get("university_url"):
        GLOBAL_GUARD.university_url = result.get("university_url")

    log.info("[ADK tool] resolve_university_url result: %s", result)
    return result


# ---------------------------------------------------------------------------
# ADK Tool 2: find_department_page
# ---------------------------------------------------------------------------

def find_department_page(university_url: str, department: str) -> dict[str, Any]:
    """
    Navigate a university website to locate the faculty listing page for a specific department.

    Call this tool ONLY when the user has provided or confirmed a general university homepage URL,
    AND provided a department name, research interests, and academic titles.
    """
    log.info("[ADK tool] find_department_page called: url=%s dept=%s", university_url, department)
    user_text = _get_active_user_text_from_stack()
    if user_text:
        GLOBAL_GUARD.update_from_text(user_text)

    # Check code guard
    ready, missing = GLOBAL_GUARD.is_fully_ready()
    if not ready:
        log.warning("[GUARD BLOCKED find_department_page] Missing fields: %s", missing)
        return {
            "status": "error",
            "error_code": "MISSING_REQUIRED_USER_INPUTS",
            "missing_fields": missing,
            "message": (
                "BLOCKED BY CODE GUARD: You CANNOT call find_department_page or scrape_faculty_page yet. "
                f"The following required pieces of information have NOT been explicitly provided by the user in this conversation: {', '.join(missing)}. "
                "Confirming the university homepage ONLY confirms the university homepage — it is NOT permission to proceed with scraping. "
                "You MUST ask the user to explicitly provide the missing piece(s) next before taking any further action!"
            ),
        }

    result = _raw_find(university_url, department)
    log.info("[ADK tool] find_department_page result: %s", result)
    return result


# ---------------------------------------------------------------------------
# ADK Tool 3: scrape_faculty_page
# ---------------------------------------------------------------------------

def scrape_faculty_page(
    url: str, department: str, desired_titles: str = ""
) -> dict[str, Any]:
    """
    Scrape raw faculty data blocks from a department faculty listing page.

    Call this tool once you have the direct department faculty page URL
    AND the user has explicitly provided department, research interests, and academic titles.
    """
    log.info(
        "[ADK tool] scrape_faculty_page called: url=%s dept=%s desired_titles=%r",
        url,
        department,
        desired_titles,
    )
    user_text = _get_active_user_text_from_stack()
    if user_text:
        GLOBAL_GUARD.update_from_text(user_text)

    # Check code guard
    ready, missing = GLOBAL_GUARD.is_fully_ready()
    if not ready:
        log.warning("[GUARD BLOCKED scrape_faculty_page] Missing fields: %s", missing)
        return {
            "status": "error",
            "error_code": "MISSING_REQUIRED_USER_INPUTS",
            "missing_fields": missing,
            "message": (
                "BLOCKED BY CODE GUARD: You CANNOT call scrape_faculty_page yet. "
                f"The following required pieces of information have NOT been explicitly provided by the user in this conversation: {', '.join(missing)}. "
                "Confirming the university homepage ONLY confirms the university homepage — it is NOT permission to proceed with scraping. "
                "You MUST ask the user to explicitly provide the missing piece(s) next before taking any further action!"
            ),
        }

    result = _raw_scrape(url, department, desired_titles=desired_titles)
    log.info(
        "[ADK tool] scrape_faculty_page found %d raw blocks (status=%s)",
        result.get("count", 0),
        result.get("status"),
    )
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

## CRITICAL MANDATE: ALL 4 REQUIRED USER INPUTS
Before calling `find_department_page` or `scrape_faculty_page`, you MUST have received ALL FOUR of the following inputs explicitly provided by the user in this conversation:
1. **University Name / URL** (confirmed homepage URL if resolved from a name)
2. **Department Name** (e.g., "Computer Science", "Electrical Engineering") — REQUIRED!
3. **Research Interest(s)** — explicit research topics OR an explicit statement from the user that they want all research areas (DO NOT default or guess this on your own!)
4. **Desired Academic Title(s)** — e.g. "Assistant Professor", "Professor", OR an explicit statement from the user that they want all titles (DO NOT default or guess this on your own!)

### HARD WORKFLOW RULES
1. **University Confirmation is ONLY University Confirmation**:
   Confirming the university homepage (e.g. user saying "yes", "correct", "sure") MUST be treated as ONLY confirming the university homepage. It does NOT grant permission to proceed with searching or scraping if department, research interests, or titles are missing!
2. **Never Guess or Default Missing Criteria**:
   You MUST NEVER invent, guess, or default missing department names, research interests, or academic titles.
3. **Explicit Prompting for Missing Fields**:
   If the university is confirmed but any of (Department Name, Research Interests, Academic Titles) are still missing, you MUST ask the user for the missing piece(s) in your very next message before taking any further action.
4. **Code Guard Enforcement**:
   The tools `find_department_page` and `scrape_faculty_page` are protected by a code-level guard. If you call them before the user explicitly provides all 4 required inputs, the tools will return a guard block error. Always follow tool error instructions.

## TOOL ORCHESTRATION & LOGIC WORKFLOW

### Step 1: University Resolution & Confirmation
- If user gives a University Name (e.g., "NUST", "KIU"):
  1. Call `resolve_university_url(university_name=...)`.
  2. Ask user: "Are you referring to [University Name] at [URL]?"
  3. STOP AND WAIT for explicit confirmation ("yes", "correct").
  4. If user confirms "yes" AND you do not have Department Name, Research Interests, and Academic Titles yet:
     Ask the user to explicitly provide the missing items next! DO NOT call `find_department_page` or `scrape_faculty_page` yet.

### Step 2: Department Discovery & Faculty Scraping (ONLY executed when ALL 4 inputs are provided)
- **Scenario A: General Homepage URL + Department Name**:
  1. Call `find_department_page(university_url=..., department=...)`.
  2. Call `scrape_faculty_page(url=discovered_department_url, department=..., desired_titles=...)`.

- **Scenario B: Direct Department Faculty Page URL**:
  1. Call `scrape_faculty_page(url=department_url, department=..., desired_titles=...)` directly.
  2. Fallback: If direct URL fails/404s/0 profs, extract base university URL, call `find_department_page`, and scrape discovered URL.


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
   - Extract research interests (e.g., ["Machine Learning", "Computer Vision", "AI", "Systems", "Theory"]).
   - Extract the email and profile URL (or note "Not listed" if not found in the block).
2. **Filter Matching Candidates**:
   - Keep professors whose canonical title matches the user's requested title(s) (e.g., "Professor").
   - If the user specified research keywords (e.g. "Machine Learning", "Computer Vision"): keep only professors whose `research_text` contains matching keywords (case-insensitive).
   - If a professor has no profile_url and no research-interest text found anywhere: include them with `Research: Not listed — see profile` UNLESS the user gave a specific research keyword (in which case only include if actual matching text is found).
   - If the user did not specify title or keyword restrictions, include all faculty found.


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

