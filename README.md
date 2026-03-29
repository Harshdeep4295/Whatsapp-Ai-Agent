# WhatsApp HCS/HPSC Exam Tutor

An AI-powered WhatsApp tutor for the **Haryana Civil Services (HCS/HPSC) Preliminary Exam**. Delivers adaptive quizzes, mock tests, current affairs, and study sessions — entirely over WhatsApp, with no app to install.

Built on FastAPI + Meta WhatsApp Business API + Groq LLM + Supabase.

---

## Features

### Practice and Tests

| Command | What it does |
|---------|-------------|
| `quiz me` | Adaptive MCQ drill — automatically picks your weakest topics |
| `hpsc mock` / `blueprint mock` | 25-question mock weighted to the real 2023 HPSC paper distribution |
| `haryana special` / `haryana drill` | Haryana-only questions (folk culture, 1857 leaders, heritage sites, geography) |
| `mock test` | Quick 10-question test on any topic |
| `drill me` | Instant fact + question on your weakest topic |

### Study

| Command | What it does |
|---------|-------------|
| `study [topic]` | Educational passage + 3 comprehension questions |
| `explain [topic]` | Guided study session with overview and warm-up questions |
| `current affairs` | Latest HCS-relevant news, RSS-fed, de-duplicated per user, LLM-filtered |
| `search [anything]` | Real web search with a summarised answer (never redirects to Google) |

### Progress Tracking

| Command | What it does |
|---------|-------------|
| `my progress` | Topic-wise accuracy breakdown |
| `wrong answers` | Review missed questions with explanations |
| `set exam date [date]` | Track countdown to your exam |

### Automated (Scheduled)

- **2-hour fact drill** — Auto-sent every 2 hours: one surprising fact + one adaptive question. Skips the question (but still sends the fact) if a quiz or mock is in progress.
- **Inactivity nudge** — Every 4 hours between 8 AM and 10 PM IST, nudges users who haven't studied today but were active in the last 7 days.
- **Nightly revision** — Daily summary: streak, exam countdown, topics covered, weak areas, and a "Did You Know?" fact.

---

## Question Formats

Questions mirror the actual HPSC GS paper distribution. GS topics never get simple MCQs.

| Format | Share | Description |
|--------|-------|-------------|
| Statement-correctness | ~55% | "How many of the above statements are correct? None / Only one / Only two / All three" |
| Match List I with List II | ~35% | Match 4 items to 4 items using code pairs (a-i, b-ii, etc.) |
| Assertion-Reason | ~10% | A and R true/false with explanation of their relationship |
| Simple MCQ | 0% for GS | Used only for CSAT/aptitude topics (Blood Relations, Number Coding, etc.) |

---

## Post-Answer Feedback

- **Correct:** Explanation of why the answer is right.
- **Wrong:** `💡 *Concept:* [2-3 sentence explanation covering the concept, why wrong options are traps, memory tip]`
- **Mock test end:** Score, weak topics, and up to 4 missed questions with the correct answer and concept note.

---

## Exam Blueprint (Real 2023 HPSC Paper)

| Topic | Questions |
|-------|-----------|
| Indian History and Culture | 22 |
| Indian Polity and Constitution | 18 |
| General Science | 18 |
| Indian Geography | 15 |
| Indian Economy and Development | 12 |
| Haryana History and Culture | 4 |
| Science and Technology | 4 |
| Important Government Schemes | 3 |
| Haryana Geography | 2 |
| Art and Culture | 2 |
| **Total** | **100** |

---

## Architecture

**Entry point:** `src/main.py` — FastAPI app with lifespan (starts APScheduler on boot).

**Routes:**
- `GET /` — health check
- `GET /webhook` — WhatsApp webhook verification
- `POST /webhook` — incoming message handler (deduplicates by message ID)

**Core modules in `src/bot/`:**

| Module | Responsibility |
|--------|---------------|
| `handler.py` | Message routing, trigger matching, session intercepts, welcome message |
| `quiz.py` | Question generation (4 formats), quiz sessions, mock tests, progress tracking |
| `scheduler.py` | APScheduler jobs: 2-hour fact drills, inactivity nudge, nightly revision, current affairs, weekly report |
| `groq_tools.py` | Tool schemas exposed to the LLM + `run_tool_loop()` (agentic tool calling) |
| `tools.py` | Tool implementations called by the LLM |
| `llm.py` | Multi-provider LLM abstraction (Groq → Cerebras → Together fallback chain), SYSTEM_PROMPT (Yudhister persona) |
| `whatsapp.py` | WhatsApp Business API: webhook parsing, `send_message()` (auto-splits at 3800 chars), interactive quiz UI |
| `memory.py` | Conversation history (Supabase), streak tracking, exam date |
| `news.py` | RSS + web search → LLM-filtered current affairs |
| `web_search.py` | Tavily → DuckDuckGo fallback search |
| `fetcher.py` | Web page and PDF content fetching |
| `supabase_client.py` | Lazy Supabase singleton |
| `rag.py` | Chroma vector store for study material search |

---

## LLM Stack

| Provider | Model | Role |
|----------|-------|------|
| Groq | llama-3.3-70b-versatile | Primary |
| Groq | llama-3.1-8b-instant | Fallback (separate quota) |
| Cerebras | llama-3.3-70b | Optional fallback |
| Together | Llama-3.3-70B-Instruct-Turbo | Optional fallback |

---

## Database Schema (Supabase)

| Table | Purpose |
|-------|---------|
| `conversations` | Full message history per user (role, content, created_at) |
| `user_profiles` | Streak, last_active_date, exam_date per user |
| `user_progress` | Topic-wise correct/total counts (used for adaptive topic selection) |
| `user_answer_history` | Every answered question with full details (for wrong-answer review) |
| `quiz_sessions` | Active quiz state per user (unique per chat_id — upsert) |
| `mock_tests` | Active mock test state (questions jsonb, answers jsonb, current_idx) |
| `scheduled_jobs` | Recurring jobs: type, interval_minutes, next_run_at, seen_keys, last_content_hash |
| `content_cache` | Fetched and indexed study material with Chroma IDs |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12 |
| Web framework | FastAPI + uvicorn |
| LLM | Groq (llama-3.3-70b) with multi-provider fallback |
| Database | Supabase (PostgreSQL via PostgREST) |
| Vector store | Chroma (RAG over study material) |
| Scheduler | APScheduler (AsyncIOScheduler) |
| WhatsApp | Meta Graph API v19.0 |
| Web search | Tavily + DuckDuckGo fallback |
| Deployment | Railway |

---

## Setup

### Requirements

- Python 3.12.9 (see `.python-version`)
- WhatsApp Business API access (Meta Developer account)
- Supabase project
- Groq API key

### Environment Variables

```env
# Required
GROQ_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=

# Optional
CEREBRAS_API_KEY=        # LLM fallback
TOGETHER_API_KEY=        # LLM fallback
TAVILY_API_KEY=          # Better web search (falls back to DuckDuckGo)
ADMIN_CHAT_ID=           # Your WhatsApp number for admin commands
SUPABASE_SERVICE_KEY=    # Falls back to SUPABASE_KEY
```

### Database

Run `docs/supabase_schema.sql` in your Supabase SQL editor to create all tables.

### Run Locally

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

### Deploy to Railway

```bash
# Procfile is already configured:
# web: uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
railway up
```

Point your WhatsApp Business webhook to: `https://your-domain.com/webhook`
