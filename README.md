# 🎓 Scholarship Professor Finder

An AI-powered agent built with **Google ADK (Agent Development Kit)**, **Gemini**, **BeautifulSoup**, and **Playwright** that finds and filters university professors for scholarship outreach through a conversational CLI.

---

## 🎯 Features

- 🏛️ **University Name Resolution & Confirmation** — Give a university name or acronym (e.g. `KIU`, `NUST`, `Stanford`), and the agent resolves its official homepage URL and confirms with you before proceeding.
- 🔍 **Smart Faculty Scraping** — Deterministic fetching with `requests` + `BeautifulSoup`, with automatic `Playwright` fallback for JavaScript-rendered sites.
- 🤖 **LLM-Powered Organization & Filtering** — Gemini organizes raw, messy scraped text into structured faculty profiles and filters them by your desired academic titles and research keywords.
- 🔗 **Two-Step Site Navigation** — Give a general university homepage URL and the agent automatically locates the department faculty page.
- ⚡ **Direct Department Page Support** — Provide a direct department page URL to skip navigation and scrape immediately.

---

## 📁 Project Structure

```
scholarship-scraper/
├── main.py            # Entry point — CLI conversation loop
├── agent.py           # Google ADK agent definition, tools, and system prompt
├── scraper.py         # 3 core tools: resolve_university_url, find_department_page, scrape_faculty_page
├── config.py          # Shared config (API key, timeouts, logging)
├── requirements.txt   # Python dependencies
├── .env.example       # Template for environment variables
├── logs/              # Auto-created execution logs
└── output/            # Auto-created results directory
```

---

## 🛠️ The Three Agent Tools

| Tool | Input | Description |
|---|---|---|
| `resolve_university_url` | `{ university_name: string }` | Resolves a university name/acronym to its official homepage URL. The agent asks the user for explicit confirmation before proceeding. |
| `find_department_page` | `{ university_url: string, department: string }` | Navigates the university homepage to locate the specific department faculty listing page. |
| `scrape_faculty_page` | `{ url: string, department: string }` | Scrapes raw HTML from the department page and extracts unstructured professor data blocks for the LLM to organize and filter. |

---

## 🚀 Quickstart

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

Create a `.env` file with your Gemini API key:

```env
GEMINI_API_KEY=your-gemini-api-key-here
```

Get a free API key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

### 4. Run the interactive CLI agent

```bash
python main.py
```

---

## 💬 Example Interaction

```text
============================================================
  🎓  Scholarship Professor Finder  
============================================================
  Type 'exit' or 'quit' to end the session.
============================================================

Agent: Hello! 👋 I'm your scholarship professor finder assistant. Tell me the university name or URL, department, research interests, and preferred academic titles, and I'll find matching professors for you!

You: KIU, Computer Science, Machine Learning, Assistant Professors only

Agent: Are you referring to Karakoram International University at https://www.kiu.edu.pk/?

You: Yes

Agent: Got it! Searching the Computer Science department faculty...

I found 3 Assistant Professor(s) in Computer Science at Karakoram International University matching your criteria:

1. **Dr. Ali Khan** — Assistant Professor
   - 🔬 **Research:** Machine Learning, NLP, Deep Learning
   - 📧 **Email:** ali.khan@kiu.edu.pk
   - 🔗 **Profile:** https://www.kiu.edu.pk/faculty/ali-khan

2. **Dr. Sarah Ahmed** — Assistant Professor
   - 🔬 **Research:** Computer Vision, Pattern Recognition, ML
   - 📧 **Email:** sarah.ahmed@kiu.edu.pk
   - 🔗 **Profile:** https://www.kiu.edu.pk/faculty/sarah-ahmed
```
