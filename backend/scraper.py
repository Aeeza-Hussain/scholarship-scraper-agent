"""
scraper.py — Raw scraping and lookup tool functions.

Three tools:
  resolve_university_url(university_name)
      → Resolves a university name/acronym to its official homepage URL.
        Called when the user provides only a university name with no URL.
        The agent must confirm this URL with the user before proceeding.

  find_department_page(university_url, department)
      → Navigates the university site to locate the faculty/people page
        for the given department. Called only when the user provides a
        general university URL instead of a direct department page URL.

  scrape_faculty_page(url, department)
      → Fetches the faculty listing page and extracts raw text blocks
        (name, title text, research text, email, profile URL) for every
        professor it can find. Returns raw unstructured text blocks;
        the LLM organizes and filters the data.

Fetching strategy:
  1. Try requests + BeautifulSoup (fast, no JS overhead).
  2. If visible text is shorter than MIN_CONTENT_LENGTH characters, the
     page is probably JS-rendered → fall back to Playwright (headless
     Chromium), which must be installed separately:
         playwright install chromium
"""

from __future__ import annotations

import difflib
import json
import re
import time
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    MAX_PROFESSORS,
    MAX_PROFILE_FETCHES,
    MIN_CONTENT_LENGTH,
    PROFILE_FETCH_DELAY,
    PARALLEL_PROFILE_WORKERS,
    REQUEST_TIMEOUT,
    scraper_logger as log,
)

# ---------------------------------------------------------------------------
# Common university aliases and curated homepage mappings for instant lookup
# ---------------------------------------------------------------------------
_CURATED_UNIVERSITIES: dict[str, dict[str, str]] = {
    "kiu": {
        "name": "Karakoram International University",
        "url": "https://www.kiu.edu.pk/",
    },
    "karakoram international university": {
        "name": "Karakoram International University",
        "url": "https://www.kiu.edu.pk/",
    },
    "nust": {
        "name": "National University of Sciences and Technology (NUST)",
        "url": "https://nust.edu.pk/",
    },
    "national university of sciences and technology": {
        "name": "National University of Sciences and Technology (NUST)",
        "url": "https://nust.edu.pk/",
    },
    "lums": {
        "name": "Lahore University of Management Sciences (LUMS)",
        "url": "https://lums.edu.pk/",
    },
    "lahore university of management sciences": {
        "name": "Lahore University of Management Sciences (LUMS)",
        "url": "https://lums.edu.pk/",
    },
    "fast": {
        "name": "National University of Computer and Emerging Sciences (FAST-NUCES)",
        "url": "https://www.nu.edu.pk/",
    },
    "fast-nuces": {
        "name": "National University of Computer and Emerging Sciences (FAST-NUCES)",
        "url": "https://www.nu.edu.pk/",
    },
    "qau": {
        "name": "Quaid-i-Azam University",
        "url": "https://qau.edu.pk/",
    },
    "quaid-i-azam university": {
        "name": "Quaid-i-Azam University",
        "url": "https://qau.edu.pk/",
    },
    "comsats": {
        "name": "COMSATS University Islamabad",
        "url": "https://www.comsats.edu.pk/",
    },
    "giki": {
        "name": "Ghulam Ishaq Khan Institute of Engineering Sciences and Technology (GIKI)",
        "url": "https://giki.edu.pk/",
    },
    "uet lahore": {
        "name": "University of Engineering and Technology, Lahore",
        "url": "https://uet.edu.pk/",
    },
    "pu": {
        "name": "University of the Punjab",
        "url": "http://pu.edu.pk/",
    },
    "punjab university": {
        "name": "University of the Punjab",
        "url": "http://pu.edu.pk/",
    },
    "mit": {
        "name": "Massachusetts Institute of Technology (MIT)",
        "url": "https://www.mit.edu/",
    },
    "massachusetts institute of technology": {
        "name": "Massachusetts Institute of Technology (MIT)",
        "url": "https://www.mit.edu/",
    },
    "stanford": {
        "name": "Stanford University",
        "url": "https://www.stanford.edu/",
    },
    "stanford university": {
        "name": "Stanford University",
        "url": "https://www.stanford.edu/",
    },
    "harvard": {
        "name": "Harvard University",
        "url": "https://www.harvard.edu/",
    },
    "harvard university": {
        "name": "Harvard University",
        "url": "https://www.harvard.edu/",
    },
    "oxford": {
        "name": "University of Oxford",
        "url": "https://www.ox.ac.uk/",
    },
    "university of oxford": {
        "name": "University of Oxford",
        "url": "https://www.ox.ac.uk/",
    },
    "cambridge": {
        "name": "University of Cambridge",
        "url": "https://www.cam.ac.uk/",
    },
    "university of cambridge": {
        "name": "University of Cambridge",
        "url": "https://www.cam.ac.uk/",
    },
    "cmu": {
        "name": "Carnegie Mellon University",
        "url": "https://www.cmu.edu/",
    },
    "carnegie mellon university": {
        "name": "Carnegie Mellon University",
        "url": "https://www.cmu.edu/",
    },
    "berkeley": {
        "name": "University of California, Berkeley",
        "url": "https://www.berkeley.edu/",
    },
    "uc berkeley": {
        "name": "University of California, Berkeley",
        "url": "https://www.berkeley.edu/",
    },
    "toronto": {
        "name": "University of Toronto",
        "url": "https://www.utoronto.ca/",
    },
    "university of toronto": {
        "name": "University of Toronto",
        "url": "https://www.utoronto.ca/",
    },
}


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
    """Playwright fallback for JS-heavy pages. Runs inside a separate worker
    thread so it can be called safely from within an active asyncio event loop.
    Properly closes browser and page resources in try...finally blocks."""
    import concurrent.futures

    def _sync_worker() -> str:
        browser = None
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            log.info("[playwright] Launching headless browser for: %s", url)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    page.set_extra_http_headers(_HEADERS)
                    page.goto(url, timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded")
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(REQUEST_TIMEOUT * 1000, 10000))
                    except Exception:
                        pass
                    html = page.content()
                    return html
                finally:
                    page.close()
        except ImportError:
            log.error(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            return ""
        except Exception as exc:
            log.error("[playwright] Playwright rendering failed for %s: %s", url, exc)
            return ""
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_sync_worker)
        return future.result()




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
# Link scoring and domain helpers for find_department_page
# ---------------------------------------------------------------------------

_NAV_KEYWORDS = [
    "faculty", "people", "staff", "academics", "professors",
    "researchers", "department", "members", "team", "directory",
]

_FACULTY_BONUS_KEYWORDS = [
    "faculty-name", "all-faculty", "faculty-directory", "people-cs",
    "faculty-list", "people/faculty", "directory/faculty",
]


def _is_same_uni_domain(netloc1: str, netloc2: str) -> bool:
    """Check if two netlocs belong to the same base institution domain."""
    p1 = netloc1.lower().split(":")[0].split(".")
    p2 = netloc2.lower().split(":")[0].split(".")
    d1 = ".".join(p1[-2:]) if len(p1) >= 2 else netloc1
    d2 = ".".join(p2[-2:]) if len(p2) >= 2 else netloc2
    # Handle country-code second-level domains like .edu.pk or .ac.uk
    if len(p1) >= 3 and p1[-2] in ["edu", "ac", "org", "gov", "com"]:
        d1 = ".".join(p1[-3:])
    if len(p2) >= 3 and p2[-2] in ["edu", "ac", "org", "gov", "com"]:
        d2 = ".".join(p2[-3:])
    return d1 == d2


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

    # High-priority faculty directory pattern bonus
    for bonus_kw in _FACULTY_BONUS_KEYWORDS:
        if bonus_kw in combined:
            score += 5

    # Penalise obvious non-faculty pages
    for bad in ["login", "apply", "admission", "news", "event", "blog",
                "contact", "about", "library", "alumni", "gallery",
                "research-journal", "hostel", "fee", "transport", "privacy", "terms"]:
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
# Tool 1 — resolve_university_url & Plausibility Validation
# ---------------------------------------------------------------------------

_GENERIC_UNIVERSITY_STOP_WORDS = {
    "university", "college", "institute", "school", "technical",
    "technology", "of", "and", "the", "for", "in", "at", "sciences", "science"
}


def _clean_university_tokens(text: str) -> list[str]:
    """Extract meaningful distinct tokens from a university name, stripping generic words."""
    return [
        t for t in re.findall(r"[a-z0-9]+", text.lower())
        if t not in _GENERIC_UNIVERSITY_STOP_WORDS and len(t) > 1
    ]


def _is_plausible_university_match(query: str, resolved_title: str, candidate_url: str = "") -> bool:
    """
    Check if a resolved university candidate plausibly matches the user's query.
    Prevents false-positive matches for nonexistent/fake universities.
    """
    q_norm = query.strip().lower()
    t_norm = (resolved_title or "").strip().lower()
    if not q_norm or not t_norm:
        return False

    # Exact or full substring match
    if q_norm == t_norm or q_norm in t_norm or t_norm in q_norm:
        return True

    q_distinct = _clean_university_tokens(q_norm)
    t_distinct = _clean_university_tokens(t_norm)

    domain = urllib.parse.urlparse(candidate_url).netloc.lower() if candidate_url else ""
    dom_tokens = _clean_university_tokens(domain.replace(".", " ").replace("-", " "))

    if q_distinct:
        matched_tokens = 0
        for q_tok in q_distinct:
            tok_matched = False
            # Check domain name (e.g. 'stanford' in 'stanford.edu')
            if any(q_tok in d_tok or (len(d_tok) >= 4 and d_tok in q_tok) for d_tok in dom_tokens):
                tok_matched = True
            else:
                # Check candidate title tokens
                for t_tok in t_distinct:
                    if q_tok == t_tok or (len(q_tok) >= 4 and (q_tok in t_tok or t_tok in q_tok)):
                        tok_matched = True
                        break
                    if len(q_tok) >= 5 and difflib.SequenceMatcher(None, q_tok, t_tok).ratio() >= 0.85:
                        tok_matched = True
                        break
            if tok_matched:
                matched_tokens += 1

        if matched_tokens > 0 and (matched_tokens == len(q_distinct) or matched_tokens / len(q_distinct) >= 0.66):
            return True

    # Acronym matching (e.g. MIT -> Massachusetts Institute of Technology)
    if len(q_norm) <= 6 and q_norm.isalpha():
        acronym = "".join(w[0] for w in re.findall(r"[a-z]+", t_norm) if w not in {"of", "and", "the", "for", "in", "at"})
        if q_norm == acronym or q_norm in acronym:
            return True

    return False


def _lookup_wikipedia_university(name: str) -> tuple[str, str | None, list[str]]:
    """
    Search Wikipedia & Wikidata for a university by name/acronym and extract
    its official website (P856). Returns (resolved_title, official_url, candidate_urls).
    """
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "opensearch",
            "search": name,
            "limit": 5,
            "namespace": 0,
            "format": "json",
        }
        res = requests.get(search_url, params=search_params, headers=_HEADERS, timeout=8)
        if not res.ok:
            return name, None, []
        data = res.json()
        titles: list[str] = data[1] if len(data) > 1 else []
        if not titles:
            return name, None, []

        candidates: list[str] = []
        best_title = titles[0]
        best_url: str | None = None

        # Check the top 2 matching article titles
        for title in titles[:2]:
            if not _is_plausible_university_match(name, title):
                continue
            query_params = {
                "action": "query",
                "titles": title,
                "prop": "pageprops|extlinks",
                "ellimit": 50,
                "format": "json",
                "redirects": 1,
            }
            q_res = requests.get(search_url, params=query_params, headers=_HEADERS, timeout=8)
            if not q_res.ok:
                continue
            pages = q_res.json().get("query", {}).get("pages", {})
            for _, page_data in pages.items():
                # 1. Check Wikidata P856 (official website property)
                wb = page_data.get("pageprops", {}).get("wikibase_item")
                if wb:
                    try:
                        wdata_url = f"https://www.wikidata.org/wiki/Special:EntityData/{wb}.json"
                        wdata_res = requests.get(wdata_url, headers=_HEADERS, timeout=8)
                        if wdata_res.ok:
                            wdata_json = wdata_res.json()
                            claims = wdata_json.get("entities", {}).get(wb, {}).get("claims", {})
                            p856 = claims.get("P856", [])
                            if p856:
                                val = p856[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                                if val and isinstance(val, str) and val.startswith("http"):
                                    if not best_url:
                                        best_url = val
                                        best_title = title
                                    if val not in candidates:
                                        candidates.append(val)
                    except Exception as e:
                        log.debug("Wikidata fetch error for %s: %s", wb, e)

                # 2. Check external links in page
                extlinks = page_data.get("extlinks", [])
                for el in extlinks:
                    link = el.get("*", "")
                    if any(tld in link for tld in [".edu", ".ac.", ".edu.", "university"]):
                        # ensure scheme
                        if not link.startswith("http"):
                            link = "https:" + link if link.startswith("//") else "https://" + link
                        parsed = urllib.parse.urlparse(link)
                        base = f"{parsed.scheme}://{parsed.netloc}/"
                        if base not in candidates and not any(bad in parsed.netloc for bad in ["wikipedia", "wikimedia", "wikidata"]):
                            candidates.append(base)
                            if not best_url:
                                best_url = base
                                best_title = title

        return best_title, best_url, candidates
    except Exception as exc:
        log.warning("Wikipedia lookup error for %s: %s", name, exc)
        return name, None, []


def _search_ddg_university(name: str) -> list[tuple[str, str]]:
    """Search DuckDuckGo HTML for university website candidates, validating plausibility."""
    try:
        query = f"{name} official website university homepage"
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        resp = requests.get(search_url, headers=_HEADERS, timeout=8)
        if not resp.ok:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates: list[tuple[str, str]] = []
        seen_urls: set[str] = set()
        for r in soup.select(".result"):
            a_url = r.select_one("a.result__url")
            a_title = r.select_one("a.result__title, a.result__a")
            if not a_url:
                continue
            raw_href = a_url.get("href", "")
            if "uddg=" not in raw_href:
                continue
            target = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
            parsed = urllib.parse.urlparse(target)
            if not parsed.scheme or not parsed.netloc:
                continue
            if any(bad in parsed.netloc for bad in ["duckduckgo", "wikipedia", "facebook", "linkedin", "twitter", "x.com", "youtube", "instagram", "tripadvisor"]):
                continue
            base_url = f"{parsed.scheme}://{parsed.netloc}/"
            if base_url in seen_urls:
                continue
            seen_urls.add(base_url)
            title = a_title.get_text(strip=True) if a_title else ""
            if _is_plausible_university_match(name, title, base_url):
                candidates.append((title or name, base_url))
        return candidates[:3]
    except Exception as exc:
        log.warning("DDG search fallback failed for %s: %s", name, exc)
        return []


def resolve_university_url(university_name: str) -> dict[str, Any]:
    """
    Resolve a university name or acronym to its official homepage URL.

    Call this tool ONLY when the user provides a university NAME with no URL.
    After this tool returns the university URL, the agent MUST show the found
    university name and URL to the user and ask for explicit confirmation
    (e.g., 'Are you referring to [University Name] at [URL]?') before proceeding.

    Args:
        university_name: The name or abbreviation of the university
                         (e.g. 'KIU', 'Stanford', 'NUST', 'Harvard University').

    Returns:
        A dict with:
          - status: 'success' or 'error'
          - university_name: resolved full official university name
          - university_url: the primary official homepage URL (on success)
          - candidates: list of candidate URLs
          - message: error description (on error)
    """
    name_clean = university_name.strip()
    log.info("[resolve_university_url] Resolving university name: %r", name_clean)

    if not name_clean:
        return {
            "status": "error",
            "message": "University name is empty. Please provide a valid university name.",
        }

    key = name_clean.lower()

    # 1. Curated / direct mapping (checked FIRST so acronyms/abbreviations work instantly)
    if key in _CURATED_UNIVERSITIES:
        entry = _CURATED_UNIVERSITIES[key]
        log.info("[resolve_university_url] Curated match for %r: %s", key, entry["url"])
        return {
            "status": "success",
            "university_name": entry["name"],
            "university_url": entry["url"],
            "candidates": [entry["url"]],
        }

    # 2. Wikipedia / Wikidata lookup (validated with plausibility check)
    wiki_title, wiki_url, wiki_candidates = _lookup_wikipedia_university(name_clean)
    if wiki_url and _is_plausible_university_match(name_clean, wiki_title, wiki_url):
        log.info("[resolve_university_url] Wikipedia match: %s -> %s", wiki_title, wiki_url)
        return {
            "status": "success",
            "university_name": wiki_title,
            "university_url": wiki_url,
            "candidates": wiki_candidates or [wiki_url],
        }

    # 3. DuckDuckGo search lookup fallback (validated with plausibility check)
    ddg_candidates = _search_ddg_university(name_clean)
    if ddg_candidates:
        resolved_name, primary_url = ddg_candidates[0]
        candidate_urls = [u for _, u in ddg_candidates]
        log.info("[resolve_university_url] DDG match for %r: %s (%s)", name_clean, resolved_name, primary_url)
        return {
            "status": "success",
            "university_name": resolved_name,
            "university_url": primary_url,
            "candidates": candidate_urls,
        }

    log.info("[resolve_university_url] No confident match found for %r", university_name)
    return {
        "status": "error",
        "message": (
            f"I couldn't confidently find a university matching '{university_name}'. "
            "Please check the spelling, or provide the university's website URL directly."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 2 — find_department_page & Search Fallback
# ---------------------------------------------------------------------------

def _search_department_fallback(
    university_url: str, department: str, dept_tokens: list[str]
) -> list[tuple[int, str, str]]:
    """Search DuckDuckGo HTML for department faculty page candidates on university domain."""
    parsed_uni = urllib.parse.urlparse(university_url)
    uni_netloc = parsed_uni.netloc
    parts = uni_netloc.lower().split(":")[0].split(".")
    base_dom = ".".join(parts[-2:]) if len(parts) >= 2 else uni_netloc
    if len(parts) >= 3 and parts[-2] in ["edu", "ac", "org", "gov", "com"]:
        base_dom = ".".join(parts[-3:])

    queries = [
        f"site:{base_dom} {department} faculty",
        f"site:{base_dom} {department} department",
        f"{base_dom} {department} faculty OR staff directory",
    ]

    scored: list[tuple[int, str, str]] = []
    _root_norm = university_url.rstrip("/")
    _origin_norm = f"{parsed_uni.scheme}://{parsed_uni.netloc}".rstrip("/")

    for query in queries:
        try:
            log.info("[find_department_page] Trying search fallback query: %r", query)
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
            resp = requests.get(search_url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for r in soup.select(".result"):
                a_url = r.select_one("a.result__url")
                a_title = r.select_one("a.result__title, a.result__a")
                if not a_url:
                    continue
                raw_href = a_url.get("href", "")
                if "uddg=" not in raw_href:
                    continue
                target = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
                parsed_target = urllib.parse.urlparse(target)
                if not parsed_target.scheme or not parsed_target.netloc:
                    continue
                if not _is_same_uni_domain(parsed_target.netloc, uni_netloc):
                    continue
                if target.rstrip("/") in (_root_norm, _origin_norm):
                    continue
                title_text = a_title.get_text(separator=" ", strip=True) if a_title else ""
                s = _score_link(target, title_text, dept_tokens, university_url)
                if s > 0:
                    scored.append((s, target, title_text))
            if scored:
                break
        except Exception as exc:
            log.warning("[find_department_page] Search fallback error for query %r: %s", query, exc)

    return scored


def find_department_page(university_url: str, department: str) -> dict[str, Any]:
    """
    Locate the department faculty/people listing page from a general university URL.

    Navigates the university homepage (and one level deeper if needed) to find
    the page that lists professors for the given department. If homepage scanning
    does not confidently locate the department page, automatically falls back
    to web search. Returns the best matching URL or an error message asking the user
    for a direct link only as the last resort.

    Args:
        university_url: The general university homepage URL
                        (e.g. 'https://www.kiu.edu.pk' or 'https://cs.stanford.edu').
        department: The department to search for
                    (e.g. 'Computer Science').

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - department_url: the discovered faculty page URL (on success)
          - candidates: list of candidate dicts
          - message: error description (on error)
    """
    log.info("[find_department_page] university=%s  department=%s", university_url, department)

    dept_tokens = _tokenize_department(department)

    # Try the given URL first; if it fails or returns minimal content, try root origin
    html = _get_html(university_url)
    target_url = university_url

    parsed_orig = urllib.parse.urlparse(university_url)
    origin_url = f"{parsed_orig.scheme}://{parsed_orig.netloc}/"

    if (not html or len(html) < 200) and origin_url.rstrip("/") != university_url.rstrip("/"):
        log.info("[find_department_page] Given URL failed/empty; falling back to origin: %s", origin_url)
        html = _get_html(origin_url)
        target_url = origin_url

    if not html:
        return {"status": "error", "message": f"Could not fetch {university_url}"}

    soup = BeautifulSoup(html, "lxml")
    scored: list[tuple[int, str, str]] = []

    _root_norm = target_url.rstrip("/")
    _origin_norm = origin_url.rstrip("/")
    uni_netloc = parsed_orig.netloc

    for tag in soup.find_all("a", href=True):
        href = _normalize_url(target_url, tag["href"])
        parsed_href = urllib.parse.urlparse(href)
        # Allow same domain and institutional subdomains (e.g. cs.stanford.edu)
        if not _is_same_uni_domain(parsed_href.netloc, uni_netloc):
            continue
        # Skip the root URLs themselves — never a faculty listing page
        if href.rstrip("/") in (_root_norm, _origin_norm):
            continue
        text = tag.get_text(separator=" ", strip=True)
        s = _score_link(href, text, dept_tokens, target_url)
        if s > 0:
            scored.append((s, href, text))

    # If nothing found on subpage, also check the root origin homepage
    if not scored and target_url.rstrip("/") != origin_url.rstrip("/"):
        log.info("[find_department_page] No links on subpage; checking origin homepage: %s", origin_url)
        orig_html = _get_html(origin_url)
        if orig_html:
            orig_soup = BeautifulSoup(orig_html, "lxml")
            for tag in orig_soup.find_all("a", href=True):
                href = _normalize_url(origin_url, tag["href"])
                parsed_href = urllib.parse.urlparse(href)
                if not _is_same_uni_domain(parsed_href.netloc, uni_netloc):
                    continue
                if href.rstrip("/") in (_root_norm, _origin_norm):
                    continue
                text = tag.get_text(separator=" ", strip=True)
                s = _score_link(href, text, dept_tokens, origin_url)
                if s > 0:
                    scored.append((s, href, text))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_url, top_text = scored[0]
        log.info("[find_department_page] Top candidate from homepage scan: score=%d  url=%s (text: %r)", top_score, top_url, top_text[:40])
    else:
        top_score = 0

    # If top score is modest (< 12), check if a direct department subdomain exists (e.g. cs.stanford.edu)
    if top_score < 12:
        parsed_target = urllib.parse.urlparse(target_url)
        d_parts = parsed_target.netloc.split(".")
        base_dom = ".".join(d_parts[-2:]) if len(d_parts) >= 2 else parsed_target.netloc
        if len(d_parts) >= 3 and d_parts[-2] in ["edu", "ac", "org", "gov", "com"]:
            base_dom = ".".join(d_parts[-3:])

        # Prioritize abbreviations (e.g. 'cs') then full names
        sub_candidates = [t for t in dept_tokens if len(t) <= 4] + [t for t in dept_tokens if len(t) > 4]
        for token in sub_candidates:
            subdomain_url = f"{parsed_target.scheme}://{token}.{base_dom}/"
            if subdomain_url.rstrip("/") != target_url.rstrip("/"):
                sub_html = _fetch_html(subdomain_url)
                if sub_html and len(sub_html) > 500:
                    log.info("[find_department_page] Found alive department subdomain: %s — scanning links", subdomain_url)
                    sub_soup = BeautifulSoup(sub_html, "lxml")
                    for tag in sub_soup.find_all("a", href=True):
                        href = _normalize_url(subdomain_url, tag["href"])
                        parsed_href = urllib.parse.urlparse(href)
                        if not _is_same_uni_domain(parsed_href.netloc, uni_netloc):
                            continue
                        if href.rstrip("/") in (_root_norm, _origin_norm, subdomain_url.rstrip("/")):
                            continue
                        text = tag.get_text(separator=" ", strip=True)
                        s = _score_link(href, text, dept_tokens, subdomain_url)
                        if s > 0:
                            scored.append((s, href, text))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            top_score, top_url, top_text = scored[0]

    # If the top score is modest (< 10), explore candidate subpages (e.g. top faculty/academic pages)
    if top_score < 10 and scored:
        log.info("[find_department_page] Score modest (%d) — exploring top candidate subpages deeper", top_score)
        candidates_to_explore = [u for _, u, _ in scored[:3]]
        for cand_url in candidates_to_explore:
            cand_html = _get_html(cand_url)
            if cand_html:
                cand_soup = BeautifulSoup(cand_html, "lxml")
                cand_norm = cand_url.rstrip("/")
                for tag in cand_soup.find_all("a", href=True):
                    href = _normalize_url(cand_url, tag["href"])
                    parsed_href = urllib.parse.urlparse(href)
                    if not _is_same_uni_domain(parsed_href.netloc, uni_netloc):
                        continue
                    if href.rstrip("/") in (_root_norm, _origin_norm, cand_norm):
                        continue
                    text = tag.get_text(separator=" ", strip=True)
                    s = _score_link(href, text, dept_tokens, target_url)
                    if s > 0:
                        scored.append((s, href, text))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            top_score, top_url, top_text = scored[0]
            log.info("[find_department_page] After deeper candidate scan: score=%d  url=%s", top_score, top_url)

    # Search Fallback: Triggered when homepage-link-scoring fails to find a confident match (score < 10 or empty)
    method_used = "homepage-scan"
    if top_score < 10 or not scored:
        log.info("[find_department_page] Homepage scan score below threshold (%d) — triggering search fallback", top_score)
        search_candidates = _search_department_fallback(university_url, department, dept_tokens)
        if search_candidates:
            search_candidates.sort(key=lambda x: x[0], reverse=True)
            best_search_score, best_search_url, best_search_text = search_candidates[0]
            if best_search_score > top_score or not scored:
                method_used = "search-fallback"
                scored = search_candidates + scored
                scored.sort(key=lambda x: x[0], reverse=True)
                top_score, top_url, top_text = scored[0]
                log.info(
                    "[find_department_page] Search fallback discovered candidate: score=%d url=%s (text: %r)",
                    top_score, top_url, top_text[:40]
                )

    if not scored or top_score <= 0:
        log.warning("[find_department_page] Both homepage-scan and search-fallback failed to find faculty page for %r at %s", department, university_url)
        return {
            "status": "error",
            "message": (
                f"Could not automatically locate the department faculty page for '{department}' on {university_url}. "
                "Please provide the direct department faculty listing URL."
            ),
        }

    top_score, top_url, top_text = scored[0]
    log.info(
        "[find_department_page] Successfully located department page via [%s]: score=%d url=%s (text: %r)",
        method_used, top_score, top_url, top_text[:40]
    )

    # Deduplicate candidates
    seen_urls: set[str] = set()
    unique_candidates: list[dict[str, Any]] = []
    for s, u, _ in scored:
        if u not in seen_urls:
            seen_urls.add(u)
            unique_candidates.append({"url": u, "score": s})

    return {
        "status": "success",
        "department_url": top_url,
        "candidates": unique_candidates[:5],
    }


# ---------------------------------------------------------------------------
# Professor block extraction helpers
# ---------------------------------------------------------------------------

def _decode_cf_email(cf_hex: str) -> str:
    """Decode Cloudflare-obfuscated email string."""
    try:
        r = int(cf_hex[:2], 16)
        return "".join([chr(int(cf_hex[i:i + 2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""


def _extract_email(text: str, tag_html: str) -> str:
    """Extract email from visible text, mailto links, or Cloudflare data-cfemail."""
    # 1. Look for Cloudflare email protection
    cf_match = re.search(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', tag_html)
    if cf_match:
        decoded = _decode_cf_email(cf_match.group(1))
        if "@" in decoded:
            return decoded

    # 2. Look for mailto in raw HTML
    mailto = re.search(r'mailto:([^\s"\'<>?]+)', tag_html)
    if mailto:
        return mailto.group(1)

    # 3. Regex in visible text
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
        sibling_html = ""
        sib = heading.find_next_sibling()
        for _ in range(3):
            if sib is None:
                break
            sibling_text += sib.get_text(separator=" ", strip=True) + " "
            sibling_html += str(sib) + " "
            sib = sib.find_next_sibling()

        full_text = name_text + " " + sibling_text
        full_html = str(heading) + " " + sibling_html
        results.append({
            "name": name_text,
            "title_text": sibling_text.strip(),
            "research_text": sibling_text.strip(),
            "email": _extract_email(full_text, full_html),
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


_RESEARCH_HINT_PATTERNS = re.compile(
    r"\b(research|interests|specialization|focus|publications|projects|laboratory|lab|group|field|area|topics)\b",
    re.IGNORECASE,
)


def _has_research_content(text: str) -> bool:
    """Check if the raw listing block already contains research description."""
    if len(text) > 250:
        return True
    if _RESEARCH_HINT_PATTERNS.search(text):
        return True
    return False


def _fetch_profile_page_text(profile_url: str) -> tuple[str, str]:
    """Fetch an individual professor profile page and extract text snippet and email if present.
    Returns (profile_text, email)."""
    if not profile_url or not profile_url.startswith(("http://", "https://")):
        return ("", "")

    html = _fetch_html(profile_url)
    if not html or len(html) < 150:
        return ("", "")

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    full_text = soup.get_text(separator=" ", strip=True)
    if len(full_text) < 40:
        return ("", "")

    email = _extract_email(full_text, str(soup))

    # Try to extract sections specifically discussing research or about
    research_snippets = []
    for heading in soup.find_all(re.compile(r"h[1-6]")):
        h_text = heading.get_text(separator=" ", strip=True).lower()
        if any(
            w in h_text
            for w in [
                "research",
                "interest",
                "publication",
                "project",
                "about",
                "bio",
                "overview",
                "specialization",
            ]
        ):
            curr = heading.next_sibling
            count = 0
            while curr and count < 4:
                if hasattr(curr, "get_text"):
                    t = curr.get_text(separator=" ", strip=True)
                    if t:
                        research_snippets.append(t)
                        count += 1
                curr = curr.next_sibling

    if research_snippets:
        combined = " | ".join(research_snippets)
        return (combined[:2000], email)

    return (full_text[:1500], email)


def _enrich_professors_with_profile_pages(
    raw_profs: list[dict],
    desired_titles: str = "",
    max_fetches: int = MAX_PROFILE_FETCHES,
) -> list[dict]:
    """
    Tier-2 enrichment: For professor blocks that lack research text in the listing page,
    fetch their individual profile pages up to max_fetches (with rate-limiting delay),
    prioritizing professors that match desired_titles.
    """
    if not raw_profs:
        return raw_profs

    # Parse desired titles into normalized lowercase keywords
    title_keywords = [
        t.strip().lower() for t in re.split(r"[,;|/]", desired_titles) if t.strip()
    ]

    def _matches_title(prof: dict) -> bool:
        if not title_keywords:
            return True
        t_text = (prof.get("title_text") or "").lower()
        for kw in title_keywords:
            if kw in t_text:
                return True
        return False

    fetches_done = 0
    for prof in raw_profs:
        if fetches_done >= max_fetches:
            break

        profile_url = prof.get("profile_url", "")
        # Only fetch if profile_url is valid and listing text has no research content
        if not profile_url or not profile_url.startswith(("http://", "https://")):
            continue

        if _has_research_content(prof.get("research_text", "")):
            continue

        # Check title match filter
        if not _matches_title(prof):
            continue

        log.info(
            "[profile_scrape] Fetching profile page for %s: %s",
            prof.get("name"),
            profile_url,
        )
        profile_text, profile_email = _fetch_profile_page_text(profile_url)
        fetches_done += 1

        if profile_text:
            prof["research_text"] = (
                f"{prof.get('title_text', '')} | Profile: {profile_text}"
            )
        if profile_email and not prof.get("email"):
            prof["email"] = profile_email

        # Short delay to be polite to university servers
        time.sleep(PROFILE_FETCH_DELAY)

    if fetches_done > 0:
        log.info("[profile_scrape] Enriched %d professors with profile page details", fetches_done)
    return raw_profs


# ---------------------------------------------------------------------------
# Tool 2 — scrape_faculty_page
# ---------------------------------------------------------------------------

def scrape_faculty_page(
    url: str, department: str, desired_titles: str = ""
) -> dict[str, Any]:
    """
    Scrape a faculty listing page and return raw professor data blocks.

    First attempts standard requests + BeautifulSoup parsing (fast & lightweight).
    If BeautifulSoup returns 0 professor blocks (e.g. on JavaScript-rendered
    pages), it automatically falls back to Playwright (headless browser) to render the DOM
    and extract professor blocks using the same block-detection logic.

    For professor blocks that lack detailed research descriptions on the listing page,
    it automatically follows and scrapes their individual profile pages (up to 20 fetches),
    prioritizing faculty matching desired_titles.

    Args:
        url: Direct URL to the department faculty/people listing page.
        department: Name of the department (used for context/logging).
        desired_titles: Optional filter for academic titles (e.g. 'Professor', 'Assistant Professor').

    Returns:
        A dict with keys:
          - status: 'success' or 'error'
          - raw_professors: list of raw professor dicts (on success)
          - count: number of raw entries found
          - method: 'BeautifulSoup' or 'Playwright' (on success)
          - message: error description (on error)
    """
    log.info(
        "[scrape_faculty_page] Starting scrape: url=%s  department=%s  desired_titles=%r",
        url,
        department,
        desired_titles,
    )
    start_time = time.monotonic()

    # -----------------------------------------------------------------------
    # Step 1: Default fast attempt using requests + BeautifulSoup
    # -----------------------------------------------------------------------
    bs_html = _fetch_html(url)
    raw_profs: list[dict] = []

    if bs_html:
        bs_soup = BeautifulSoup(bs_html, "lxml")
        for tag in bs_soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        raw_profs = _extract_raw_professors(bs_soup, url)

    if raw_profs:
        raw_profs = _enrich_professors_with_profile_pages(
            raw_profs, desired_titles=desired_titles, max_fetches=MAX_PROFILE_FETCHES
        )
        elapsed = time.monotonic() - start_time
        log.info(
            "[scrape_faculty_page] Succeeded via BeautifulSoup: found %d professor blocks in %.2fs (url=%s)",
            len(raw_profs),
            elapsed,
            url,
        )
        return {
            "status": "success",
            "raw_professors": raw_profs,
            "count": len(raw_profs),
            "method": "BeautifulSoup",
        }

    # -----------------------------------------------------------------------
    # Step 2: Automatic Playwright fallback for JS-rendered pages
    # -----------------------------------------------------------------------
    log.info(
        "[scrape_faculty_page] BeautifulSoup returned 0 professor blocks for %s — retrying with Playwright fallback",
        url,
    )
    pw_html = _fetch_html_playwright(url)

    if pw_html:
        pw_soup = BeautifulSoup(pw_html, "lxml")
        for tag in pw_soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        raw_profs = _extract_raw_professors(pw_soup, url)

    if raw_profs:
        raw_profs = _enrich_professors_with_profile_pages(
            raw_profs, desired_titles=desired_titles, max_fetches=MAX_PROFILE_FETCHES
        )
        elapsed = time.monotonic() - start_time
        log.info(
            "[scrape_faculty_page] Succeeded via Playwright fallback: found %d professor blocks in %.2fs (url=%s)",
            len(raw_profs),
            elapsed,
            url,
        )
        return {
            "status": "success",
            "raw_professors": raw_profs,
            "count": len(raw_profs),
            "method": "Playwright",
        }

    # -----------------------------------------------------------------------
    # Step 3: Both attempts returned zero results
    # -----------------------------------------------------------------------
    elapsed = time.monotonic() - start_time
    log.warning(
        "[scrape_faculty_page] Both BeautifulSoup and Playwright returned 0 blocks in %.2fs (url=%s)",
        elapsed,
        url,
    )
    return {
        "status": "error",
        "message": (
            f"No professor blocks detected on {url} using either standard parsing or browser rendering. "
            "The page structure may be unusual or the directory may be located at a different URL. "
            "Please check the faculty listing URL or provide the general university homepage."
        ),
        "count": 0,
    }


