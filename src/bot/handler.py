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
    "It can be anything — government jobs, entrance exams, school/college exams, certifications, or any competitive exam!"
)

def _extract_exam_from_text(text: str) -> str | None:
    """Use LLM to extract exam name from natural language."""
    from bot.llm import get_client
    client = get_client()
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": (
                    "Extract the exam name the user wants to prepare for. "
                    "It can be ANY exam — government jobs (UPSC, SSC, HCS, IBPS, RAS...), "
                    "entrance tests (JEE, NEET, GATE, CAT, GMAT, GRE, SAT, IELTS, TOEFL...), "
                    "school/college (CBSE, ICSE, IB, A-levels...), certifications (AWS, PMP, CFA...), or anything else. "
                    "Return ONLY a short recognizable exam name or abbreviation. "
                    "Examples: 'Haryana Civil Service' -> 'HCS', 'IAS' -> 'UPSC', "
                    "'AWS Solutions Architect' -> 'AWS-SAA', 'Class 10 boards' -> 'CBSE Class 10'. "
                    "Return ONLY the exam name, nothing else. If unclear, return UNKNOWN."
                )},
                {"role": "user", "content": text}
            ],
            max_tokens=10,
            temperature=0,
        )
        result = response.choices[0].message.content.strip().upper()
        return None if result == "UNKNOWN" or len(result) > 20 else result
    except Exception:
        return None

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

    # Check if user is correcting or switching exam
    lower_text = user_text.lower()
    switching_keywords = ["change exam", "switch to", "preparing for", "switching to",
                          "now preparing", "no no", "actually", "i mean", "want to prepare"]
    if any(k in lower_text for k in switching_keywords):
        new_exam = _extract_exam_from_text(user_text)
        if new_exam:
            save_profile(chat_id, exam=new_exam, onboarded=True)
            reply = f"Got it, switching to *{new_exam}*! 💪 What do you want to start with?"
            save_message(chat_id, "assistant", reply)
            return reply

    parsed  = detect_intent(user_text)
    intent  = parsed.get("intent", "GENERAL")
    # Always prefer stored profile exam; only use detected if explicitly mentioned
    exam    = parsed.get("exam") or profile.get("exam") or "General"
    subject = parsed.get("subject") or ""
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
