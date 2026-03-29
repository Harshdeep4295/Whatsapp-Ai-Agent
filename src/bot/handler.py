import re as _re
from bot.groq_tools import run_tool_loop
from bot.memory import (
    save_message, get_history, get_current_topic, set_current_topic,
    update_streak, get_exam_date, _days_until,
)
from config import ADMIN_CHAT_ID
from bot.quiz import (
    has_active_quiz, check_answer, stop_quiz,
    has_active_mock_test, check_mock_answer,
    has_active_study_session, check_study_answer,
    has_active_passage_quiz, check_passage_answer,
)
from bot.whatsapp import send_message

WELCOME_MSG = (
    "Hey! I'm *Yudhister* 👋 Your HCS exam prep buddy.\n\n"
    "I'm here to help you crack the *Haryana Civil Services (HPSC)* exam. "
    "We can do syllabus, practice questions, current affairs, study plans — whatever you need.\n\n"
    "Where do you want to start?"
)

GREETINGS = {"hi", "hello", "hey", "hii", "helo", "helloo", "heyy", "yo", "sup",
             "good morning", "good evening", "good afternoon", "good night",
             "gm", "howdy", "namaste", "namaskar", "hlo", "hola"}

STOP_PHRASES = {"stop", "quit", "end", "end quiz", "stop quiz", "end test", "stop test",
                "end session", "stop session"}


async def _quiz_reply(chat_id: str, text: str, q_data: dict | None) -> None:
    save_message(chat_id, "assistant", text)
    await send_message(chat_id, text)
    if q_data:
        topic = q_data.get("topic", "")
        topic_line = f"_Topic: {topic}_\n\n" if topic else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        q_text = f"{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
        await send_message(chat_id, q_text)


async def handle_message(chat_id: str, sender: str, user_text: str, is_group: bool = False) -> str | None:
    save_message(chat_id, "user", user_text)
    update_streak(chat_id)
    lower = user_text.strip().lower()

    # --- Admin nuclear reset (Harshdeep only) ---
    if lower == "yudhister nuke" and ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID:
        from bot.supabase_client import get_sb
        sb = get_sb()
        sb.table("conversations").delete().eq("chat_id", chat_id).execute()
        sb.table("quiz_sessions").delete().eq("chat_id", chat_id).execute()
        sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
        sb.table("scheduled_jobs").update({"active": False}).eq("chat_id", chat_id).execute()
        sb.table("user_answer_history").delete().eq("chat_id", chat_id).execute()
        sb.table("user_progress").delete().eq("chat_id", chat_id).execute()
        sb.table("user_profiles").update({
            "current_topic": None,
            "study_session": None,
            "exam_date": None,
            "study_streak": 0,
            "last_active_date": None,
        }).eq("chat_id", chat_id).execute()
        set_current_topic(chat_id, None)
        msg = (
            "💣 *Nuclear reset complete.*\n\n"
            "Cleared:\n"
            "✅ All conversations\n"
            "✅ All quiz & mock test sessions\n"
            "✅ All scheduled jobs\n"
            "✅ All answer history\n"
            "✅ All progress stats\n"
            "✅ Profile (streak, exam date, topic)\n\n"
            "Fresh start. Say *hi* to begin."
        )
        save_message(chat_id, "assistant", msg)
        return msg

    # --- Reset ---
    if "clear all my session" in lower:
        from bot.supabase_client import get_sb
        sb = get_sb()
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
            # Auto-schedule nightly revision at 10 PM IST (16:30 UTC) for new users.
            # schedule_job deactivates any existing same-type job first, so re-onboarding
            # won't create duplicates.
            try:
                from bot.scheduler import schedule_job, _next_1630_utc
                schedule_job(chat_id, "nightly_revision", 1440, next_run_at=_next_1630_utc())
            except Exception as e:
                print(f"[handler] failed to auto-schedule nightly_revision for {chat_id}: {e}")
            return WELCOME_MSG
        try:
            from bot.supabase_client import get_sb
            from bot.memory import get_profile
            _sb = get_sb()
            profile = get_profile(chat_id)
            streak = profile.get("study_streak") or 0
            streak_line = f"Day *{streak}* streak 🔥  " if streak >= 2 else ""

            prog_res = _sb.table("user_progress").select("topic,correct,total")\
                .eq("chat_id", chat_id).order("total", desc=True).execute()
            weak_line = ""
            if prog_res.data:
                weak = [(r["topic"], r["correct"] / r["total"]) for r in prog_res.data if r["total"] >= 2]
                if weak:
                    worst = min(weak, key=lambda x: x[1])
                    pct = int(worst[1] * 100)
                    weak_line = f"\n\n📊 *Focus today:* {worst[0]} ({pct}% accuracy) — say *study {worst[0]}* to drill it."
            countdown_line = ""
            try:
                exam_date = get_exam_date(chat_id)
                if exam_date:
                    days = _days_until(exam_date)
                    if days == 0:
                        countdown_line = "\n\n🎯 *Today is your HCS exam day! All the best!*"
                    elif days is not None:
                        countdown_line = f"\n\n⏳ *{days} days left* until your HCS exam ({exam_date})."
            except Exception:
                countdown_line = ""
            reply = f"Hey! 👋 {streak_line}Good to see you back.\n\nWhat do you need — quiz, mock test, syllabus, current affairs, or study plan?{weak_line}{countdown_line}"
        except Exception:
            reply = "Hey! 👋 Good to see you again. Ready to continue HCS prep?\n\nWhat do you need — quiz, mock test, syllabus, current affairs, or study plan?"
        save_message(chat_id, "assistant", reply)
        return reply

    def _is_answer(text: str) -> bool:
        t = text.strip().lower()
        return (
            len(t) <= 2
            or t in ["a", "b", "c", "d"]
            or bool(_re.match(r'^[a-d][\.\s]', t))
            or bool(_re.search(r'\bq\d+[\.\s]', t))
        )

    # --- Active mock test intercept ---
    if has_active_mock_test(chat_id):
        if lower in STOP_PHRASES:
            from bot.supabase_client import get_sb
            get_sb().table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
            await _quiz_reply(chat_id, "Mock test ended.", None)
            return None
        if _is_answer(user_text):
            # Batch answers: "Q1 C...\nQ2 B..." — extract each and process sequentially
            batch = _re.findall(r'q\d+[.\s]+([a-d])', lower)
            if batch:
                for ans in batch:
                    text, q_data = check_mock_answer(chat_id, ans)
                    await _quiz_reply(chat_id, text, q_data)
                    if q_data is None:
                        break
            else:
                await _quiz_reply(chat_id, *check_mock_answer(chat_id, user_text))
            return None

    # --- Active passage quiz intercept ---
    if has_active_passage_quiz(chat_id):
        if lower in STOP_PHRASES:
            from bot.memory import set_study_session
            set_study_session(chat_id, None)
            set_current_topic(chat_id, None)
            await _quiz_reply(chat_id, "Passage quiz ended.", None)
            return None
        if _is_answer(user_text):
            await _quiz_reply(chat_id, *check_passage_answer(chat_id, user_text))
            return None

    # --- Active study session intercept ---
    if has_active_study_session(chat_id):
        if lower in STOP_PHRASES:
            from bot.memory import set_study_session
            set_study_session(chat_id, None)
            set_current_topic(chat_id, None)
            await _quiz_reply(chat_id, "Study session ended.", None)
            return None
        if _is_answer(user_text):
            await _quiz_reply(chat_id, *check_study_answer(chat_id, user_text))
            return None

    # --- Mid-quiz intercept ---
    if has_active_quiz(chat_id):
        if lower in STOP_PHRASES:
            await _quiz_reply(chat_id, *stop_quiz(chat_id))
            return None
        if _is_answer(user_text):
            await _quiz_reply(chat_id, *check_answer(chat_id, user_text))
            return None

    # --- Tool loop ---
    reply = await run_tool_loop(chat_id, user_text)
    save_message(chat_id, "assistant", reply)
    return reply
