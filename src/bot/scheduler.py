import hashlib
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import create_client
from bot.news import get_current_affairs
from bot.whatsapp import send_message
from config import SUPABASE_URL, SUPABASE_KEY

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
_scheduler = None

JOB_TYPES = {
    "news": "current_affairs",
    "current_affairs": "current_affairs",
    "updates": "current_affairs",
    "quiz": "quiz",
    "mcq": "quiz",
    "practice": "quiz",
    "syllabus": "syllabus",
    "study": "study_material",
    "material": "study_material",
    "explain": "explain",
}

INTERVAL_ALIASES = {
    "hourly": 60,
    "every hour": 60,
    "daily": 1440,
    "every day": 1440,
    "every morning": 1440,
    "twice a day": 720,
    "every 30 minutes": 30,
    "every 6 hours": 360,
    "every 12 hours": 720,
}

def parse_interval(text: str) -> int:
    """Return interval in minutes from natural language, default 60."""
    t = text.lower()
    for alias, mins in INTERVAL_ALIASES.items():
        if alias in t:
            return mins
    import re
    m = re.search(r'every\s+(\d+)\s*(hour|hr|minute|min)', t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return n * 60 if 'hour' in unit or 'hr' in unit else n
    return 60

def schedule_job(chat_id: str, job_type: str, interval_minutes: int, exam: str = "HCS", subject: str = "") -> str:
    # Deactivate any existing same-type job for this user
    sb.table("scheduled_jobs")\
        .update({"active": False})\
        .eq("chat_id", chat_id).eq("job_type", job_type)\
        .execute()

    now = datetime.now(timezone.utc)
    sb.table("scheduled_jobs").insert({
        "chat_id": chat_id,
        "job_type": job_type,
        "interval_minutes": interval_minutes,
        "exam": exam,
        "subject": subject,
        "next_run_at": now.isoformat(),
        "active": True,
    }).execute()

    hrs = interval_minutes // 60
    mins = interval_minutes % 60
    if hrs and mins:
        freq = f"every {hrs}h {mins}m"
    elif hrs:
        freq = f"every {hrs} hour{'s' if hrs > 1 else ''}"
    else:
        freq = f"every {mins} minutes"
    return f"Done! I'll send you {job_type.replace('_', ' ')} {freq}. Say *stop updates* to cancel anytime."

def cancel_jobs(chat_id: str) -> str:
    res = sb.table("scheduled_jobs")\
        .update({"active": False})\
        .eq("chat_id", chat_id).eq("active", True)\
        .execute()
    if res.data:
        return "All your scheduled updates have been cancelled."
    return "You don't have any active scheduled updates."

async def _run_due_jobs():
    now = datetime.now(timezone.utc)
    res = sb.table("scheduled_jobs")\
        .select("*")\
        .eq("active", True)\
        .lte("next_run_at", now.isoformat())\
        .execute()

    for job in (res.data or []):
        try:
            content, content_hash = _generate_content(job)
            next_run = now + timedelta(minutes=job["interval_minutes"])
            update = {"next_run_at": next_run.isoformat()}

            if content:
                await send_message(job["chat_id"], content)
                update["last_content_hash"] = content_hash
            else:
                print(f"[scheduler] job {job['id']} — no new content found after search")

            sb.table("scheduled_jobs").update(update).eq("id", job["id"]).execute()
        except Exception as e:
            print(f"[scheduler] job {job['id']} failed: {e}")

def _generate_content(job: dict) -> tuple[str, str]:
    """Returns (content, hash). content is None if nothing new found."""
    jtype = job.get("job_type", "")
    exam = job.get("exam", "General")
    subject = job.get("subject") or "General Studies"
    last_hash = job.get("last_content_hash")

    if jtype == "current_affairs":
        return get_current_affairs(exam, last_hash=last_hash)

    if jtype == "quiz":
        # Quiz questions are LLM-generated with high temperature — always unique
        from bot.quiz import _generate, _fmt
        try:
            q = _generate(exam, subject)
            content = f"*Scheduled Quiz — {exam}*\n\n" + _fmt(q)
            content_hash = hashlib.md5(q["question"].encode()).hexdigest()
            if content_hash == last_hash:
                # Regenerate once more to get a different question
                q = _generate(exam, subject)
                content = f"*Scheduled Quiz — {exam}*\n\n" + _fmt(q)
                content_hash = hashlib.md5(q["question"].encode()).hexdigest()
            return content, content_hash
        except Exception as e:
            print(f"[scheduler] quiz generation failed: {e}")
            return None, ""

    if jtype in ("syllabus", "explain", "study_material"):
        # Fetch fresh web content on the topic
        try:
            from ddgs import DDGS
            query = f"{exam} {subject} latest updates {jtype}"
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return None, last_hash or ""
            snippets = "\n".join(f"- {r.get('title','')}: {r.get('body','')[:100]}" for r in results)
            content_hash = hashlib.md5(snippets.encode()).hexdigest()
            if content_hash == last_hash:
                return None, last_hash
            from bot.llm import get_client
            client = get_client()
            r = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content":
                    f"Summarize this for a {exam} student studying {subject}. "
                    f"3-4 key points only:\n{snippets}"
                }],
                max_tokens=250,
            )
            content = f"*{exam} — {subject} Update*\n\n" + r.choices[0].message.content
            return content, content_hash
        except Exception as e:
            print(f"[scheduler] study material fetch failed: {e}")
            return None, ""

    return None, ""

def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(_run_due_jobs, "interval", minutes=1, id="job_runner")
    _scheduler.start()
    print("[scheduler] started")

def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown()
