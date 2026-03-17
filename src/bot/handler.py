from bot.intent import detect_intent
from bot.rag import retrieve
from bot.llm import chat
from bot.memory import save_message, get_history
from bot.fetcher import search_and_fetch
from bot.quiz import start_quiz, check_answer, stop_quiz, has_active_quiz
from bot.news import get_current_affairs

async def handle_message(chat_id: str, user_text: str) -> str:
    save_message(chat_id, "user", user_text)

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

    parsed  = detect_intent(user_text)
    intent  = parsed.get("intent", "GENERAL")
    exam    = parsed.get("exam") or "HCS"
    subject = parsed.get("subject") or "General Studies"
    year    = parsed.get("year")

    if intent == "QUIZ":
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
