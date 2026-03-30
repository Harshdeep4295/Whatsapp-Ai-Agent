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

def _next_1630_utc() -> datetime:
    """Return the next occurrence of 16:30 UTC (10 PM IST) from now."""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=16, minute=30, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def schedule_job(chat_id: str, job_type: str, interval_minutes: int, exam: str = "HCS", subject: str = "", next_run_at: datetime | None = None) -> str:
    # Deactivate any existing same-type job for this user
    sb.table("scheduled_jobs")\
        .update({"active": False})\
        .eq("chat_id", chat_id).eq("job_type", job_type)\
        .execute()

    if next_run_at is None:
        next_run_at = datetime.now(timezone.utc)
    sb.table("scheduled_jobs").insert({
        "chat_id": chat_id,
        "job_type": job_type,
        "interval_minutes": interval_minutes,
        "exam": exam,
        "subject": subject,
        "next_run_at": next_run_at.isoformat(),
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

def _is_within_24h_window(last_active_date: str | None) -> bool:
    """Return True if last_active_date is within the last 3 days (UTC).
    Wider than the WhatsApp 24h window to avoid silently skipping users
    who studied 1-2 days ago and haven't opened WhatsApp yet today."""
    if not last_active_date:
        return False
    from datetime import date, timedelta
    today = date.today()  # UTC (scheduler runs in UTC)
    three_days_ago = today - timedelta(days=3)
    try:
        lad = date.fromisoformat(last_active_date)
        return lad >= three_days_ago
    except Exception:
        return False


async def _run_due_jobs():
    now = datetime.now(timezone.utc)
    res = sb.table("scheduled_jobs")\
        .select("*")\
        .eq("active", True)\
        .lte("next_run_at", now.isoformat())\
        .execute()

    jobs = res.data or []

    # Batch-fetch last_active_date for all unique chat_ids in one query
    chat_ids = list({job["chat_id"] for job in jobs})
    last_active_by_chat: dict[str, str | None] = {}
    if chat_ids:
        try:
            profiles_res = sb.table("user_profiles")\
                .select("chat_id,last_active_date")\
                .in_("chat_id", chat_ids)\
                .execute()
            for row in (profiles_res.data or []):
                last_active_by_chat[row["chat_id"]] = row.get("last_active_date")
        except Exception as e:
            print(f"[scheduler] failed to fetch user_profiles for 24h check: {e}")

    for job in jobs:
        try:
            next_run = now + timedelta(minutes=job["interval_minutes"])
            update = {"next_run_at": next_run.isoformat()}

            last_active = last_active_by_chat.get(job["chat_id"])
            if not _is_within_24h_window(last_active):
                print(f"[scheduler] job {job['id']} — skipped, user outside 24h window (last_active_date={last_active})")
                sb.table("scheduled_jobs").update(update).eq("id", job["id"]).execute()
                continue

            content, content_hash = _generate_content(job)

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
            from bot.llm import create_completion
            result = create_completion(
                messages=[{"role": "user", "content":
                    f"Summarize this for a {exam} student studying {subject}. "
                    f"3-4 key points only:\n{snippets}"
                }],
                max_tokens=250,
            )
            content = f"*{exam} — {subject} Update*\n\n" + result
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

    if jtype == "fact_drill":
        return _generate_fact_drill(job)

    return None, ""

def _generate_daily_facts(topics: list) -> str:
    """Returns a formatted 'Did You Know?' block or empty string on failure."""
    from bot.llm import create_completion
    import random
    from bot.quiz import HCS_GS_TOPICS
    if not topics:
        topics = random.sample(HCS_GS_TOPICS, k=2)
    try:
        facts = create_completion(
            messages=[{"role": "user", "content": DAILY_FACT_PROMPT.format(topics=", ".join(topics[:3]))}],
            max_tokens=180,
            temperature=0.9,
        )
        return f"*📌 Did You Know?*\n\n{facts.strip()}"
    except Exception as e:
        print(f"[scheduler] daily facts failed: {e}")
        return ""


def _generate_fact_with_question_context(question_text: str) -> str:
    """Generate 1 fact directly aligned to the question being asked."""
    from bot.llm import create_completion
    try:
        fact = create_completion(
            messages=[{"role": "user", "content": DAILY_FACT_PROMPT_WITH_CONTEXT.format(question=question_text)}],
            max_tokens=120,
            temperature=0.9,
        )
        return f"*📌 Did You Know?*\n\n{fact.strip()}"
    except Exception as e:
        print(f"[scheduler] context-aware fact failed: {e}")
        return ""


def _generate_fact_drill(job: dict) -> tuple[str, str]:
    """Every 2 hours: send one fact on an adaptive topic. No quiz question — keeps it lightweight."""
    import hashlib
    import random

    chat_id = job["chat_id"]
    last_hash = job.get("last_content_hash")
    seen_hashes = list(job.get("seen_keys") or [])

    from bot.quiz import _get_adaptive_topic, HCS_GS_TOPICS

    try:
        topic = _get_adaptive_topic(chat_id, "")
    except Exception:
        topic = random.choice(HCS_GS_TOPICS)

    fact_block = _generate_daily_facts([topic])
    if not fact_block:
        return None, ""

    content = f"⏰ *Fact of the Day — {topic}*\n\n{fact_block}"
    content_hash = hashlib.md5(content.encode()).hexdigest()

    if content_hash == last_hash or content_hash in seen_hashes:
        # Regenerate with a different topic
        try:
            topic = random.choice(HCS_GS_TOPICS)
            fact_block = _generate_daily_facts([topic])
            content = f"⏰ *Fact of the Day — {topic}*\n\n{fact_block}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
        except Exception:
            return None, last_hash or ""

    # Prompt user to confirm they've read it — reply triggers a quiz question
    content += "\n\n_Read it? Reply *got it* and I'll test you on this! 💪_"

    seen_hashes.append(content_hash)
    if len(seen_hashes) > 50:
        seen_hashes = seen_hashes[-50:]
    try:
        # Store the topic so handler can generate a matching quiz when user replies
        sb.table("scheduled_jobs").update({"seen_keys": seen_hashes, "subject": topic})\
            .eq("chat_id", job["chat_id"]).eq("job_type", "fact_drill").execute()
    except Exception as e:
        print(f"[scheduler] fact_drill seen_keys update failed: {e}")

    return content, content_hash


def _generate_nightly_revision(job: dict) -> tuple[str, str]:
    import hashlib
    from datetime import datetime, timezone, timedelta
    from bot.llm import create_completion

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

    # Build topic list for daily facts: weak topics first, then today's topics
    fact_topics = [r["topic"] for r in weak] if weak else []

    # 3. Get streak
    try:
        profile_res = sb.table("user_profiles").select("study_streak").eq("chat_id", chat_id).execute()
        streak = (profile_res.data[0].get("study_streak") or 0) if profile_res.data else 0
    except Exception:
        streak = 0

    # 3b. Get exam countdown
    try:
        from bot.memory import get_exam_date, _days_until
        exam_date = get_exam_date(chat_id)
        days_left = _days_until(exam_date) if exam_date else None
    except Exception:
        days_left = None

    # 4. LLM: extract today's topics + key facts from conversations
    today_summary = ""
    if messages:
        convo_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:200]}" for m in messages[-30:]
        )
        try:
            today_summary = create_completion(
                messages=[{"role": "user", "content":
                    "From this HCS study chat, extract:\n"
                    "1. Topics the student studied today (list up to 4, short names)\n"
                    "2. Up to 3 key facts worth remembering\n\n"
                    "Format:\nTopics: [topic1, topic2]\nKey Facts:\n• fact1\n• fact2\n\n"
                    f"Chat:\n{convo_text}"
                }],
                max_tokens=200,
            )
        except Exception:
            today_summary = ""

    # If no weak topics yet, try extracting from today's summary
    if not fact_topics and today_summary:
        import re as _re
        m = _re.search(r"Topics:\s*\[([^\]]+)\]", today_summary)
        if m:
            fact_topics = [t.strip() for t in m.group(1).split(",") if t.strip()]

    # 5. Build the message
    from datetime import date
    date_str = date.today().strftime("%d %b %Y")
    streak_line = f"🔥 Day *{streak}* streak!\n\n" if streak >= 2 else ""

    countdown_line = ""
    if days_left is not None:
        if days_left == 0:
            countdown_line = "🎯 *Today is your HCS exam — all the best!*\n\n"
        elif days_left <= 7:
            countdown_line = f"⚠️ *{days_left} days to exam!* Final sprint — maximize revision.\n\n"
        else:
            countdown_line = f"⏳ *{days_left} days to your HCS exam.* Stay consistent!\n\n"

    parts = [f"*📚 Nightly Revision — {date_str}*\n\n{streak_line}{countdown_line}"]

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

    facts_block = _generate_daily_facts(fact_topics)
    if facts_block:
        parts.append(facts_block)

    parts.append("_Reply *quiz me* to drill your weak topics, or *my progress* for full stats._")

    content = "\n\n".join(parts)
    content_hash = hashlib.md5(content.encode()).hexdigest()

    if content_hash == last_hash:
        return None, last_hash

    return content, content_hash

NUDGE_MESSAGE = (
    "📚 *Hey! Yudhister here — haven't seen you studying today.*\n\n"
    "Even 10 minutes of practice makes a difference in the long run. "
    "The students who crack HCS aren't necessarily the smartest — they're the most consistent.\n\n"
    "Reply *quiz me* for a quick 5-question drill, or *hpsc mock* for a full practice session. "
    "Let's keep that streak alive! 💪"
)

DAILY_FACT_PROMPT = (
    "You are Yudhister, an HCS professor. Generate exactly 2 surprising, exam-relevant facts "
    "from the following HCS syllabus topic(s): {topics}.\n\n"
    "Rules:\n"
    "- Each fact must be a memorable one-liner under 40 words\n"
    "- Frame it as something a student will remember on exam day\n"
    "- After each fact, add a short '(Why it matters: ...)' note in italics\n"
    "- Use 'By the way —' to open the first fact, nothing before it\n"
    "- No preamble like 'Here are' or 'Sure!'\n\n"
    "Output format:\n"
    "• By the way — [fact 1]. _(Why it matters: ...)_\n"
    "• [fact 2]. _(Why it matters: ...)_"
)

DAILY_FACT_PROMPT_WITH_CONTEXT = (
    "You are Yudhister, an HCS professor. A student is about to answer this question:\n\n"
    "{question}\n\n"
    "Generate exactly 1 surprising fact that directly relates to the concept in this question. "
    "It should help the student understand the topic better before answering.\n\n"
    "Rules:\n"
    "- One memorable fact under 40 words\n"
    "- Must be directly about the same concept/event/topic as the question\n"
    "- Add '_(Why it matters: ...)_' after the fact\n"
    "- Start with 'By the way —'\n"
    "- No preamble like 'Here are' or 'Sure!'\n\n"
    "Output:\n"
    "• By the way — [fact]. _(Why it matters: ...)_"
)

async def _check_inactive_users():
    """Every 4 hours: nudge users who haven't studied today (UTC) and were active in the last 7 days."""
    from datetime import date

    # Only send nudges between 8 AM and 10 PM IST (02:30–16:30 UTC)
    now_utc = datetime.now(timezone.utc)
    utc_minutes = now_utc.hour * 60 + now_utc.minute
    if not (150 <= utc_minutes <= 990):  # 02:30 = 150 min, 16:30 = 990 min
        print("[scheduler] inactivity nudge skipped — outside 8 AM–10 PM IST window")
        return

    today = date.today().isoformat()
    seven_days_ago = (date.today() - timedelta(days=7)).isoformat()

    try:
        res = sb.table("user_profiles")\
            .select("chat_id,last_active_date")\
            .not_.is_("last_active_date", "null")\
            .gte("last_active_date", seven_days_ago)\
            .neq("last_active_date", today)\
            .execute()
        inactive_users = res.data or []
    except Exception as e:
        print(f"[scheduler] inactivity check — failed to query user_profiles: {e}")
        return

    if not inactive_users:
        print("[scheduler] inactivity check — no inactive users to nudge")
        return

    print(f"[scheduler] inactivity check — {len(inactive_users)} candidate(s)")

    for user in inactive_users:
        chat_id = user["chat_id"]
        try:
            # Check if we already sent a nudge today to avoid double-nudging
            today_start = f"{today}T00:00:00+00:00"
            conv_res = sb.table("conversations")\
                .select("id")\
                .eq("chat_id", chat_id)\
                .eq("role", "assistant")\
                .gte("created_at", today_start)\
                .ilike("content", "%Haven't studied today yet%")\
                .limit(1)\
                .execute()
            if conv_res.data:
                print(f"[scheduler] nudge already sent today to {chat_id} — skipping")
                continue

            await send_message(chat_id, NUDGE_MESSAGE)
            # Record the nudge in conversations so we don't send again today
            sb.table("conversations").insert({
                "chat_id": chat_id,
                "role": "assistant",
                "content": NUDGE_MESSAGE,
            }).execute()
            print(f"[scheduler] nudge sent to {chat_id}")
        except Exception as e:
            print(f"[scheduler] nudge failed for {chat_id}: {e}")


def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(_run_due_jobs, "interval", minutes=1, id="job_runner")
    _scheduler.add_job(_check_inactive_users, "interval", hours=4, id="inactivity_checker")
    _scheduler.start()
    print("[scheduler] started")

def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown()
