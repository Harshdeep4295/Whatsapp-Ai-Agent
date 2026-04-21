<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

---

## Recent Updates (2026-04-22)

### ✨ Pre-Exam Power Toolkit (3 New Features)

Added three last-hour exam prep tools to help students prepare in ~1 hour before exams:

#### 1. **Crash Course Notes** (`get_crash_course` tool)
- **What:** Generates condensed bullet-point notes on user's 3–4 weakest topics
- **When:** User says "crash course", "exam in 1 hour", "quick revision"
- **How:** Queries `user_progress`, identifies weak topics, LLM generates 8–10 high-yield bullets per topic
- **Implementation:** `src/bot/groq_tools.py` (TOOL_SCHEMAS), `src/bot/tools.py` (_get_crash_course function)

#### 2. **Last-Minute Cheat Sheet** (`get_cheat_sheet` tool)
- **What:** Compact topic-specific revision card with key facts, exam traps, memory tips
- **Smart Caching:** Requests 1–2 return cached version; request 3, 6, 9... generate fresh content with new angle
- **When:** User says "cheat sheet on [topic]", "quick notes for [topic]", "summarize [topic]"
- **Implementation:** `src/bot/groq_tools.py`, `src/bot/tools.py` (_get_cheat_sheet function + _CHEAT_SHEET_PROMPT)
- **Database:** New `quick_notes` table stores (chat_id, topic, content, request_count) with UNIQUE index on (chat_id, topic)

#### 3. **Confidence Booster** (`get_confidence_boost` tool)
- **What:** Warm mentor-style pep talk showing strong topics (≥80% accuracy), exam countdown, exam-day tips
- **When:** User asks "am I ready?", "confidence boost", "how am I doing?"
- **How:** Queries `user_progress` for strong topics, fetches exam countdown from `user_profiles`, LLM writes 5–7 lines of WhatsApp text
- **Implementation:** `src/bot/groq_tools.py`, `src/bot/tools.py` (_get_confidence_boost function)

**Files Modified:**
- `src/bot/groq_tools.py` — Added 3 tool schemas to TOOL_SCHEMAS
- `src/bot/tools.py` — Added 3 tool implementations + registered in execute_tool dispatcher

---

### 🐛 Fix: Scheduled Messages Not Sending (Stats/Streak Messages)

**Root Cause:** When user profiles were created, `last_active_date` was not being set, causing scheduled jobs to skip users (scheduler.py checks if `last_active_date` is within 3 days).

**Fix Applied:**
- Modified `save_profile()` in `src/bot/memory.py` to always set `last_active_date: today` when creating/updating profiles
- This ensures ALL scheduled jobs (nightly revision, morning kickoff, weekly report) run for all active users

**Files Modified:**
- `src/bot/memory.py` — Updated `save_profile()` function (line 24–29)

**Impact:**
- ✅ Users now receive nightly revision messages with streak + stats
- ✅ Morning kickoff messages work for all users
- ✅ Weekly performance reports send correctly
- ✅ Scheduled jobs no longer skip users

---

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
