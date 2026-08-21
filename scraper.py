"""
scraper.py — Phase 1: Raw scraping tool functions.

Two tools:
  find_department_page(university_url, department)
      → Navigates the university site to locate the faculty/people page
        for the given department. Called only when the user provides a
        general university URL instead of a direct department page URL.

  scrape_faculty_page(url, department)
      → Fetches the faculty listing page and extracts raw text blocks
        (name, title text, research text, email, profile URL) for every
        professor it can find. Returns messy-but-structured raw data;
        the LLM cleans it up in the next step.

Fetching strategy:
  1. Try requests + BeautifulSoup (fast, no JS overhead).
  2. If visible text is shorter than MIN_CONTENT_LENGTH characters, the
     page is probably JS-rendered → fall back to Playwright (headless
     Chromium), which must be installed separately:
         playwright install chromium
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import (
    MAX_PROFESSORS,
    MIN_CONTENT_LENGTH,
    REQUEST_TIMEOUT,
    scraper_logger as log,
)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_html(url: str) -> str:
    """Fetch page HTML via requests.  Returns empty string on error.

    Tries with SSL verification first.  If an SSL error occurs, retries once
    with verify=False before giving up (avoids unnecessary Playwright fallback
    on sites with self-signed or misconfigured certificates).
    """
    import urllib3  # bundled with requests

    for verify in (True, False):
        try:
            if not verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                log.info("Retrying %s with SSL verification disabled", url)
            resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT, verify=verify)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.SSLError as exc:
            if not verify:
                log.warning("requests SSL error (verify=False) for %s: %s", url, exc)
                return ""
            log.info("SSL error for %s — will retry without verification", url)
        except requests.RequestException as exc:
            log.warning("requests failed for %s: %s", url, exc)
            return ""
    return ""


def _fetch_html_playwright(url: str) -> str:
    """Playwright fallback for JS-heavy pages. Imports lazily so the package
    is optional for users who only scrape static sites."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        log.info("Playwright fallback triggered for %s", url)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(_HEADERS)
            page.goto(url, timeout=REQUEST_TIMEOUT * 1000)
            # Wait for network to settle (handles lazy-loaded content)
            page.wait_for_load_state("networkidle", timeout=REQUEST_TIMEOUT * 1000)
            html = page.content()
            browser.close()
            return html
    except ImportError:
        log.error(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )
        return ""
    except Exception as exc:
        log.error("Playwright failed for %s: %s", url, exc)
        return ""


def _get_html(url: str) -> str:
    """Try requests first; fall back to Playwright if content is too short."""
    html = _fetch_html(url)
    soup = BeautifulSoup(html, "lxml")
    visible_text = soup.get_text(separator=" ", strip=True)
    if len(visible_text) < MIN_CONTENT_LENGTH:
        log.info(
            "Page at %s returned only %d chars — trying Playwright fallback",
            url,
            len(visible_text),
        )
        html = _fetch_html_playwright(url)
    return html


def _normalize_url(base: str, href: str) -> str:
    """Resolve a possibly-relative href against a base URL."""
    return urllib.parse.urljoin(base, href)


# ---------------------------------------------------------------------------
# Link scoring for find_department_page
# ---------------------------------------------------------------------------

_NAV_KEYWORDS = [
    "faculty", "people", "staff", "academics", "professors",
    "researchers", "department", "members", "team", "directory",
]


def _score_link(
    href: str,
    text: str,
    department_tokens: list[str],
    university_url: str = "",
) -> int:
    """
    Score a link by how likely it is to be the department faculty page.
    Higher is better.
    """
    combined = (href + " " + text).lower()
    score = 0

    # Heavy penalty: skip the root URL itself — it's never the faculty page
    base = university_url.rstrip("/")
    if base and href.rstrip("/") == base:
        return -99

    # Department name tokens (e.g. ["computer", "science", "cs"])
    dept_hit = False
    for token in department_tokens:
        if token in combined:
            score += 3
            dept_hit = True

    # Generic navigation keywords
    nav_hit = False
    for kw in _NAV_KEYWORDS:
        if kw in combined:
            score += 1
            nav_hit = True

    # Combo bonus: link contains BOTH a department token AND a nav keyword
    if dept_hit and nav_hit:
        score += 4

    # Penalise obvious non-faculty pages
    for bad in ["login", "apply", "admission", "news", "event", "blog",
                "contact", "about", "library", "alumni", "gallery",
                "research-journal", "hostel", "fee", "transport"]:
        if bad in combined:
            score -= 3

    return score


def _tokenize_department(department: str) -> list[str]:
    """Turn 'Computer Science' → ['computer', 'science', 'cs'] etc."""
    tokens = re.findall(r"[a-z]+", department.lower())
    # Add common abbreviation heuristic (first letters)
    abbrev = "".join(t[0] for t in tokens if t)
    if len(abbrev) >= 2:
        tokens.append(abbrev)
    return tokens


# ---------------------------------------------------------------------------
# Tool 1 — find_department_page
# ---------------------------------------------------------------------------

def find_department_page(university_url: str, department: str) -> dict[str, Any]:
    """
    Locate the department faculty/people listing page from a general university URL.

    Navigates the university homepage (and one level deeper if needed) to find
    the page that lists professors for the given department. Returns the best
    matching URL or an error message.

    Args:
        university_url: The general university homepage URL
                        (e.g. 'https://www.kiu.edu.pk').
        department: The department to search for
                    (e.g. 'Computer Science').

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - department_url: the discovered faculty page URL (on success)
          - candidates: list of (url, score) tuples for debugging
          - message: error description (on error)
    """
    log.info("[find_department_page] university=%s  department=%s", university_url, department)

    dept_tokens = _tokenize_department(department)
    html = _get_html(university_url)
    if not html:
        return {"status": "error", "message": f"Could not fetch {university_url}"}

    soup = BeautifulSoup(html, "lxml")
    scored: list[tuple[int, str, str]] = []

    # Normalise the root URL for exclusion check
    _root_norm = university_url.rstrip("/")
    uni_netloc = urllib.parse.urlparse(university_url).netloc

    for tag in soup.find_all("a", href=True):
        href = _normalize_url(university_url, tag["href"])
        # Only consider same-domain links
        if urllib.parse.urlparse(href).netloc != uni_netloc:
            continue
        # Skip the root URL itself — it is never a faculty listing page
        if href.rstrip("/") == _root_norm:
            continue
        text = tag.get_text(separator=" ", strip=True)
        s = _score_link(href, text, dept_tokens, university_url)
        if s > 0:
            scored.append((s, href, text))

    if not scored:
        return {
            "status": "error",
            "message": "No relevant links found on the university homepage. "
                       "Try providing the department page URL directly.",
        }

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_url, top_text = scored[0]

    log.info("[find_department_page] Top candidate: score=%d  url=%s", top_score, top_url)
    log.info("[find_department_page] All candidates: %s", [(s, u) for s, u, _ in scored[:5]])

    # If the top score is modest, go one level deeper on the best candidate.
    # Threshold raised to 6: a score of 6 means dept token + nav keyword hit
    # without the combo bonus, which is still a reasonable candidate.
    if top_score < 6:
        log.info("[find_department_page] Score low (%d) — exploring one level deeper: %s", top_score, top_url)
        deeper_html = _get_html(top_url)
        if deeper_html:
            deeper_soup = BeautifulSoup(deeper_html, "lxml")
            deeper_root_norm = top_url.rstrip("/")
            for tag in deeper_soup.find_all("a", href=True):
                href = _normalize_url(top_url, tag["href"])
                if urllib.parse.urlparse(href).netloc != uni_netloc:
                    continue
                if href.rstrip("/") in (_root_norm, deeper_root_norm):
                    continue
                text = tag.get_text(separator=" ", strip=True)
                s = _score_link(href, text, dept_tokens, university_url)
                if s > 0:
                    scored.append((s, href, text))

            scored.sort(key=lambda x: x[0], reverse=True)
            top_score, top_url, top_text = scored[0]
            log.info("[find_department_page] After deeper search: score=%d  url=%s", top_score, top_url)

    candidates = [{"url": u, "score": s} for s, u, _ in scored[:5]]

    return {
        "status": "success",
        "department_url": top_url,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Professor block extraction helpers
# ---------------------------------------------------------------------------

def _extract_email(text: str, tag_html: str) -> str:
    """Extract email from visible text or mailto links."""
    # 1. Look for mailto in raw HTML
    mailto = re.search(r'mailto:([^\s"\'<>]+)', tag_html)
    if mailto:
        return mailto.group(1)
    # 2. Regex in visible text
    email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    if email_match:
        return email_match.group(0)
    return ""


def _extract_profile_url(block_tag, base_url: str) -> str:
    """Find the most likely profile link inside a faculty card/block."""
    for a in block_tag.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        # Skip social/mailto/anchor links
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        for kw in ["profile", "faculty", "staff", "people", "person", "bio", "member", "detail"]:
            if kw in href.lower() or kw in text:
                return _normalize_url(base_url, href)
    # Fallback: first real link in the block
    for a in block_tag.find_all("a", href=True):
        href = a["href"]
        if not href.startswith(("mailto:", "tel:", "#", "javascript:")):
            return _normalize_url(base_url, href)
    return ""


# CSS class fragments that suggest a faculty card container
_CARD_CLASS_HINTS = [
    "faculty", "people", "person", "professor", "staff", "member",
    "researcher", "instructor", "lecturer", "academic", "profile",
    "team", "directory", "card", "bio",
]


def _classes_match(tag, hints: list[str]) -> bool:
    classes = " ".join(tag.get("class", [])).lower()
    return any(h in classes for h in hints)


_JUNK_NAME_TOKENS = {
    "professor", "associate", "assistant", "lecturer", "instructor",
    "roles", "filter", "search", "sort", "title", "research", "area",
}


def _is_junk_name(name: str) -> bool:
    """Return True if the 'name' looks like a nav widget or filter bar."""
    words = set(name.lower().split())
    # If 3 or more words are canonical title/UI keywords, it's not a real name
    return len(words & _JUNK_NAME_TOKENS) >= 3


def _deduplicate_and_clean(entries: list[dict]) -> list[dict]:
    """
    Remove junk entries (nav widgets) and deduplicate by name,
    keeping the entry with the most non-empty fields.
    """
    seen: dict[str, dict] = {}
    for entry in entries:
        name = entry.get("name", "").strip()
        if not name or _is_junk_name(name):
            continue
        key = name.lower()
        if key not in seen:
            seen[key] = entry
        else:
            # Keep the richer entry (more non-empty fields)
            existing = seen[key]
            score_new = sum(1 for v in entry.values() if v)
            score_old = sum(1 for v in existing.values() if v)
            if score_new > score_old:
                seen[key] = entry
    return list(seen.values())


def _extract_raw_professors(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Heuristic extraction of professor blocks from a parsed faculty page.

    Strategy (tried in order, first that yields results wins):
      1. Look for elements whose CSS classes hint at faculty cards.
      2. Look for <article> tags containing a name-like heading.
      3. Look for <li> items inside a list whose id/class hints at a directory.
      4. Look for <tr> rows in a table where the first cell looks like a name.
      5. Last resort: extract all headings (h2/h3/h4) as names with surrounding text.
    """
    results: list[dict] = []

    # --- Strategy 1: class-hinted containers ---
    for tag_name in ["div", "article", "section", "li", "tr"]:
        matches = [t for t in soup.find_all(tag_name) if _classes_match(t, _CARD_CLASS_HINTS)]
        if len(matches) >= 5:  # require at least 5 to avoid tiny unrelated sections
            log.info("[extract] Strategy 1 matched %d <%s> elements", len(matches), tag_name)
            for m in matches:
                raw = _parse_block(m, base_url)
                if raw:
                    results.append(raw)
            if results:
                return _deduplicate_and_clean(results)[:MAX_PROFESSORS]

    # --- Strategy 2: <article> with a heading inside ---
    articles = soup.find_all("article")
    articles = [a for a in articles if a.find(re.compile(r"h[1-6]"))]
    if len(articles) >= 2:
        log.info("[extract] Strategy 2 matched %d <article> elements", len(articles))
        for a in articles:
            raw = _parse_block(a, base_url)
            if raw:
                results.append(raw)
        if results:
            return _deduplicate_and_clean(results)[:MAX_PROFESSORS]

    # --- Strategy 3: <li> inside directory-hinted lists ---
    for ul in soup.find_all(["ul", "ol"]):
        ul_class = " ".join(ul.get("class", [])).lower()
        ul_id = (ul.get("id") or "").lower()
        if any(h in ul_class + ul_id for h in _CARD_CLASS_HINTS):
            items = ul.find_all("li", recursive=False)
            if len(items) >= 2:
                log.info("[extract] Strategy 3 matched %d <li> elements in a hinted list", len(items))
                for li in items:
                    raw = _parse_block(li, base_url)
                    if raw:
                        results.append(raw)
                if results:
                    return _deduplicate_and_clean(results)[:MAX_PROFESSORS]

    # --- Strategy 4: table rows ---
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) >= 3:
            log.info("[extract] Strategy 4 trying table with %d rows", len(rows))
            for row in rows[1:]:  # skip header row
                raw = _parse_block(row, base_url)
                if raw and raw.get("name"):
                    results.append(raw)
            if len(results) >= 2:
                return results[:MAX_PROFESSORS]
            results.clear()

    # --- Strategy 5: heading-based fallback ---
    log.info("[extract] Strategy 5 (heading fallback) in use")
    for heading in soup.find_all(re.compile(r"h[2-4]")):
        name_text = heading.get_text(separator=" ", strip=True)
        if not name_text or len(name_text) > 80:
            continue
        # Grab the next sibling paragraph(s) for context
        sibling_text = ""
        sib = heading.find_next_sibling()
        for _ in range(3):
            if sib is None:
                break
            sibling_text += sib.get_text(separator=" ", strip=True) + " "
            sib = sib.find_next_sibling()

        full_text = name_text + " " + sibling_text
        results.append({
            "name": name_text,
            "title_text": "",
            "research_text": sibling_text.strip(),
            "email": _extract_email(full_text, str(heading)),
            "profile_url": _extract_profile_url(heading.parent, base_url),
        })

    return results[:MAX_PROFESSORS]


def _parse_block(tag, base_url: str) -> dict | None:
    """
    Extract name / title / research / email / profile_url from a single
    faculty card/block tag. Returns None if the block looks empty.
    """
    text = tag.get_text(separator=" ", strip=True)
    html_str = str(tag)

    if len(text) < 5:
        return None

    # Name: first heading inside the block, or first strong/b text
    name = ""
    heading = tag.find(re.compile(r"h[1-6]"))
    if heading:
        name = heading.get_text(separator=" ", strip=True)
    if not name:
        strong = tag.find(["strong", "b"])
        if strong:
            name = strong.get_text(separator=" ", strip=True)
    if not name:
        # Take the first non-empty line of the block text
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        name = lines[0] if lines else ""

    # Truncate clearly-too-long "names"
    if len(name) > 80:
        name = name[:80]

    return {
        "name": name,
        "title_text": text,          # full block text — LLM will parse title from here
        "research_text": text,       # same — LLM will extract research interests
        "email": _extract_email(text, html_str),
        "profile_url": _extract_profile_url(tag, base_url),
    }


# ---------------------------------------------------------------------------
# Tool 2 — scrape_faculty_page
# ---------------------------------------------------------------------------

def scrape_faculty_page(url: str, department: str) -> dict[str, Any]:
    """
    Scrape a faculty listing page and return raw professor data blocks.

    Fetches the page (with Playwright fallback for JS-heavy sites) and
    extracts a list of raw text blocks — one per detected professor. Each
    block contains the professor's name, raw title text, raw research text,
    email, and profile URL. The data may be messy; the LLM cleans it up.

    Args:
        url: Direct URL to the department faculty/people listing page.
        department: Name of the department (used for context/logging).

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - raw_professors: list of raw professor dicts (on success)
          - count: number of raw entries found
          - message: error description (on error)
    """
    log.info("[scrape_faculty_page] url=%s  department=%s", url, department)
    start = time.monotonic()

    html = _get_html(url)
    if not html:
        return {"status": "error", "message": f"Could not fetch page: {url}"}

    soup = BeautifulSoup(html, "lxml")

    # Remove noise: nav, footer, sidebars, scripts, styles
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    raw_profs = _extract_raw_professors(soup, url)

    elapsed = time.monotonic() - start
    log.info(
        "[scrape_faculty_page] Found %d raw professor blocks in %.2fs",
        len(raw_profs),
        elapsed,
    )

    if not raw_profs:
        return {
            "status": "error",
            "message": (
                "No professor blocks detected on the page. "
                "The page structure may be unusual. "
                "Try providing the direct faculty listing URL."
            ),
        }

    return {
        "status": "success",
        "raw_professors": raw_profs,
        "count": len(raw_profs),
    }
