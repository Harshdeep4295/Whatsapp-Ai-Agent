async def _get_crash_course(chat_id: str) -> str:
    from bot.supabase_client import get_sb
    from bot.llm import create_completion
    from bot.whatsapp import send_message

    sb = get_sb()

    res = sb.table("user_progress").select("topic,correct,total") \
        .eq("chat_id", chat_id).execute()
    rows = sorted(res.data or [], key=lambda r: r["correct"] / r["total"])
    weak_topics = [r["topic"] for r in rows[:4]] or ["Indian Polity", "History", "Geography", "Economy"]

    topic_list = ", ".join(weak_topics)
    prompt = (
        f"You are Yudhister, an HCS exam expert. A student has 1 hour before their exam.\n"
        f"Their weakest topics are: {topic_list}.\n\n"
        f"For each topic, write 8-10 bullet points covering the most important, high-yield facts "
        f"that appear most frequently in HCS exams. Be concise — each bullet must be under 15 words. "
        f"Format:\n*[Topic Name]*\n• fact\n• fact\n...\n\n"
        f"Start directly with the first topic. No intro text."
    )
    notes = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700,
        temperature=0.6,
    )

    header = "📋 *Crash Course — Your Weak Topics*\n_(High-yield facts only — 1 hour to exam!)_\n\n"
    await send_message(chat_id, header + notes.strip())
    return "Crash course notes delivered to user."


_CHEAT_SHEET_PROMPT = (
    "You are Yudhister, an HCS exam expert. Create a cheat sheet for: {topic}.\n"
    "Format:\n"
    "*{topic} — Quick Notes*\n"
    "Key Facts:\n• ...\n• ...\n"
    "Common Exam Traps:\n• ...\n"
    "Remember:\n• ...\n\n"
    "Rules: Max 15 words per bullet. No padding or intro. Exam-focused only."
)


async def _get_cheat_sheet(chat_id: str, topic: str) -> str:
    from bot.supabase_client import get_sb
    from bot.llm import create_completion
    from bot.whatsapp import send_message

    sb = get_sb()

    res = sb.table("quick_notes").select("content,request_count") \
        .eq("chat_id", chat_id).eq("topic", topic).execute()
    row = res.data[0] if res.data else None

    if row:
        count = row["request_count"] + 1
        is_refresh = (count % 3 == 0)
    else:
        count = 1
        is_refresh = True

    if is_refresh:
        content = create_completion(
            messages=[{"role": "user", "content": _CHEAT_SHEET_PROMPT.format(topic=topic)}],
            max_tokens=450,
            temperature=0.85,
        )
        content = content.strip()
        sb.table("quick_notes").upsert({
            "chat_id": chat_id,
            "topic": topic,
            "content": content,
            "request_count": count,
        }, on_conflict="chat_id,topic").execute()
    else:
        content = row["content"]
        sb.table("quick_notes").update({"request_count": count}) \
            .eq("chat_id", chat_id).eq("topic", topic).execute()

    tag = "\n\n_🔄 Fresh version!_" if is_refresh and count > 1 else ""
    await send_message(chat_id, content + tag)
    return "Cheat sheet delivered to user."


async def _get_confidence_boost(chat_id: str) -> str:
    from bot.supabase_client import get_sb
    from bot.memory import get_exam_date, _days_until
    from bot.llm import create_completion
    from bot.whatsapp import send_message

    sb = get_sb()

    res = sb.table("user_progress").select("topic,correct,total") \
        .eq("chat_id", chat_id).execute()
    rows = res.data or []

    # Filter for strong topics: >= 80% accuracy with minimum 3 attempts
    strong_topics = [
        r["topic"] for r in rows
        if r["total"] >= 3 and (r["correct"] / r["total"]) >= 0.8
    ]

    exam_date = get_exam_date(chat_id)
    days_left = _days_until(exam_date) if exam_date else None
    countdown = f"{days_left} days left" if days_left is not None else "your exam day"

    strong_topics_str = ", ".join(strong_topics) if strong_topics else "multiple topics"

    prompt = (
        f"You are Yudhister, a warm and supportive HCS exam mentor. "
        f"Write a genuine, encouraging message (5-7 lines of WhatsApp text, NOT bullet points) "
        f"to a student who:\n"
        f"• Is strong in: {strong_topics_str}\n"
        f"• Has {countdown} to exam\n\n"
        f"Tone: mentor-like, genuinely warm, acknowledging their progress, motivating without being preachy. "
        f"End with a single, powerful motivational line. No emojis, no bullets."
    )

    message = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.7,
    )

    header = "💪 *You've Got This!*\n\n"
    await send_message(chat_id, header + message.strip())
    return "Confidence boost message delivered to user."


async def _start_answer_writing(chat_id: str, topic: str, answer_type: str = "medium") -> str:
    from bot.mains import start_answer_writing
    from bot.whatsapp import send_message
    msg = await start_answer_writing(chat_id, topic, answer_type)
    await send_message(chat_id, msg)
    return f"Answer writing session started on '{topic}'. Content delivered to user."


async def _start_case_study(chat_id: str) -> str:
    from bot.mains import start_case_study
    from bot.whatsapp import send_message
    msg = await start_case_study(chat_id)
    await send_message(chat_id, msg)
    return "Ethics case study started. Content delivered to user."


async def _get_mains_pyq(chat_id: str, topic: str, paper: str = None) -> str:
    from bot.mains import get_mains_pyq
    from bot.whatsapp import send_message
    msg = await get_mains_pyq(chat_id, topic, paper)
    await send_message(chat_id, msg)
    return f"Mains PYQ on '{topic}' delivered to user."


async def _get_answer_template(chat_id: str, topic: str, answer_type: str = "medium") -> str:
    from bot.mains import get_answer_template
    from bot.whatsapp import send_message
    msg = await get_answer_template(chat_id, topic, answer_type)
    await send_message(chat_id, msg)
    return f"Answer template for '{topic}' delivered to user."


async def _switch_exam_mode(chat_id: str, mode: str) -> str:
    from bot.mains import switch_exam_mode
    from bot.whatsapp import send_message
    msg = await switch_exam_mode(chat_id, mode)
    await send_message(chat_id, msg)
    return f"Exam mode switched to {mode}."


async def execute_tool(name: str, inputs: dict, chat_id: str) -> str:
    fns = {
        "start_quiz": _start_quiz,
        "start_mock_test": _start_mock_test,
        "start_study_session": _start_study_session,
        "start_passage_quiz": _start_passage_quiz,
        "get_current_affairs": _get_current_affairs,
        "get_syllabus_or_paper": _get_syllabus_or_paper,
        "get_user_progress": _get_user_progress,
        "schedule_updates": _schedule_updates,
        "cancel_scheduled_updates": _cancel_scheduled_updates,
        "get_wrong_answers": _get_wrong_answers,
        "set_exam_date": _set_exam_date,
        "start_hpsc_mock": _start_hpsc_mock,
        "start_haryana_special": _start_haryana_special,
        "search_and_summarise": _search_and_summarise,
        "explain_topic": _explain_topic,
        "get_crash_course": _get_crash_course,
        "get_cheat_sheet": _get_cheat_sheet,
        "get_confidence_boost": _get_confidence_boost,
        "start_answer_writing": _start_answer_writing,
        "start_case_study": _start_case_study,
        "get_mains_pyq": _get_mains_pyq,
        "get_answer_template": _get_answer_template,
        "switch_exam_mode": _switch_exam_mode,
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
    from bot.whatsapp import send_message
    text, q_data = start_batch_quiz(chat_id, 5)
    if q_data:
        topic = q_data.get("topic", "")
        topic_line = f"_Topic: {topic}_\n\n" if topic else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        q_text = f"{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
        full = text + "\n\n" + q_text
    else:
        full = text
    await send_message(chat_id, full)
    return "Quiz started. Content delivered to user."


async def _start_mock_test(chat_id: str, question_count: int = 10, topic: str = None) -> str:
    from bot.quiz import start_mock_test
    from bot.whatsapp import send_message
    text, q_data = start_mock_test(chat_id, question_count, topic=topic)
    if q_data:
        topic_name = q_data.get("topic", "")
        topic_line = f"_Topic: {topic_name}_\n\n" if topic_name else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        full = text + "\n\n" + f"{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
    else:
        full = text
    await send_message(chat_id, full)
    return "Mock test started. Content delivered to user."


async def _start_study_session(chat_id: str, topic: str) -> str:
    from bot.quiz import start_study_session
    from bot.whatsapp import send_message
    text, q_data = start_study_session(chat_id, topic)
    if q_data:
        topic_name = q_data.get("topic", "")
        topic_line = f"_Topic: {topic_name}_\n\n" if topic_name else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        full = f"{text}\n\n{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
    else:
        full = text
    await send_message(chat_id, full)
    return f"Study session on '{topic}' started. Content delivered to user."


async def _start_passage_quiz(chat_id: str, topic: str) -> str:
    from bot.quiz import start_passage_quiz
    from bot.whatsapp import send_message
    text, q_data = start_passage_quiz(chat_id, topic)
    if q_data:
        topic_name = q_data.get("topic", "")
        topic_line = f"_Topic: {topic_name}_\n\n" if topic_name else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        full = f"{text}\n\n{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
    else:
        full = text
    await send_message(chat_id, full)
    return f"Passage quiz on '{topic}' started. Content delivered to user."


async def _get_current_affairs(chat_id: str) -> str:
    from bot.news import get_current_affairs
    summary, _, _ = get_current_affairs("HCS")
    if not summary:
        return "Couldn't fetch news right now. Try again in a bit!"
    return summary


async def _get_syllabus_or_paper(chat_id: str, content_type: str, subject: str = "", year: str = None) -> str:
    from bot.fetcher import search_and_fetch
    from bot.rag import retrieve
    year_int = int(year) if year and str(year).isdigit() else None
    search_and_fetch("HCS", content_type, subject, year_int)
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
    return (
        f"CONTENT FOR YOUR REPLY — paste the following {content_type} content directly into your reply "
        f"to the user. Do NOT say 'you have already seen this' or 'as shown above' — "
        f"the user has not received this yet. Include it in your response now:\n\n{context}"
    )


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


async def _get_wrong_answers(chat_id: str, topic: str = None) -> str:
    from bot.supabase_client import get_sb
    _sb = get_sb()
    try:
        query = _sb.table("user_answer_history")\
            .select("topic,question_text,options,correct_answer,user_answer,explanation")\
            .eq("chat_id", chat_id)\
            .eq("is_correct", False)\
            .order("attempted_at", desc=True)\
            .limit(10)
        if topic:
            query = query.eq("topic", topic)
        res = query.execute()
        rows = res.data or []

        if not rows:
            msg = "No wrong answers recorded"
            msg += f" for *{topic}*" if topic else ""
            msg += " yet. Keep practising! 🎉"
            return msg

        header = "*Your Recent Wrong Answers"
        header += f" — {topic}*\n\n" if topic else "*\n\n"
        lines = []
        for i, r in enumerate(rows, 1):
            opts = r.get("options", {})
            correct_text = opts.get(r["correct_answer"], r["correct_answer"])
            user_text = opts.get(r["user_answer"], r["user_answer"])
            lines.append(
                f"*{i}. [{r['topic']}]* {r['question_text']}\n"
                f"   You answered: *{r['user_answer']}* — {user_text}\n"
                f"   Correct: *{r['correct_answer']}* — {correct_text}\n"
                f"   _{r.get('explanation', '')}_"
            )
        return header + "\n\n".join(lines)
    except Exception as e:
        return "Couldn't load wrong answers right now. Try again in a moment."


async def _set_exam_date(chat_id: str, exam_date: str) -> str:
    from bot.memory import set_exam_date, _days_until
    set_exam_date(chat_id, exam_date)
    days = _days_until(exam_date)
    if days is None:
        return f"Exam date set to {exam_date}. (That date appears to be in the past — double-check?)"
    if days == 0:
        return "Exam date set — that's TODAY! All the best! 🎯"
    return f"Exam date set to {exam_date}. *{days} days to go!* Let's make them count. 💪"


async def _start_hpsc_mock(chat_id: str, question_count: int = 25) -> str:
    from bot.quiz import start_hpsc_mock
    from bot.whatsapp import send_message
    n = min(max(question_count, 5), 50)
    text, q_data = start_hpsc_mock(chat_id, n=n)
    if q_data:
        topic_name = q_data.get("topic", "")
        topic_line = f"_Topic: {topic_name}_\n\n" if topic_name else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        full = text + "\n\n" + f"{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
    else:
        full = text
    await send_message(chat_id, full)
    return "HPSC blueprint mock started. Content delivered to user."


async def _start_haryana_special(chat_id: str, question_count: int = 10) -> str:
    from bot.quiz import start_haryana_special
    from bot.whatsapp import send_message
    n = min(max(question_count, 5), 20)
    text, q_data = start_haryana_special(chat_id, n=n)
    if q_data:
        topic_name = q_data.get("topic", "")
        topic_line = f"_Topic: {topic_name}_\n\n" if topic_name else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        full = text + "\n\n" + f"{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
    else:
        full = text
    await send_message(chat_id, full)
    return "Haryana special drill started. Content delivered to user."


async def _search_and_summarise(chat_id: str, query: str) -> str:
    from bot.web_search import search_web
    from bot.llm import create_completion

    lower = query.lower()
    # Always include HCS context in the search query so results stay exam-relevant
    if "hcs" not in lower and "haryana" not in lower:
        search_query = f"{query} Haryana civil services HCS exam"
    else:
        search_query = query

    results = search_web(search_query, max_results=4)
    if not results:
        return "Could not find results for that right now. Try again in a moment!"

    snippets = "\n\n".join(
        f"Source: {r.get('title', 'Untitled')}\n{r.get('body', '')[:300]}"
        for r in results if r.get("title") or r.get("body")
    )
    if not snippets.strip():
        return "Found results but couldn't extract content. Try rephrasing your query."

    summary = create_completion(
        messages=[{"role": "user", "content":
            f"You are Yudhister, HCS exam coach. A student asked: \"{query}\"\n\n"
            f"Using ONLY the information in these search results, give a clear HCS-focused answer in 3-5 bullet points. "
            f"Every point must connect back to the HCS exam — if a fact has exam relevance, add '(HCS: ...)'. "
            f"Omit anything not relevant to HCS preparation. Do NOT add facts not in the sources.\n\nSearch results:\n{snippets}"
        }],
        max_tokens=350,
        temperature=0.6,
    )
    return f"*Search: {query}*\n\n{summary.strip()}"


async def _explain_topic(chat_id: str, topic: str) -> str:
    from bot.llm import create_completion
    from bot.whatsapp import send_message

    explanation = create_completion(
        messages=[{"role": "user", "content":
            f"You are Yudhister, HCS exam coach. Explain '{topic}' for an HCS aspirant.\n\n"
            f"Cover: what it is, key facts/dates/numbers, why it matters for HCS Prelims.\n"
            f"Keep it under 180 words. Friendly, clear, no quiz questions. "
            f"End with one *HCS exam tip* in bold."
        }],
        max_tokens=350,
        temperature=0.7,
    )
    await send_message(chat_id, explanation.strip())
    return "Explanation delivered to user."
