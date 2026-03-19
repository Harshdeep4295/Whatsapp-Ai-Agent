import re
from bot.intent import detect_intent
from bot.rag import retrieve
from bot.llm import chat
from bot.memory import save_message, get_history, get_current_topic, set_current_topic, update_streak
from bot.fetcher import search_and_fetch
from bot.quiz import (
    start_quiz, check_answer, stop_quiz, has_active_quiz,
    start_batch_quiz, start_mock_test, check_mock_answer, has_active_mock_test,
    start_study_session, check_study_answer, has_active_study_session,
)
from bot.news import get_current_affairs
from bot.scheduler import schedule_job, cancel_jobs, parse_interval, JOB_TYPES
from bot.whatsapp import send_message, send_interactive_quiz

EXAM = "HCS"  # Hardcoded — this bot is for HCS only

WELCOME_MSG = (
    "Hey! I'm *Yudhister* 👋 Your HCS exam prep buddy.\n\n"
    "I'm here to help you crack the *Haryana Civil Services (HPSC)* exam. "
    "We can do syllabus, practice questions, current affairs, study plans — whatever you need.\n\n"
    "Where do you want to start?"
)

GREETINGS = {"hi", "hello", "hey", "hii", "helo", "helloo", "heyy", "yo", "sup",
             "good morning", "good evening", "good afternoon", "good night",
             "gm", "howdy", "namaste", "namaskar", "hlo", "hola"}

EXPAND_PHRASES = {"tell me more", "explain more", "elaborate", "in detail", "more about",
                  "expand", "deep dive", "go on", "what else", "explain further",
                  "keep going", "and then", "then what", "continue"}

STOP_PHRASES = {"stop", "quit", "end", "end quiz", "stop quiz", "end test", "stop test",
                "end session", "stop session"}


def _parse_mock_count(text: str, parsed_count) -> int:
    """Extract number of questions from text, fall back to parsed intent count, default 10."""
    if parsed_count and isinstance(parsed_count, int) and 1 <= parsed_count <= 50:
        return parsed_count
    m = re.search(r'(\d+)\s*(?:question|q)', text.lower())
    if m:
        n = int(m.group(1))
        return max(1, min(n, 50))
    return 10


async def _quiz_reply(chat_id: str, text: str, q_data: dict | None) -> None:
    """Send quiz feedback as text, then question as interactive list if present. Returns None."""
    save_message(chat_id, "assistant", text)
    await send_message(chat_id, text)
    if q_data:
        await send_interactive_quiz(chat_id, q_data["question"], q_data["options"], q_data.get("topic", ""))


async def handle_message(chat_id: str, sender: str, user_text: str, is_group: bool = False) -> str | None:
    save_message(chat_id, "user", user_text)
    update_streak(chat_id)
    lower = user_text.strip().lower()

    # --- Reset ---
    if "clear all my session" in lower:
        from supabase import create_client
        from config import SUPABASE_URL, SUPABASE_KEY
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        sb.table("conversations").delete().eq("chat_id", chat_id).execute()
        sb.table("quiz_sessions").delete().eq("chat_id", chat_id).execute()
        sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
        sb.table("scheduled_jobs").update({"active": False}).eq("chat_id", chat_id).execute()
        set_current_topic(chat_id, None)
        save_message(chat_id, "assistant", WELCOME_MSG)
        return WELCOME_MSG

    # --- Greeting ---
    if lower in GREETINGS or lower.rstrip("!") in GREETINGS:
        history = get_history(chat_id)
        if not history:
            save_message(chat_id, "assistant", WELCOME_MSG)
            return WELCOME_MSG
        try:
            from supabase import create_client
            from config import SUPABASE_URL, SUPABASE_KEY
            from bot.memory import get_profile
            _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            profile = get_profile(chat_id)
            streak = profile.get("study_streak") or 0
            streak_line = f"Day *{streak}* streak 🔥  " if streak >= 2 else ""

            prog_res = _sb.table("user_progress").select("topic,correct,total")\
                .eq("chat_id", chat_id).order("total", desc=True).execute()
            weak_line = ""
            if prog_res.data:
                weak = [(r["topic"], r["correct"]/r["total"]) for r in prog_res.data if r["total"] >= 2]
                if weak:
                    worst = min(weak, key=lambda x: x[1])
                    pct = int(worst[1] * 100)
                    weak_line = f"\n\n📊 *Focus today:* {worst[0]} ({pct}% accuracy) — say *study {worst[0]}* to drill it."
            reply = f"Hey! 👋 {streak_line}Good to see you back.\n\nWhat do you need — quiz, mock test, syllabus, current affairs, or study plan?{weak_line}"
        except Exception:
            reply = "Hey! 👋 Good to see you again. Ready to continue HCS prep?\n\nWhat do you need — quiz, mock test, syllabus, current affairs, or study plan?"
        save_message(chat_id, "assistant", reply)
        return reply

    # --- Active mock test intercept ---
    if has_active_mock_test(chat_id):
        if lower in STOP_PHRASES:
            from supabase import create_client
            from config import SUPABASE_URL, SUPABASE_KEY
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
            await _quiz_reply(chat_id, "Mock test ended.", None)
            return None
        if len(lower) <= 2 or lower in ["a", "b", "c", "d"]:
            await _quiz_reply(chat_id, *check_mock_answer(chat_id, user_text))
            return None

    # --- Active study session intercept ---
    if has_active_study_session(chat_id):
        if lower in STOP_PHRASES:
            from bot.memory import set_study_session
            set_study_session(chat_id, None)
            set_current_topic(chat_id, None)
            await _quiz_reply(chat_id, "Study session ended.", None)
            return None
        if len(lower) <= 2 or lower in ["a", "b", "c", "d"]:
            await _quiz_reply(chat_id, *check_study_answer(chat_id, user_text))
            return None

    # --- Mid-quiz intercept ---
    if has_active_quiz(chat_id):
        if lower in STOP_PHRASES:
            await _quiz_reply(chat_id, *stop_quiz(chat_id))
            return None
        if len(lower) <= 2 or lower in ["a", "b", "c", "d"]:
            await _quiz_reply(chat_id, *check_answer(chat_id, user_text))
            return None

    # --- Intent detection ---
    parsed = detect_intent(user_text)
    intent = parsed.get("intent", "GENERAL")
    subject = parsed.get("subject") or ""
    year = parsed.get("year")
    current_topic = get_current_topic(chat_id)

    # --- Route ---
    if intent == "SCHEDULE":
        schedule_text = parsed.get("schedule_text") or user_text
        interval = parse_interval(schedule_text)
        full_lower = user_text.lower()
        if any(k in full_lower for k in ["practice", "question", "quiz", "mcq", "test"]):
            job_type = "quiz"
        elif any(k in full_lower for k in ["news", "current affairs", "update", "headlines"]):
            job_type = "current_affairs"
        elif any(k in full_lower for k in ["report", "performance", "weekly"]):
            job_type = "weekly_report"
        elif any(k in full_lower for k in ["nightly", "revision", "recap", "daily revision"]):
            job_type = "nightly_revision"
        else:
            job_type = JOB_TYPES.get(subject.lower(), "current_affairs")
        reply = schedule_job(chat_id, job_type, interval, EXAM, subject)

    elif intent == "CANCEL_SCHEDULE":
        reply = cancel_jobs(chat_id)

    elif intent == "MOCK_TEST":
        n = _parse_mock_count(user_text, parsed.get("count"))
        await _quiz_reply(chat_id, *start_mock_test(chat_id, n))
        return None

    elif intent == "STUDY_SESSION":
        topic = subject or "General Studies"
        set_current_topic(chat_id, topic)
        await _quiz_reply(chat_id, *start_study_session(chat_id, topic))
        return None

    elif intent == "QUIZ":
        if subject:
            set_current_topic(chat_id, subject)
        # Default: send 5 questions at once as a numbered list
        await _quiz_reply(chat_id, *start_batch_quiz(chat_id, 5))
        return None

    elif intent == "NEWS":
        reply, _, _ = get_current_affairs(EXAM)
        if not reply:
            reply = "Couldn't fetch news right now. Try again in a bit!"

    elif intent in ("SYLLABUS", "PAPER"):
        ctype = "syllabus" if intent == "SYLLABUS" else "paper"
        search_and_fetch(EXAM, ctype, subject, year)
        context = retrieve(user_text)
        if not context:
            context = (
                "HCS Prelims Paper 1 GS (100 marks): Indian History & Culture, Haryana History & Culture, "
                "Indian Geography, Haryana Geography, Indian Polity & Constitution, Panchayati Raj, "
                "Indian Economy, Haryana Economy & Agriculture, Science & Technology, Environment & Ecology, "
                "Current Affairs, Important Govt Schemes. "
                "Paper 2 CSAT (80 marks): Reading Comprehension, Logical Reasoning, Analytical Ability, "
                "Data Interpretation, Basic Numeracy, Decision Making. "
                "Haryana-specific content is ~30% of GS — History, Geography, Economy, Culture, Art, Personalities."
            )
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, context=context, depth="full", current_topic=current_topic)

    elif intent == "EXPLAIN":
        context = retrieve(user_text)
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, context=context, depth="full", current_topic=current_topic)
        reply += "\n\n_Want a quick MCQ on this to test yourself? Say *quiz me* or yes._"

    elif intent == "STUDY_PLAN":
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, depth="full", current_topic=current_topic)

    elif intent == "PROGRESS":
        try:
            from supabase import create_client
            from config import SUPABASE_URL, SUPABASE_KEY
            from bot.memory import get_profile
            _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            profile = get_profile(chat_id)
            streak = profile.get("study_streak") or 0

            res = _sb.table("user_progress").select("topic,correct,total")\
                .eq("chat_id", chat_id).execute()
            rows = res.data or []

            if not rows:
                reply = "You haven't done any quizzes yet!\n\nSay *quiz me* to start — I'll track your progress from here."
            else:
                total_q = sum(r["total"] for r in rows)
                total_c = sum(r["correct"] for r in rows)
                overall = int(total_c / total_q * 100) if total_q else 0

                strong = [r for r in rows if r["total"] >= 2 and r["correct"]/r["total"] > 0.8]
                weak = [r for r in rows if r["total"] >= 2 and r["correct"]/r["total"] < 0.6]
                mid = [r for r in rows if r["total"] >= 2 and 0.6 <= r["correct"]/r["total"] <= 0.8]

                def fmt_topic(r):
                    return f"{r['topic']} ({int(r['correct']/r['total']*100)}%)"

                streak_line = f"🔥 *Streak:* {streak} day{'s' if streak != 1 else ''}\n" if streak else ""
                strong_line = f"\n✅ *Strong:* {', '.join(fmt_topic(r) for r in sorted(strong, key=lambda x: -x['correct']/x['total'])[:3])}" if strong else ""
                mid_line = f"\n📖 *Improving:* {', '.join(fmt_topic(r) for r in mid[:3])}" if mid else ""
                weak_line = f"\n⚠️ *Needs work:* {', '.join(fmt_topic(r) for r in sorted(weak, key=lambda x: x['correct']/x['total'])[:3])}" if weak else ""

                reply = (
                    f"📊 *Your HCS Progress*\n\n"
                    f"{streak_line}"
                    f"*Overall accuracy:* {total_c}/{total_q} ({overall}%)"
                    f"{strong_line}{mid_line}{weak_line}\n\n"
                    f"_Say *quiz me* to practice weak topics, or *nightly revision* to schedule a daily recap._"
                )
        except Exception as e:
            reply = "Couldn't load your progress right now. Try again in a moment."

    else:  # GENERAL — continue conversation naturally
        is_expanding = any(p in lower for p in EXPAND_PHRASES)
        context = retrieve(user_text) if len(user_text) > 10 else ""
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, context=context, depth="full" if is_expanding else "short",
                     current_topic=current_topic)

    save_message(chat_id, "assistant", reply)
    return reply
