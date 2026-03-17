from bot.intent import detect_intent
from bot.rag import retrieve
from bot.llm import chat
from bot.memory import save_message, get_history, get_profile, save_profile
from bot.fetcher import search_and_fetch
from bot.quiz import start_quiz, check_answer, stop_quiz, has_active_quiz
from bot.news import get_current_affairs
from bot.scheduler import schedule_job, cancel_jobs, parse_interval, JOB_TYPES

ONBOARDING_MSG = (
    "Hey! I'm *Yudhister*, your exam prep buddy 👋\n\n"
    "Which exam are you preparing for? "
    "(e.g. HCS, UPSC, SSC, IBPS, CBSE, RAS, or anything else)"
)

def _extract_exam_from_text(text: str) -> str | None:
    """Quick keyword check for known exams in onboarding reply."""
    known = ["upsc", "hcs", "ssc", "ibps", "ras", "ias", "neet", "jee",
             "cbse", "rrb", "ctet", "gate", "cat", "clat", "nda", "cds"]
    lower = text.lower()
    for e in known:
        if e in lower:
            return e.upper()
    # If user typed something custom (any word 2+ chars), trust it
    words = [w.strip(".,!?") for w in text.split() if len(w.strip(".,!?")) >= 2]
    return words[0].upper() if words else None

async def handle_message(chat_id: str, sender: str, user_text: str, is_group: bool = False) -> str:
    # In groups, track conversation per group but attribute to sender
    # In DMs, chat_id == sender
    display_name = sender if is_group else None
    save_message(chat_id, "user", user_text)

    # Reset command — clears everything and restarts onboarding
    if "clear all my session" in user_text.strip().lower():
        from supabase import create_client
        from config import SUPABASE_URL, SUPABASE_KEY
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        sb.table("conversations").delete().eq("chat_id", chat_id).execute()
        sb.table("user_profiles").delete().eq("chat_id", chat_id).execute()
        sb.table("quiz_sessions").delete().eq("chat_id", chat_id).execute()
        sb.table("scheduled_jobs").update({"active": False}).eq("chat_id", chat_id).execute()
        save_message(chat_id, "assistant", ONBOARDING_MSG)
        return ONBOARDING_MSG

    # In groups: skip onboarding, use group-level profile
    if is_group:
        profile = get_profile(chat_id)
        if not profile["onboarded"]:
            history = get_history(chat_id)
            already_asked = any(ONBOARDING_MSG[:30] in m.get("content", "") for m in history if m["role"] == "assistant")
            if not already_asked:
                save_message(chat_id, "assistant", ONBOARDING_MSG)
                return ONBOARDING_MSG
            else:
                exam_guess = _extract_exam_from_text(user_text)
                if not exam_guess:
                    p = detect_intent(user_text)
                    exam_guess = p.get("exam")
                if exam_guess:
                    save_profile(chat_id, exam=exam_guess, onboarded=True)
                    reply = f"Got it! This group is prepping for *{exam_guess}* 💪 What do you need first?"
                    save_message(chat_id, "assistant", reply)
                    return reply
                else:
                    reply = "Which exam is this group preparing for? (e.g. UPSC, HCS, SSC)"
                    save_message(chat_id, "assistant", reply)
                    return reply

    # Mid-quiz: intercept answers and stop commands first
    if has_active_quiz(chat_id):
        lower = user_text.strip().lower()
        if lower in ["stop", "quit", "end", "end quiz", "stop quiz"]:
            reply = stop_quiz(chat_id)
            save_message(chat_id, "assistant", reply)
            return reply
        if len(lower) <= 3 or lower in ["a", "b", "c", "d"]:
            reply = check_answer(chat_id, user_text)
            save_message(chat_id, "assistant", reply)
            return reply

    # Onboarding: ask exam on first message
    profile = get_profile(chat_id)
    if not profile["onboarded"]:
        history = get_history(chat_id)
        # Check if we already asked the onboarding question (it'll be in history)
        already_asked = any(ONBOARDING_MSG[:30] in m.get("content", "") for m in history if m["role"] == "assistant")
        if not already_asked:
            save_message(chat_id, "assistant", ONBOARDING_MSG)
            return ONBOARDING_MSG
        else:
            # User is replying with their exam — try to detect it
            exam_guess = _extract_exam_from_text(user_text)
            if not exam_guess:
                # Try intent detection as fallback
                p = detect_intent(user_text)
                exam_guess = p.get("exam")
            if exam_guess:
                save_profile(chat_id, exam=exam_guess, onboarded=True)
                reply = (
                    f"Got it! Preparing for *{exam_guess}* 💪\n\n"
                    f"I'll tailor everything for {exam_guess} from now on. "
                    f"What do you want to start with? Syllabus, a quiz, current affairs, or something else?"
                )
                save_message(chat_id, "assistant", reply)
                return reply
            else:
                reply = "I didn't catch that — which exam are you preparing for? (e.g. UPSC, HCS, SSC, IBPS)"
                save_message(chat_id, "assistant", reply)
                return reply

    # Check if user is switching exam
    parsed_check = detect_intent(user_text)
    detected_exam = parsed_check.get("exam")
    lower_text = user_text.lower()
    switching_keywords = ["change exam", "switch to", "preparing for", "switching to", "now preparing"]
    if detected_exam and any(k in lower_text for k in switching_keywords):
        save_profile(chat_id, exam=detected_exam, onboarded=True)
        reply = f"Switched to *{detected_exam}*! Let's crush it. What do you need first?"
        save_message(chat_id, "assistant", reply)
        return reply

    parsed  = detect_intent(user_text)
    intent  = parsed.get("intent", "GENERAL")
    # Use stored exam if intent didn't pick one up, else use detected
    exam    = parsed.get("exam") or profile.get("exam") or "HCS"
    subject = parsed.get("subject") or "General Studies"
    year    = parsed.get("year")

    if intent == "SCHEDULE":
        schedule_text = parsed.get("schedule_text") or user_text
        interval = parse_interval(schedule_text)
        job_type = JOB_TYPES.get(subject.lower(), "current_affairs")
        reply = schedule_job(chat_id, job_type, interval, exam, subject)

    elif intent == "CANCEL_SCHEDULE":
        reply = cancel_jobs(chat_id)

    elif intent == "QUIZ":
        reply = start_quiz(chat_id, exam, subject)

    elif intent == "NEWS":
        reply = get_current_affairs(exam)

    elif intent in ("SYLLABUS", "PAPER"):
        ctype = "syllabus" if intent == "SYLLABUS" else "paper"
        search_and_fetch(exam, ctype, subject, year)
        context = retrieve(user_text)
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, context=context)

    elif intent == "STUDY_PLAN":
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages)

    else:  # EXPLAIN, GENERAL, ANSWER fallback
        context = retrieve(user_text)
        history = get_history(chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        reply = chat(messages, context=context)

    save_message(chat_id, "assistant", reply)
    return reply
