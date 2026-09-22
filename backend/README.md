# ⚙️ Scholarship Scraper Agent — Backend

FastAPI server and Google ADK agent for discovering and scraping faculty profiles for scholarship outreach.

---

## 📁 Backend Structure

```
backend/
├── app.py              # FastAPI REST API server (port 8001)
├── agent.py            # Google ADK agent definition & prompt engineering
├── scraper.py          # Scraping engine (BeautifulSoup + Playwright fallback)
├── config.py           # Configuration, environment variables, & logging
├── main.py             # Standalone CLI interactive loop
├── requirements.txt    # Python dependencies
├── apps/               # ADK app definitions
├── logs/               # Execution log files
├── .env                # Secret keys (GEMINI_API_KEY)
└── .env.example        # Environment variable template
```

---

## 🚀 Running the Backend

### 1. Ensure Virtual Environment is Active
From the repository root:
```powershell
venv\Scripts\Activate.ps1
```

### 2. Environment Variables
Make sure your `.env` file exists in `backend/.env` (or project root):
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Start the FastAPI Server (for Frontend)
```bash
# Option A: From backend directory
cd backend
python app.py

# Option B: Using uvicorn from backend directory
cd backend
uvicorn app:app --reload --port 8001
```
The API server will run at `http://127.0.0.1:8001` with docs at `http://127.0.0.1:8001/docs`.

### 4. Interactive CLI Mode (Standalone)
If you wish to chat with the agent in the command line:
```bash
cd backend
python main.py
```
