import hashlib
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.supabase_client import get_sb
from bot.news import get_current_affairs
from bot.web_search import search_web
from bot.whatsapp import send_message

sb = get_sb()
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
    "weekly_report": "weekly_report",
    "report": "weekly_report",
    "performance": "weekly_report",
    "nightly_revision": "nightly_revision",
    "night": "nightly_revision",
    "revision": "nightly_revision",
    "daily revision": "nightly_revision",
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
        seen_keys = job.get("seen_keys") or []
        content, content_hash, new_seen_keys = get_current_affairs(exam, last_hash=last_hash, seen_keys=seen_keys)
        if new_seen_keys:
            try:
                sb.table("scheduled_jobs").update({"seen_keys": new_seen_keys}).eq("id", job["id"]).execute()
            except Exception as e:
                print(f"[scheduler] seen_keys update failed: {e}")
        return content, content_hash

    if jtype == "quiz":
        # Quiz questions are LLM-generated with high temperature — always unique
        from bot.quiz import _generate, _fmt, _get_adaptive_topic
        try:
            topic = _get_adaptive_topic(job["chat_id"], subject)
            q = _generate(topic)
            content = f"*Scheduled Quiz — {exam}*\n\n" + _fmt(q)
            content_hash = hashlib.md5(q["question"].encode()).hexdigest()
            if content_hash == last_hash:
                # Regenerate once more to get a different question
                q = _generate(topic)
                content = f"*Scheduled Quiz — {exam}*\n\n" + _fmt(q)
                content_hash = hashlib.md5(q["question"].encode()).hexdigest()
            return content, content_hash
        except Exception as e:
            print(f"[scheduler] quiz generation failed: {e}")
            return None, ""

    if jtype in ("syllabus", "explain", "study_material"):
        # Fetch fresh web content on the topic
        try:
            query = f"{exam} {subject} latest updates {jtype}"
            results = search_web(query, max_results=5)
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

    if jtype == "weekly_report":
        try:
            chat_id = job["chat_id"]
            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            res = sb.table("user_progress").select("topic,correct,total,last_attempted")\
                .eq("chat_id", chat_id)\
                .gte("last_attempted", week_ago)\
                .execute()
            rows = res.data or []
            if not rows:
                return "*Weekly Report*\n\nNo quiz activity this week. Try *quiz me* to start practicing!", ""

            total_q = sum(r["total"] for r in rows)
            total_c = sum(r["correct"] for r in rows)
            pct = int(total_c / total_q * 100) if total_q else 0

            sorted_rows = sorted(rows, key=lambda r: (r["correct"] / r["total"]) if r["total"] else 0)
            worst = sorted_rows[0]["topic"] if sorted_rows else "N/A"
            best = sorted_rows[-1]["topic"] if sorted_rows else "N/A"
            weak = [r["topic"] for r in sorted_rows if r["total"] > 0 and r["correct"] / r["total"] < 0.6]

            report = (
                f"*Weekly Performance Report* 📊\n\n"
                f"Questions attempted: *{total_q}*\n"
                f"Accuracy: *{total_c}/{total_q}* ({pct}%)\n\n"
                f"*Best topic:* {best}\n"
                f"*Needs work:* {worst}\n"
            )
            if weak:
                report += f"\n*Focus next week:* {', '.join(weak[:3])}"
            content_hash = hashlib.md5(report.encode()).hexdigest()
            return report, content_hash
        except Exception as e:
            print(f"[scheduler] weekly_report failed: {e}")
            return None, ""

    if jtype == "nightly_revision":
        return _generate_nightly_revision(job)

    return None, ""

def _generate_nightly_revision(job: dict) -> tuple[str, str]:
    import hashlib
    from datetime import datetime, timezone, timedelta
    from bot.llm import get_client

    chat_id = job["chat_id"]
    last_hash = job.get("last_content_hash")

    # 1. Pull today's conversation (last 24h)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        conv_res = sb.table("conversations").select("role,content")\
            .eq("chat_id", chat_id)\
            .gte("created_at", since)\
            .order("created_at").execute()
        messages = conv_res.data or []
    except Exception:
        messages = []

    # 2. Get weak topics from user_progress
    try:
        prog_res = sb.table("user_progress").select("topic,correct,total")\
            .eq("chat_id", chat_id).execute()
        rows = prog_res.data or []
        weak = sorted(
            [r for r in rows if r["total"] >= 2],
            key=lambda r: r["correct"] / r["total"]
        )[:3]
    except Exception:
        weak = []

    # 3. Get streak
    try:
        profile_res = sb.table("user_profiles").select("study_streak").eq("chat_id", chat_id).execute()
        streak = (profile_res.data[0].get("study_streak") or 0) if profile_res.data else 0
    except Exception:
        streak = 0

    # 4. LLM: extract today's topics + key facts from conversations
    today_summary = ""
    if messages:
        convo_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:200]}" for m in messages[-30:]
        )
        client = get_client()
        try:
            r = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content":
                    "From this HCS study chat, extract:\n"
                    "1. Topics the student studied today (list up to 4, short names)\n"
                    "2. Up to 3 key facts worth remembering\n\n"
                    "Format:\nTopics: [topic1, topic2]\nKey Facts:\n• fact1\n• fact2\n\n"
                    f"Chat:\n{convo_text}"
                }],
                max_tokens=200,
            )
            today_summary = r.choices[0].message.content.strip()
        except Exception:
            today_summary = ""

    # 5. Build the message
    from datetime import date
    date_str = date.today().strftime("%d %b %Y")
    streak_line = f"🔥 Day *{streak}* streak!\n\n" if streak >= 2 else ""

    parts = [f"*📚 Nightly Revision — {date_str}*\n\n{streak_line}"]

    if today_summary:
        parts.append(f"*What you covered today:*\n{today_summary}")
    else:
        parts.append("No activity recorded today — make sure to study something tomorrow! 💪")

    if weak:
        weak_lines = "\n".join(
            f"• {r['topic']}: {int(r['correct']/r['total']*100)}% ({r['total']} questions)"
            for r in weak
        )
        parts.append(f"*⚠️ Weak areas to revise:*\n{weak_lines}")

    parts.append("_Reply *quiz me* to drill your weak topics, or *my progress* for full stats._")

    content = "\n\n".join(parts)
    content_hash = hashlib.md5(content.encode()).hexdigest()

    if content_hash == last_hash:
        return None, last_hash

    return content, content_hash

def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(_run_due_jobs, "interval", minutes=1, id="job_runner")
    _scheduler.start()
    print("[scheduler] started")

def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown()
