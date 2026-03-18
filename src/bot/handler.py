import re
from bot.intent import detect_intent
from bot.rag import retrieve
from bot.llm import chat
from bot.memory import save_message, get_history, get_current_topic, set_current_topic
from bot.fetcher import search_and_fetch
from bot.quiz import (
    start_quiz, check_answer, stop_quiz, has_active_quiz,
    start_mock_test, check_mock_answer, has_active_mock_test,
    start_study_session, check_study_answer, has_active_study_session,
)
from bot.news import get_current_affairs
from bot.scheduler import schedule_job, cancel_jobs, parse_interval, JOB_TYPES

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


async def handle_message(chat_id: str, sender: str, user_text: str, is_group: bool = False) -> str:
    save_message(chat_id, "user", user_text)
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
            reply = "Mock test ended."
            save_message(chat_id, "assistant", reply)
            return reply
        if len(lower) <= 2 or lower in ["a", "b", "c", "d"]:
            reply = check_mock_answer(chat_id, user_text)
            save_message(chat_id, "assistant", reply)
            return reply

    # --- Active study session intercept ---
    if has_active_study_session(chat_id):
        if lower in STOP_PHRASES:
            from bot.memory import set_study_session
            set_study_session(chat_id, None)
            set_current_topic(chat_id, None)
            reply = "Study session ended."
            save_message(chat_id, "assistant", reply)
            return reply
        if len(lower) <= 2 or lower in ["a", "b", "c", "d"]:
            reply = check_study_answer(chat_id, user_text)
            save_message(chat_id, "assistant", reply)
            return reply

    # --- Mid-quiz intercept ---
    if has_active_quiz(chat_id):
        if lower in STOP_PHRASES:
            reply = stop_quiz(chat_id)
            save_message(chat_id, "assistant", reply)
            return reply
        if len(lower) <= 2 or lower in ["a", "b", "c", "d"]:
            reply = check_answer(chat_id, user_text)
            save_message(chat_id, "assistant", reply)
            return reply

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
        else:
            job_type = JOB_TYPES.get(subject.lower(), "current_affairs")
        reply = schedule_job(chat_id, job_type, interval, EXAM, subject)

    elif intent == "CANCEL_SCHEDULE":
        reply = cancel_jobs(chat_id)

    elif intent == "MOCK_TEST":
        n = _parse_mock_count(user_text, parsed.get("count"))
        reply = start_mock_test(chat_id, n)

    elif intent == "STUDY_SESSION":
        topic = subject or "General Studies"
        set_current_topic(chat_id, topic)
        reply = start_study_session(chat_id, topic)

    elif intent == "QUIZ":
        if subject:
            set_current_topic(chat_id, subject)
        reply = start_quiz(chat_id, EXAM, subject)

    elif intent == "NEWS":
        reply, _ = get_current_affairs(EXAM)
        if not reply:
            reply = "Couldn't fetch news right now. Try again in a bit!"

    elif intent in ("SYLLABUS", "PAPER"):
        ctype = "syllabus" if intent == "SYLLABUS" else "paper"
        search_and_fetch(EXAM, ctype, subject, year)
        context = retrieve(user_text)
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        depth = "full" if subject else "short"
        reply = chat(messages, context=context, depth=depth, current_topic=current_topic)

    elif intent == "EXPLAIN":
        context = retrieve(user_text)
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        is_expanding = any(p in lower for p in EXPAND_PHRASES)
        reply = chat(messages, context=context, depth="full" if is_expanding else "short",
                     current_topic=current_topic)

    elif intent == "STUDY_PLAN":
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, depth="full", current_topic=current_topic)

    else:  # GENERAL — continue conversation naturally
        is_expanding = any(p in lower for p in EXPAND_PHRASES)
        context = retrieve(user_text) if len(user_text) > 10 else ""
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, context=context, depth="full" if is_expanding else "short",
                     current_topic=current_topic)

    save_message(chat_id, "assistant", reply)
    return reply
