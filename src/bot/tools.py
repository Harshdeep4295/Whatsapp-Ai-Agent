from bot.whatsapp import send_message, send_interactive_quiz
from bot.memory import save_message


async def execute_tool(name: str, inputs: dict, chat_id: str) -> str:
    fns = {
        "start_quiz": _start_quiz,
        "start_mock_test": _start_mock_test,
        "start_study_session": _start_study_session,
        "get_current_affairs": _get_current_affairs,
        "get_syllabus_or_paper": _get_syllabus_or_paper,
        "get_user_progress": _get_user_progress,
        "schedule_updates": _schedule_updates,
        "cancel_scheduled_updates": _cancel_scheduled_updates,
    }
    fn = fns.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return await fn(chat_id=chat_id, **inputs)
    except Exception as e:
        return f"Tool error: {e}"


async def _start_quiz(chat_id: str, subject: str = None) -> str:
    from bot.quiz import start_batch_quiz
    text, q_data = start_batch_quiz(chat_id, 5)
    save_message(chat_id, "assistant", text)
    await send_message(chat_id, text)
    if q_data:
        await send_interactive_quiz(chat_id, q_data["question"], q_data["options"], q_data.get("topic", ""))
    return "Quiz started — 5 questions sent to user."


async def _start_mock_test(chat_id: str, question_count: int = 10) -> str:
    from bot.quiz import start_mock_test
    text, q_data = start_mock_test(chat_id, question_count)
    save_message(chat_id, "assistant", text)
    await send_message(chat_id, text)
    if q_data:
        await send_interactive_quiz(chat_id, q_data["question"], q_data["options"], q_data.get("topic", ""))
    return f"Mock test started — {question_count} questions."


async def _start_study_session(chat_id: str, topic: str) -> str:
    from bot.quiz import start_study_session
    from bot.memory import set_current_topic
    set_current_topic(chat_id, topic)
    text, q_data = start_study_session(chat_id, topic)
    save_message(chat_id, "assistant", text)
    await send_message(chat_id, text)
    if q_data:
        await send_interactive_quiz(chat_id, q_data["question"], q_data["options"], q_data.get("topic", ""))
    return f"Study session on '{topic}' started."


async def _get_current_affairs(chat_id: str) -> str:
    from bot.news import get_current_affairs
    summary, _, _ = get_current_affairs("HCS")
    if not summary:
        return "Couldn't fetch news right now. Try again in a bit!"
    return summary


async def _get_syllabus_or_paper(chat_id: str, content_type: str, subject: str = "", year: int = None) -> str:
    from bot.fetcher import search_and_fetch
    from bot.rag import retrieve
    search_and_fetch("HCS", content_type, subject, year)
    context = retrieve(f"HCS {content_type} {subject}")
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
    return context


async def _get_user_progress(chat_id: str) -> str:
    try:
        from bot.supabase_client import get_sb
        from bot.memory import get_profile
        _sb = get_sb()
        profile = get_profile(chat_id)
        streak = profile.get("study_streak") or 0

        res = _sb.table("user_progress").select("topic,correct,total")\
            .eq("chat_id", chat_id).execute()
        rows = res.data or []

        if not rows:
            return "You haven't done any quizzes yet!\n\nSay *quiz me* to start — I'll track your progress from here."

        total_q = sum(r["total"] for r in rows)
        total_c = sum(r["correct"] for r in rows)
        overall = int(total_c / total_q * 100) if total_q else 0

        strong = [r for r in rows if r["total"] >= 2 and r["correct"] / r["total"] > 0.8]
        weak = [r for r in rows if r["total"] >= 2 and r["correct"] / r["total"] < 0.6]
        mid = [r for r in rows if r["total"] >= 2 and 0.6 <= r["correct"] / r["total"] <= 0.8]

        def fmt_topic(r):
            return f"{r['topic']} ({int(r['correct'] / r['total'] * 100)}%)"

        streak_line = f"🔥 *Streak:* {streak} day{'s' if streak != 1 else ''}\n" if streak else ""
        strong_line = f"\n✅ *Strong:* {', '.join(fmt_topic(r) for r in sorted(strong, key=lambda x: -x['correct'] / x['total'])[:3])}" if strong else ""
        mid_line = f"\n📖 *Improving:* {', '.join(fmt_topic(r) for r in mid[:3])}" if mid else ""
        weak_line = f"\n⚠️ *Needs work:* {', '.join(fmt_topic(r) for r in sorted(weak, key=lambda x: x['correct'] / x['total'])[:3])}" if weak else ""

        return (
            f"📊 *Your HCS Progress*\n\n"
            f"{streak_line}"
            f"*Overall accuracy:* {total_c}/{total_q} ({overall}%)"
            f"{strong_line}{mid_line}{weak_line}\n\n"
            f"_Say *quiz me* to practice weak topics, or *nightly revision* to schedule a daily recap._"
        )
    except Exception:
        return "Couldn't load your progress right now. Try again in a moment."


async def _schedule_updates(chat_id: str, job_type: str, interval_text: str) -> str:
    from bot.scheduler import schedule_job, parse_interval
    interval = parse_interval(interval_text)
    return schedule_job(chat_id, job_type, interval, "HCS")


async def _cancel_scheduled_updates(chat_id: str) -> str:
    from bot.scheduler import cancel_jobs
    return cancel_jobs(chat_id)
