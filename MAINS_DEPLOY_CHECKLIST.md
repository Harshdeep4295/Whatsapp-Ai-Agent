# HCS Mains Deployment Checklist

## ✅ Code Testing — COMPLETE
All 11 tests passed. Code is production-ready.

---

## Step 1: Database Setup (Run Once in Supabase)

### 1a. Open Supabase Dashboard
- Go to [app.supabase.com](https://app.supabase.com/)
- Select your whatsapp-agent project
- Click **SQL Editor**

### 1b. Run Migration
```sql
-- Copy entire contents of docs/migrations_mains.sql into SQL Editor
-- Then click "Run"
```

**What runs:**
- `ALTER TABLE user_profiles ADD COLUMN exam_mode text DEFAULT 'prelims';`
- `CREATE TABLE mains_answers (...)` with indexes
- Takes ~5 seconds

**Verify Success:**
```sql
-- Run this to confirm tables exist:
SELECT * FROM mains_answers LIMIT 1;
SELECT exam_mode FROM user_profiles LIMIT 1;
```

---

## Step 2: Commit & Deploy

### 2a. Stage Changes
```bash
git add -A
```

### 2b. Verify What's Being Committed
```bash
git status
```

**Expected:**
```
Modified:
  src/bot/groq_tools.py
  src/bot/handler.py
  src/bot/llm.py
  src/bot/quiz.py
  src/bot/tools.py

Untracked files:
  src/bot/mains.py
  docs/MAINS_SETUP.md
  docs/MAINS_DEPLOYMENT.md
  docs/migrations_mains.sql
```

### 2c. Commit
```bash
git commit -m "Add HCS Mains exam prep module — answer writing, case studies, PYQ, templates, mode switch"
```

### 2d. Push to Railway
```bash
git push origin main
```

**Expected:**
- Railway detects push
- Auto-build starts (~2 minutes)
- Bot is live with Mains support

---

## Step 3: Test in WhatsApp

### Test Flow #1: Switch to Mains Mode
```
You: "switch to mains"
Bot: "🎯 *Mains Mode Activated!*... You're now in Mains preparation mode..."
```

### Test Flow #2: Answer Writing
```
You: "answer writing on Panchayati Raj short"
Bot: "📝 *Short Answer — Panchayati Raj*..."
     "[question]"
     "_Word limit: ~100 words_"

You: "[write your answer about panchayati raj]"
Bot: "📝 *Answer Evaluated*"
     "*Content:* 7/10"
     "*Structure:* 3/5"
     "*Examples:* 2/5"
     "*Total: 12/20* (60%)"
```

### Test Flow #3: Case Study
```
You: "case study"
Bot: "⚖️ *Ethics Case Study*"
     "[scenario text]"
     "*Answer these 3 questions:*"

You: "[write your answer]"
Bot: "⚖️ *Case Study Evaluated*"
     "*Issue Identification:* 5/7"
     "*Stakeholder Analysis:* 4/7"
     "*Recommendation Quality:* 3/6"
     "*Total: 12/20*"
```

### Test Flow #4: Answer Template
```
You: "how to answer on Indian Economy"
Bot: "📋 *Answer Template — Indian Economy*"
     "*Opening Line:* ..."
     "*Key Points to Cover:* ..."
```

### Test Flow #5: Previous Year Questions
```
You: "PYQ mains on Environment"
Bot: "📚 *Mains PYQ — Environment*"
     "1. [question]..."
     "Expected Answer Outline:..."
```

### Test Flow #6: Back to Prelims (Verify No Regression)
```
You: "switch to prelims"
Bot: "📝 *Back to Prelims Mode*..."

You: "quiz me"
Bot: "[MCQ question as before]"
```

---

## Step 4: Verify Database Entry

After testing answer writing, verify data was saved:

```sql
-- In Supabase SQL Editor
SELECT chat_id, topic, answer_type, total_score, attempted_at 
FROM mains_answers 
ORDER BY attempted_at DESC 
LIMIT 5;
```

**Expected output:**
```
chat_id  | topic           | answer_type | total_score | attempted_at
---------|-----------------|-------------|-------------|----
12345    | Panchayati Raj  | short       | 12          | 2026-04-30 10:30:00
```

---

## Rollback Plan (If Issues)

If something breaks after deployment:

### Option A: Quick Rollback
```bash
git revert HEAD --no-edit
git push origin main
```
(Railway auto-redeploys with previous version)

### Option B: Keep Database, Revert Code
```bash
# Database changes are permanent (you'll need to remove the column manually if needed)
# But code changes revert immediately
git revert HEAD --no-edit
git push origin main
```

### Option C: Remove Database Changes (if table causes issues)
```sql
-- In Supabase SQL Editor, if needed:
DROP TABLE mains_answers CASCADE;
ALTER TABLE user_profiles DROP COLUMN exam_mode;
```

---

## Success Checklist

- [ ] Database migration ran without errors in Supabase
- [ ] Code committed and pushed to Railway
- [ ] Railway shows "Deployment successful" (check Railway dashboard)
- [ ] "switch to mains" command works in WhatsApp
- [ ] Answer writing practice generates a question
- [ ] Can submit an answer and get a score report
- [ ] Score saved in `mains_answers` table (verify in SQL)
- [ ] Case study generates ethical dilemma
- [ ] PYQ command returns previous year questions
- [ ] Quiz/mock still works (no regression in prelims)

---

## File Locations

| File | Purpose | Editable |
|------|---------|----------|
| `src/bot/mains.py` | All Mains logic | ✓ Code |
| `src/bot/groq_tools.py` | 5 tool schemas | ✓ Code |
| `src/bot/tools.py` | 5 tool wrappers | ✓ Code |
| `src/bot/handler.py` | 2 intercepts | ✓ Code |
| `src/bot/llm.py` | Mains in SYSTEM_PROMPT | ✓ Code |
| `src/bot/quiz.py` | HCS_MAINS_TOPICS dict | ✓ Code |
| `docs/migrations_mains.sql` | Database schema | ✓ SQL (one-time) |
| `docs/MAINS_SETUP.md` | Feature guide | ✓ Docs |
| `docs/MAINS_DEPLOYMENT.md` | Deployment guide | ✓ Docs |
| Supabase `mains_answers` table | Answer history | ✗ Auto (via app) |
| Supabase `user_profiles.exam_mode` | User setting | ✗ Auto (via app) |

---

## Support

### If tests fail after deployment:
1. Check Railway logs: `railway logs --tail 100`
2. Verify database migration: `SELECT * FROM information_schema.columns WHERE table_name='mains_answers';`
3. Check Supabase API health: [status.supabase.com](https://status.supabase.com/)
4. Verify WhatsApp webhook is still connected: [Meta Business Platform](https://business.facebook.com/)

### If you want to customize:
- **Prompts**: Edit `src/bot/mains.py` (lines 103-167)
- **Scoring rubric**: Edit evaluation prompts in mains.py
- **Topics**: Edit `HCS_MAINS_TOPICS` in `src/bot/quiz.py` or `HCS_MAINS_GS*_TOPICS` in `src/bot/mains.py`
- **Tool descriptions**: Edit `src/bot/groq_tools.py` (for LLM routing)

---

## Timeline

| Step | Time | Status |
|------|------|--------|
| Code testing | ~5 min | ✅ DONE |
| Database setup | ~1 min | ⏳ TODO |
| Git commit/push | ~1 min | ⏳ TODO |
| Railway build | ~2 min | ⏳ TODO |
| WhatsApp testing | ~5 min | ⏳ TODO |
| **Total** | **~14 min** | ⏳ READY |

---

**Ready? Run:** `git add -A && git commit -m "..." && git push origin main`
