import asyncio
from datetime import datetime, timezone
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
            content = _generate_content(job)
            if content:
                await send_message(job["chat_id"], content)
            # Update next_run_at
            from datetime import timedelta
            next_run = now + timedelta(minutes=job["interval_minutes"])
            sb.table("scheduled_jobs")\
                .update({"next_run_at": next_run.isoformat()})\
                .eq("id", job["id"])\
                .execute()
        except Exception as e:
            print(f"[scheduler] job {job['id']} failed: {e}")

def _generate_content(job: dict) -> str:
    jtype = job.get("job_type", "")
    exam = job.get("exam", "HCS")
    if jtype == "current_affairs":
        return get_current_affairs(exam)
    return ""

def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(_run_due_jobs, "interval", minutes=1, id="job_runner")
    _scheduler.start()
    print("[scheduler] started")

def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown()
