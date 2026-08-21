# 🎓 Scholarship Professor Finder

An AI-powered agent that scrapes university faculty pages, filters professors by title and research interests, and generates personalized scholarship outreach emails — all through a conversational CLI.

Built with **Google ADK**, **Gemini**, **BeautifulSoup**, and **Playwright**.

---

## Features

- 🔍 **Smart faculty scraping** — works on static and JavaScript-rendered pages (Playwright fallback)
- 🤖 **LLM-powered data cleaning** — Gemini parses messy scraped text into clean professor profiles
- 🎯 **Flexible filtering** — filter by academic title and research keywords
- ✉️ **Personalized email drafts** — generates tailored outreach emails per professor
- 🔗 **Two-step navigation** — give a general university URL and the agent finds the department page automatically

---

## Project Structure

```
scholarship-scraper/
├── main.py            # Entry point — CLI conversation loop
├── agent.py           # ADK agent + Phases 2, 3, 4 (organize, filter, tools)
├── scraper.py         # Phase 1 — raw HTML scraping (requests + Playwright)
├── email_drafter.py   # Phase 5 — personalized email draft generation
├── config.py          # Shared config (API key, timeouts, logging)
├── requirements.txt   # Python dependencies
├── .env.example       # Template for environment variables
├── logs/              # Scraper and agent logs (auto-created)
└── output/            # Reserved for saved results (auto-created)
```

---

## Quickstart

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd scholarship-scraper
pip install -r requirements.txt
```

### 2. Install Playwright browser (one-time)

```bash
playwright install chromium
```

### 3. Set your Gemini API key

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your-gemini-api-key-here
```

Get a free API key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

Or set the key directly in your shell:

```powershell
# PowerShell
$env:GEMINI_API_KEY = "your-key-here"
```

```bash
# bash / zsh
export GEMINI_API_KEY="your-key-here"
```

### 4. Run the agent

```bash
python main.py
```

---

## Example Conversation

```
======================================================
  🎓  Scholarship Professor Finder
======================================================
  Type 'exit' or 'quit' to end the session.
======================================================

Agent: Hi! I'm your scholarship outreach assistant. To get started, please share:
  - The university URL (homepage or direct department page)
  - Department name
  - Your research interest keywords
  - Preferred academic title(s)

You: https://people.cs.uchicago.edu/  Computer Science  machine learning  Assistant Professor

🔍 Searching...

Agent: ✅ Here are 3 professor(s) I found matching your criteria: ...

Agent: Would you like me to draft personalized outreach emails for these professors?

You: Yes — my name is Ali Khan, I'm applying for a PhD, background in NLP and Urdu sentiment analysis.

✉️ Here are 3 personalized email draft(s): ...
```

---

## How It Works

```
User Input
    │
    ▼
Phase 1 — scraper.py
    Fetch HTML (requests → Playwright fallback)
    Extract raw professor blocks (5-strategy heuristic)
    │
    ▼
Phase 2 — agent.py (_organize_professors)
    Gemini parses messy text → clean JSON profiles
    { name, title, research_interests, email, profile_url }
    │
    ▼
Phase 3 — agent.py (_filter_professors)
    Plain Python: filter by title + research keywords
    │
    ▼
Phase 4 — agent.py (ADK LlmAgent)
    Orchestrates tools, manages conversation, presents results
    │
    ▼
Phase 5 — email_drafter.py
    Gemini drafts personalized emails per professor
    Tailored to student's degree level + research background
```

---

## Configuration

Edit [`config.py`](config.py) to adjust:

| Setting | Default | Description |
|---|---|---|
| `MODEL_NAME` | `gemini-2.0-flash` | Gemini model for all LLM calls |
| `REQUEST_TIMEOUT` | `15` | HTTP request timeout in seconds |
| `MAX_PROFESSORS` | `50` | Cap on raw scraped results sent to Gemini |
| `MAX_TOOL_CALLS` | `10` | Guardrail: max tool calls per conversation turn |
| `MIN_CONTENT_LENGTH` | `500` | Chars threshold below which Playwright is triggered |

---

## Scraping Strategy

The scraper tries five strategies in order, using the first that yields results:

1. **CSS class hints** — looks for elements with classes like `faculty`, `card`, `profile`, `member`
2. **`<article>` tags** — articles containing headings
3. **Directory lists** — `<ul>`/`<ol>` with directory-hinted class/id
4. **Table rows** — `<tr>` rows in tables with ≥ 3 rows
5. **Heading fallback** — extracts all `<h2>`–`<h4>` as names with surrounding text

---

## Requirements

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free tier available)
- Internet access (for scraping and Gemini API calls)

---

## Troubleshooting

**`GEMINI_API_KEY is not set`** — Create a `.env` file from `.env.example` and add your key.

**`Playwright browser not found`** — Run `playwright install chromium`.

**`No professor blocks detected`** — The page structure is unusual. Try providing the direct faculty listing URL (not the department homepage).

**`SSL certificate error`** — The scraper automatically retries with SSL verification disabled for affected sites.

**Empty results after filtering** — Try broadening your search: use fewer keywords, include more title types, or verify the URL points to the faculty listing page.
