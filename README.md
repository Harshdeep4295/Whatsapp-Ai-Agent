# WhatsApp Exam Prep Bot

An AI-powered WhatsApp assistant for Indian government exam preparation (HCS, UPSC, CBSE and more).

## Features
- Fetches exam syllabi and question papers from the web on demand
- Generates MCQ quizzes based on exam patterns
- Tracks quiz scores per user
- Summarizes current affairs from RSS feeds
- Remembers conversation history per user
- RAG pipeline: indexes fetched content for accurate answers

## Tech Stack
- **WhatsApp**: Meta Cloud API (official, free 1k conversations/month)
- **LLM**: Groq API — Llama 3.3 70B (free)
- **Vector DB**: ChromaDB (persistent, stored in repo)
- **Database**: Supabase (conversations, quiz state, content cache)
- **Hosting**: Railway (free $5 credit/month, always-on, no sleep)
- **Search**: DuckDuckGo (no API key needed)
- **News**: feedparser + free RSS feeds

## Setup

### 1. Required Accounts (all free)
- [GitHub](https://github.com)
- [Groq](https://console.groq.com)
- [Supabase](https://supabase.com)
- [Meta Developer](https://developers.facebook.com)
- [Railway](https://railway.app)

### 2. Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```
GROQ_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=
```

### 3. Supabase Tables
Run the SQL in `docs/supabase_schema.sql` in your Supabase SQL editor.

### 4. Local Development
```bash
pip install -r requirements.txt
PYTHONPATH=src uvicorn src.main:app --reload --port 8000
```

### 5. Deploy to Railway
- Go to railway.app → New Project → Deploy from GitHub repo
- Railway auto-detects the Procfile and runs the server
- Go to Variables tab → add all 8 env vars
- Go to Settings → Domains → Generate Domain (your public URL)
- Set that URL + `/webhook` in Meta Developer console as webhook URL

## Usage
Send messages to your bot number:
- `HCS syllabus` — fetches and summarises syllabus
- `quiz me on Polity` — starts MCQ quiz
- `A` / `B` / `C` / `D` — answer quiz questions
- `stop quiz` — ends quiz, shows final score
- `current affairs` — today's news summary
- `HCS 2023 question paper` — fetches past paper
- `study plan for 30 days` — generates study schedule
- `explain Panchayati Raj` — detailed topic explanation
