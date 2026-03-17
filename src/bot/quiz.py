import json
from supabase import create_client
from bot.llm import get_client
from config import SUPABASE_URL, SUPABASE_KEY

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

MCQ_PROMPT = """Generate ONE {exam} exam style MCQ on: {subject}
Difficulty: {difficulty}

Return ONLY valid JSON:
{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"..."}}"""

def _generate(exam: str, subject: str, difficulty: str = "medium") -> dict:
    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": MCQ_PROMPT.format(
            exam=exam, subject=subject, difficulty=difficulty
        )}],
        max_tokens=400, temperature=0.8,
    )
    return json.loads(r.choices[0].message.content)

def _fmt(q: dict) -> str:
    opts = "\n".join(f"*{k}.* {v}" for k, v in q["options"].items())
    return f"{q['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"

def start_quiz(chat_id: str, exam: str, subject: str) -> str:
    q = _generate(exam, subject)
    sb.table("quiz_sessions").upsert({
        "chat_id": chat_id, "exam": exam, "subject": subject,
        "question": q["question"], "options": q["options"],
        "correct_answer": q["correct"], "explanation": q["explanation"],
        "active": True,
    }, on_conflict="chat_id").execute()
    return f"Starting quiz: *{exam} — {subject}*\n\n" + _fmt(q)

def check_answer(chat_id: str, user_answer: str) -> str:
    res = sb.table("quiz_sessions").select("*")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    if not res.data:
        return "No active quiz. Send *quiz me* to start!"

    s = res.data[0]
    letter = user_answer.strip().upper()[0]
    correct = s["correct_answer"]
    is_right = letter == correct
    new_score = s["score"] + (1 if is_right else 0)
    new_total = s["total"] + 1

    if is_right:
        result = f"*Correct!*\n\n{s['explanation']}"
    else:
        result = f"*Wrong.* Answer is *{correct}*: {s['options'][correct]}\n\n{s['explanation']}"

    result += f"\n\nScore: *{new_score}/{new_total}*\n\n"

    next_q = _generate(s["exam"], s["subject"])
    sb.table("quiz_sessions").update({
        "question": next_q["question"], "options": next_q["options"],
        "correct_answer": next_q["correct"], "explanation": next_q["explanation"],
        "score": new_score, "total": new_total,
    }).eq("chat_id", chat_id).execute()

    return result + _fmt(next_q)

def stop_quiz(chat_id: str) -> str:
    res = sb.table("quiz_sessions").select("score,total")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    sb.table("quiz_sessions").update({"active": False}).eq("chat_id", chat_id).execute()
    if res.data:
        d = res.data[0]
        pct = int(d["score"] / d["total"] * 100) if d["total"] else 0
        return f"Quiz ended!\n\nFinal score: *{d['score']}/{d['total']}* ({pct}%)"
    return "Quiz ended."

def has_active_quiz(chat_id: str) -> bool:
    res = sb.table("quiz_sessions").select("id")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    return bool(res.data)
