# HCS Mains Exam Prep — Setup & Features

The WhatsApp exam bot now supports **HCS Mains** exam preparation in addition to the existing Prelims MCQ mode.

## What's New

### 5 New Features

| Feature | Trigger | What happens |
|---------|---------|--------------|
| **Answer Writing** | "answer writing on [topic]", "practice short answer" | Bot generates a mains-style question → you write → LLM scores (content/structure/examples) → score report |
| **Ethics Case Study** | "case study", "ethics question", "give me a dilemma" | Realistic ethical dilemma scenario + 3 sub-questions → you respond → LLM evaluates |
| **Answer Template** | "how to answer [topic]", "format for History" | Returns structured template (opening, key points, example, conclusion) |
| **Mains PYQ** | "PYQ mains on [topic]", "previous year mains" | Generates HPSC Mains-style questions with expected answer outlines |
| **Mode Switch** | "switch to mains", "focus on mains now" | Saves `exam_mode=mains` to your profile → Yudhister adapts |

### Score Report Format

```
📝 *Answer Evaluated*

*Content:* 7/10
*Structure:* 3/5
*Examples:* 2/5
*Total: 12/20* (60%)

❗ Missing:
• 73rd Amendment provisions
• Haryana Panchayat specific role

💡 Tip: Structure as Background → Provisions → Impact → Way Forward
```

---

## Setup Instructions

### 1. Run Database Migrations

**Option A: Supabase Dashboard**
1. Open [Supabase Dashboard](https://app.supabase.com/)
2. Go to your project → SQL Editor
3. Copy/paste contents of `docs/migrations_mains.sql`
4. Click "Run"

**Option B: SQL Commands**
```sql
-- Add exam_mode column
ALTER TABLE user_profiles ADD COLUMN exam_mode text DEFAULT 'prelims';

-- Create mains_answers table
CREATE TABLE mains_answers (
  id bigserial PRIMARY KEY,
  chat_id text NOT NULL,
  topic text NOT NULL,
  question_text text NOT NULL,
  user_answer text NOT NULL,
  answer_type text NOT NULL,
  score_content int,
  score_structure int,
  score_examples int,
  total_score int,
  max_score int DEFAULT 20,
  feedback text,
  missing_points jsonb,
  attempted_at timestamptz DEFAULT NOW()
);

CREATE INDEX ON mains_answers(chat_id);
CREATE INDEX ON mains_answers(chat_id, topic);
CREATE INDEX ON mains_answers(chat_id, answer_type);
```

### 2. Verify Files Are in Place

```bash
# New file
src/bot/mains.py

# Updated files
src/bot/tools.py        # 5 tool wrappers + fns dict
src/bot/groq_tools.py   # 5 tool schemas
src/bot/handler.py      # 2 intercept blocks
src/bot/llm.py          # SYSTEM_PROMPT updated
src/bot/quiz.py         # HCS_MAINS_TOPICS dict added

# Documentation
docs/migrations_mains.sql
docs/MAINS_SETUP.md (this file)
```

### 3. Test the Deployment

After git push to Railway, test in WhatsApp:

```
User: "switch to mains"
Bot: "🎯 *Mains Mode Activated!*..."

User: "answer writing on Panchayati Raj short"
Bot: "📝 *Short Answer — Panchayati Raj*... [question] _Word limit: ~100 words_"

User: "[your answer about panchayati raj]"
Bot: "📝 *Answer Evaluated* ... *Total: 14/20* (70%)"

User: "case study"
Bot: "⚖️ *Ethics Case Study*... [scenario] *Answer these 3 questions:*..."
```

---

## Implementation Details

### New Files

**`src/bot/mains.py` (267 lines)**
- `start_answer_writing()` — generates Mains question + stores session
- `check_answer_writing()` — LLM evaluates answer → score report
- `has_active_answer_writing()` — session check
- `start_case_study()` — ethical dilemma generation
- `check_case_study_answer()` — case study evaluation
- `has_active_case_study()` — session check
- `get_answer_template()` — writing framework helper
- `get_mains_pyq()` — previous year question generator
- `switch_exam_mode()` — toggle prelims/mains mode

**`docs/migrations_mains.sql`**
- SQL to add `exam_mode` column to `user_profiles`
- SQL to create `mains_answers` table with indexes

### Modified Files

**`src/bot/tools.py`**
- Added 5 async tool wrappers:
  - `_start_answer_writing()`
  - `_start_case_study()`
  - `_get_mains_pyq()`
  - `_get_answer_template()`
  - `_switch_exam_mode()`
- Updated `execute_tool()` fns dict to register the 5 new tools

**`src/bot/groq_tools.py`**
- Added 5 new TOOL_SCHEMAS entries with LLM routing descriptions
- Each tool has explicit "Use when..." and "Do NOT use..." triggers

**`src/bot/handler.py`**
- Added 2 intercept blocks before `run_tool_loop()`:
  - `has_active_answer_writing()` intercept
  - `has_active_case_study()` intercept
- No gating on `_is_answer()` — any text is treated as an answer

**`src/bot/llm.py`**
- Updated SYSTEM_PROMPT to include Mains paper structure (4 papers)
- Yudhister now knows about descriptive/essay evaluation

**`src/bot/quiz.py`**
- Added `HCS_MAINS_TOPICS` dict with all 4 papers (GS1, GS2, GS3, GS4)

---

## Database Schema

### New Table: `mains_answers`

```
id                 bigint PK
chat_id            text (indexed)
topic              text (indexed)
question_text      text
user_answer        text
answer_type        text ('short' | 'medium' | 'essay' | 'case_study')
score_content      int (0–10)
score_structure    int (0–5)
score_examples     int (0–5)
total_score        int (0–20)
max_score          int DEFAULT 20
feedback           text
missing_points     jsonb
attempted_at       timestamptz DEFAULT NOW()
```

### Modified Table: `user_profiles`

New column:
```
exam_mode          text DEFAULT 'prelims'  ('prelims' | 'mains')
```

### Reused: `user_profiles.study_session`

Sessions stored in existing JSONB column, differentiated by mode:
- `mode="answer_writing"` — for answer writing practice
- `mode="case_study"` — for ethics case studies

---

## LLM Prompts

All evaluation uses **Groq Llama 3.3 70B** (free via Groq API).

| Prompt | Tokens | Temperature | Purpose |
|--------|--------|-------------|---------|
| `MAINS_SHORT_PROMPT` | 400 | 0.7 | Generate short-answer question + expected points |
| `MAINS_MEDIUM_PROMPT` | 400 | 0.7 | Generate medium-answer question |
| `MAINS_ESSAY_PROMPT` | 400 | 0.7 | Generate essay question |
| `MAINS_EVAL_PROMPT` | 350 | 0.6 | Evaluate answer → score report |
| `CASE_STUDY_PROMPT` | 500 | 0.8 | Generate ethical dilemma scenario |
| `CASE_STUDY_EVAL_PROMPT` | 400 | 0.6 | Evaluate case study answer |
| `TEMPLATE_PROMPT` | 450 | 0.7 | Generate answer writing template |
| `PYQ_PROMPT` | 500 | 0.7 | Generate Mains-style questions |

---

## Backward Compatibility

✅ **Prelims MCQ mode is untouched.**
- All existing quiz/mock/study tools work exactly as before
- `switch_exam_mode` adds a new column but doesn't break old sessions
- Default is `exam_mode='prelims'` — existing users stay in prelims mode
- Existing state machine intercepts (quiz, mock, study, passage) take priority before Mains intercepts

---

## Testing Checklist

- [ ] Database migrations ran successfully (`mains_answers` table exists)
- [ ] "switch to mains" command works — profile updated
- [ ] "answer writing on [topic] medium" starts a session
- [ ] Can submit an answer — LLM evaluates and saves to `mains_answers`
- [ ] Score report displays correctly (content/structure/examples breakdown)
- [ ] "case study" generates a realistic scenario
- [ ] Ethics case study answer evaluation works
- [ ] "PYQ mains on X" returns questions with outlines
- [ ] "answer template on X" returns structured framework
- [ ] Existing prelims MCQ quiz still works after Mains changes
- [ ] No regression in mock tests or study sessions

---

## Future Enhancements

- [ ] Mains answer analytics: track average scores by topic, identify weak areas
- [ ] Peer review: compare your answer against model answer (currently just score + feedback)
- [ ] Timed essay mode: 45-minute essay writing with countdown timer
- [ ] Mains-specific scheduling: daily essay prompt at fixed time
- [ ] Integration with web search for answer research (get_current_affairs for ethics)
