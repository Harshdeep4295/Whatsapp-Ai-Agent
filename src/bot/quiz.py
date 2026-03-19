import json
import random
from datetime import datetime, timezone
from bot.supabase_client import get_sb
from bot.llm import get_client

sb = get_sb()

# HCS Prelims syllabus topics — questions will be drawn from these
HCS_GS_TOPICS = [
    "Indian History and Culture",
    "Haryana History and Culture",
    "Indian Geography",
    "Haryana Geography",
    "Indian Polity and Constitution",
    "Panchayati Raj and Local Governance",
    "Indian Economy and Development",
    "Haryana Economy and Agriculture",
    "Science and Technology",
    "Environment and Ecology",
    "Current Affairs — National",
    "Current Affairs — Haryana",
    "General Science",
    "Important Government Schemes",
]

HCS_CSAT_TOPICS = [
    "Reading Comprehension",
    "Logical Reasoning",
    "Analytical Ability",
    "Data Interpretation",
    "Basic Numeracy",
    "Decision Making",
    "Problem Solving",
    "English Language Comprehension",
]

MCQ_PROMPT = """Generate ONE HCS (Haryana Civil Services) Prelims exam style MCQ strictly on this topic: {subject}

The question must:
- Be relevant to the HCS Prelims syllabus
- Match actual HPSC exam style and difficulty
- Test conceptual understanding, not just trivia
- For CSAT topics: test reasoning/aptitude skills
- For GS topics: test factual + analytical knowledge about India/Haryana

Return ONLY valid JSON, nothing else:
{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"one clear sentence explaining why"}}"""

MOCK_TEST_PROMPT = """Generate exactly {n} HCS (Haryana Civil Services) Prelims style MCQs across different topics from this list: {topics}

Each question must match actual HPSC exam style and test conceptual understanding.

Return ONLY a valid JSON array, nothing else:
[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"one clear sentence","topic":"topic name"}}]"""

STUDY_OVERVIEW_PROMPT = """You are Yudhister, a professor with 20+ years of experience teaching HCS (Haryana Civil Services) exam aspirants.

A student wants to study: "{topic}"

Write a study session intro that covers:
1. What this topic is and its 2-3 key sub-areas (be specific — name them)
2. Why it matters for HCS Prelims (typical question count or exam importance)
3. 2-3 actual important facts or concepts a student must remember
4. End with: "Let's test your knowledge with 3 warm-up questions!"

Keep it under 150 words. Friendly and specific."""


def _get_adaptive_topic(chat_id: str, subject: str) -> str:
    """Pick topic adaptively based on user_progress. Weak topics get 3x weight, untried 2x, strong 1x."""
    if subject and subject.lower() not in ["general", "general studies", "", "hcs"]:
        return subject

    all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS

    try:
        res = sb.table("user_progress").select("topic,correct,total")\
            .eq("chat_id", chat_id).execute()
        progress = {row["topic"]: row for row in (res.data or [])}
    except Exception:
        progress = {}

    weighted = []
    for topic in all_topics:
        p = progress.get(topic)
        if p is None or p["total"] == 0:
            weight = 2  # untried — ensure coverage
        else:
            pct = p["correct"] / p["total"]
            if pct < 0.6:
                weight = 3  # weak topic — prioritize
            elif pct > 0.8:
                weight = 1  # strong topic — deprioritize
            else:
                weight = 2
        weighted.extend([topic] * weight)

    return random.choice(weighted)


def _update_progress(chat_id: str, topic: str, is_correct: bool):
    """Upsert user_progress for this topic."""
    try:
        res = sb.table("user_progress").select("correct,total")\
            .eq("chat_id", chat_id).eq("topic", topic).execute()
        if res.data:
            row = res.data[0]
            sb.table("user_progress").update({
                "correct": row["correct"] + (1 if is_correct else 0),
                "total": row["total"] + 1,
                "last_attempted": datetime.now(timezone.utc).isoformat(),
            }).eq("chat_id", chat_id).eq("topic", topic).execute()
        else:
            sb.table("user_progress").insert({
                "chat_id": chat_id, "topic": topic,
                "correct": 1 if is_correct else 0,
                "total": 1,
            }).execute()
    except Exception as e:
        print(f"[quiz] progress update failed: {e}")


def _generate(subject: str) -> dict:
    topic = subject
    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": MCQ_PROMPT.format(subject=topic)}],
        max_tokens=400,
        temperature=0.85,
    )
    raw = r.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())
    result["_topic"] = topic
    return result


def _fmt(q: dict) -> str:
    topic = q.get("_topic", q.get("topic", ""))
    topic_line = f"_Topic: {topic}_\n\n" if topic else ""
    opts = "\n".join(f"*{k}.* {v}" for k, v in q["options"].items())
    return f"{topic_line}{q['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"


def _mock_report(questions: list, answers: list, n: int) -> str:
    correct_count = sum(1 for a in answers if a["correct"])
    pct = int(correct_count / n * 100)

    topic_stats: dict = {}
    for a in answers:
        t = a.get("topic", "General")
        if t not in topic_stats:
            topic_stats[t] = {"correct": 0, "total": 0}
        topic_stats[t]["total"] += 1
        if a["correct"]:
            topic_stats[t]["correct"] += 1

    report = f"*Mock Test Complete!* 🏁\n\nScore: *{correct_count}/{n}* ({pct}%)\n\n"

    weak = [t for t, s in topic_stats.items() if s["total"] > 0 and s["correct"] / s["total"] < 0.6]
    if weak:
        report += f"*Revise these topics:* {', '.join(weak)}\n\n"

    if pct >= 80:
        report += "Excellent work! 🔥 Keep it up!"
    elif pct >= 50:
        report += "Good attempt! 💪 Focus on your weak topics."
    else:
        report += "Keep practicing! 📚 Review the topics above and try again."
    return report


# ── Regular Quiz ────────────────────────────────────────────────────────────

def start_quiz(chat_id: str, exam: str, subject: str) -> tuple[str, dict]:
    topic = _get_adaptive_topic(chat_id, subject)
    q = _generate(topic)
    sb.table("quiz_sessions").upsert({
        "chat_id": chat_id, "exam": "HCS", "subject": q.get("_topic", topic),
        "question": q["question"], "options": q["options"],
        "correct_answer": q["correct"], "explanation": q["explanation"],
        "active": True, "score": 0, "total": 0,
    }, on_conflict="chat_id").execute()
    return (
        "Alright, HCS quiz time! 🎯",
        {"question": q["question"], "options": q["options"], "topic": q.get("_topic", topic)},
    )


def check_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    res = sb.table("quiz_sessions").select("*")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    if not res.data:
        return "No active quiz. Send *quiz me* to start one!", None

    s = res.data[0]
    letter = user_answer.strip().upper()[0]
    correct = s["correct_answer"]
    is_right = letter == correct
    new_score = s["score"] + (1 if is_right else 0)
    new_total = s["total"] + 1

    _update_progress(chat_id, s["subject"], is_right)

    if is_right:
        result = f"*Correct!* 🎉\n\n{s['explanation']}"
    else:
        result = f"*Not quite.* The answer is *{correct}*: {s['options'][correct]}\n\n{s['explanation']}"

    result += f"\n\nScore: *{new_score}/{new_total}*\n\nNext one 👇"

    next_topic = _get_adaptive_topic(chat_id, "")
    next_q = _generate(next_topic)
    sb.table("quiz_sessions").update({
        "question": next_q["question"], "options": next_q["options"],
        "correct_answer": next_q["correct"], "explanation": next_q["explanation"],
        "subject": next_q.get("_topic", next_topic),
        "score": new_score, "total": new_total,
    }).eq("chat_id", chat_id).execute()

    return (
        result,
        {"question": next_q["question"], "options": next_q["options"], "topic": next_q.get("_topic", next_topic)},
    )


def stop_quiz(chat_id: str) -> tuple[str, None]:
    res = sb.table("quiz_sessions").select("score,total")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    sb.table("quiz_sessions").update({"active": False}).eq("chat_id", chat_id).execute()
    if res.data:
        d = res.data[0]
        pct = int(d["score"] / d["total"] * 100) if d["total"] else 0
        msg = "Amazing! 🔥" if pct >= 80 else "Good effort! Keep going 💪" if pct >= 50 else "Keep practicing, you'll get there! 📚"
        return f"Quiz done!\n\nFinal score: *{d['score']}/{d['total']}* ({pct}%)\n\n{msg}", None
    return "Quiz ended.", None


def has_active_quiz(chat_id: str) -> bool:
    res = sb.table("quiz_sessions").select("id")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    return bool(res.data)


def start_batch_quiz(chat_id: str, n: int = 5) -> tuple[str, None]:
    """Generate n questions, send them all as a numbered list in one message.
    Answers are processed one by one via check_mock_answer (reuses mock_tests table)."""
    all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS
    topics_str = ", ".join(all_topics)
    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": MOCK_TEST_PROMPT.format(n=n, topics=topics_str)}],
        max_tokens=n * 220,
        temperature=0.85,
    )
    raw = r.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    questions = json.loads(raw.strip())

    # Deactivate any existing mock test
    sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
    sb.table("mock_tests").insert({
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "current_idx": 0,
        "active": True,
    }).execute()

    # Format all questions in one message
    lines = [f"*Quiz Round — {n} Questions* 📋\n"]
    for i, q in enumerate(questions, 1):
        topic = q.get("topic", "")
        topic_line = f"_{topic}_\n" if topic else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q["options"].items())
        lines.append(f"*Q{i}.* {topic_line}{q['question']}\n{opts}")
    lines.append("\n_Answer Q1 first — reply A, B, C, or D_")

    return "\n\n".join(lines), None


# ── Mock Test ────────────────────────────────────────────────────────────────

def start_mock_test(chat_id: str, n: int = 10) -> str:
    all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS
    topics_str = ", ".join(all_topics)
    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": MOCK_TEST_PROMPT.format(n=n, topics=topics_str)}],
        max_tokens=n * 220,
        temperature=0.85,
    )
    raw = r.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    questions = json.loads(raw.strip())

    # Deactivate any existing mock test
    sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
    sb.table("mock_tests").insert({
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "current_idx": 0,
        "active": True,
    }).execute()

    q = questions[0]
    return (
        f"*Mock Test — {n} Questions* 📝\n\nQuestion 1/{n}:",
        {"question": q["question"], "options": q["options"], "topic": q.get("topic", "")},
    )


def check_mock_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    res = sb.table("mock_tests").select("*")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    if not res.data:
        return "No active mock test. Send *mock test* to start one!", None

    test = res.data[0]
    questions = test["questions"]
    answers = list(test["answers"])
    idx = test["current_idx"]
    n = len(questions)

    q = questions[idx]
    letter = user_answer.strip().upper()[0]
    correct = q["correct"]
    is_right = letter == correct

    topic = q.get("topic", "General")
    answers.append({"q": idx, "answer": letter, "correct": is_right, "topic": topic})
    _update_progress(chat_id, topic, is_right)

    if is_right:
        feedback = f"*Correct!* ✅\n{q['explanation']}"
    else:
        feedback = f"*Wrong.* Answer: *{correct}*: {q['options'][correct]}\n{q['explanation']}"

    next_idx = idx + 1

    if next_idx >= n:
        sb.table("mock_tests").update({
            "answers": answers, "active": False, "current_idx": next_idx
        }).eq("id", test["id"]).execute()
        return feedback + "\n\n" + _mock_report(questions, answers, n), None
    else:
        sb.table("mock_tests").update({
            "answers": answers, "current_idx": next_idx
        }).eq("id", test["id"]).execute()
        next_q = questions[next_idx]
        return (
            feedback + f"\n\nQuestion {next_idx + 1}/{n}:",
            {"question": next_q["question"], "options": next_q["options"], "topic": next_q.get("topic", "")},
        )


def has_active_mock_test(chat_id: str) -> bool:
    res = sb.table("mock_tests").select("id")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    return bool(res.data)


# ── Study Session ────────────────────────────────────────────────────────────

def start_study_session(chat_id: str, topic: str) -> str:
    from bot.memory import set_study_session, set_current_topic
    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": STUDY_OVERVIEW_PROMPT.format(topic=topic)}],
        max_tokens=300,
        temperature=0.7,
    )
    overview = r.choices[0].message.content.strip()

    set_current_topic(chat_id, topic)
    set_study_session(chat_id, {"topic": topic, "q_count": 0, "correct": 0, "max_q": 3})

    first_q = _generate(topic)
    session_q = {"question": first_q["question"], "options": first_q["options"],
                 "correct": first_q["correct"], "explanation": first_q["explanation"],
                 "topic": topic}
    # Store pending question in study_session
    from bot.memory import get_study_session
    sess = get_study_session(chat_id)
    sess["pending_q"] = session_q
    set_study_session(chat_id, sess)

    return (
        f"{overview}\n\n*Question 1/3:*",
        {"question": first_q["question"], "options": first_q["options"], "topic": topic},
    )


def check_study_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    from bot.memory import get_study_session, set_study_session, set_current_topic
    sess = get_study_session(chat_id)
    if not sess or "pending_q" not in sess:
        return "No active study session. Say *let's study [topic]* to start one!", None

    q = sess["pending_q"]
    letter = user_answer.strip().upper()[0]
    correct = q["correct"]
    is_right = letter == correct

    _update_progress(chat_id, q["topic"], is_right)

    if is_right:
        feedback = f"*Correct!* 🎉\n{q['explanation']}"
    else:
        feedback = f"*Not quite.* Answer: *{correct}*: {q['options'][correct]}\n{q['explanation']}"

    sess["q_count"] += 1
    if is_right:
        sess["correct"] += 1
    q_count = sess["q_count"]
    max_q = sess["max_q"]
    topic = sess["topic"]

    if q_count >= max_q:
        correct_count = sess["correct"]
        pct = int(correct_count / max_q * 100)
        set_study_session(chat_id, None)
        set_current_topic(chat_id, None)
        msg = "Great job! 🔥" if pct >= 80 else "Good effort! 💪" if pct >= 50 else "More practice needed! 📚"
        summary = f"\n\n*Session Summary — {topic}*\nScore: *{correct_count}/{max_q}* ({pct}%) {msg}"
        return feedback + summary, None
    else:
        next_q_data = _generate(topic)
        sess["pending_q"] = {
            "question": next_q_data["question"], "options": next_q_data["options"],
            "correct": next_q_data["correct"], "explanation": next_q_data["explanation"],
            "topic": topic,
        }
        set_study_session(chat_id, sess)
        return (
            feedback + f"\n\n*Question {q_count + 1}/{max_q}:*",
            {"question": next_q_data["question"], "options": next_q_data["options"], "topic": topic},
        )


def has_active_study_session(chat_id: str) -> bool:
    from bot.memory import get_study_session
    sess = get_study_session(chat_id)
    return bool(sess and "pending_q" in sess)
