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
    _is_conf_waiting, record_confidence,
)
from bot.whatsapp import send_message

WELCOME_MSG = (
    "Hey! I'm *Yudhister* 👋 — your personal HCS exam coach.\n\n"
    "Here's everything I can do for you:\n\n"
    "*📝 Practice & Tests*\n"
    "• *quiz me* — adaptive questions on your weak topics\n"
    "• *rapid fire* — 5 questions, no pause, maximum pressure ⚡\n"
    "• *hpsc mock* — 25-question blueprint mock (real exam format)\n"
    "• *haryana special* — Haryana-only drill (folk culture, 1857, geography)\n"
    "• *mock test* — quick 10-question test on any topic\n\n"
    "*📚 Study*\n"
    "• *study [topic]* — passage + comprehension on any topic\n"
    "• *explain [topic]* — guided study session with questions\n"
    "• *current affairs* — latest HCS-relevant news\n"
    "• *search [anything]* — I'll look it up and summarise for you\n\n"
    "*⏰ Drills & Tracking*\n"
    "• *drill me* — instant fact + question on your weakest topic\n"
    "• *my progress* — see your topic-wise accuracy\n"
    "• *wrong answers* — review your mistakes\n"
    "• *set exam date [date]* — I'll track your countdown\n\n"
    "I'll also send you:\n"
    "• A *morning kickoff* at 9 AM with your daily focus plan\n"
    "• A *fact drill* every 2 hours to keep your memory sharp\n\n"
    "What do you want to start with? 🎯"
)

GREETINGS = {"hi", "hello", "hey", "hii", "helo", "helloo", "heyy", "yo", "sup",
             "good morning", "good evening", "good afternoon", "good night",
             "gm", "howdy", "namaste", "namaskar", "hlo", "hola"}

STOP_PHRASES = {"stop", "quit", "end", "end quiz", "stop quiz", "end test", "stop test",
                "end session", "stop session"}
SKIP_PHRASES = {"don't know", "dont know", "idk", "skip", "pass", "no idea", "not sure", "?"}


async def _quiz_reply(chat_id: str, text: str, q_data: dict | None) -> None:
    save_message(chat_id, "assistant", text)
    await send_message(chat_id, text)
    if q_data:
        topic = q_data.get("topic", "")
        topic_line = f"_Topic: {topic}_\n\n" if topic else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q_data["options"].items())
        q_text = f"{topic_line}{q_data['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"
        await send_message(chat_id, q_text)


def _get_drill_session(chat_id: str) -> bool:
    """Return True if the active quiz_session is a DRILL (including CONF/ERR states)."""
    try:
        from bot.supabase_client import get_sb
        res = get_sb().table("quiz_sessions").select("exam")\
            .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
        exam = (res.data[0].get("exam") or "") if res.data else ""
        return exam == "DRILL" or exam.startswith("DRILL:")
    except Exception:
        return False


def _morning_kickoff_pending(chat_id: str) -> bool:
    """True if morning kickoff was sent in the last 2 hours."""
    from datetime import datetime, timezone, timedelta
    from bot.supabase_client import get_sb
    try:
        window = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        res = get_sb().table("conversations")\
            .select("id").eq("chat_id", chat_id).eq("role", "assistant")\
            .gte("created_at", window)\
            .ilike("content", "%Today's focus%")\
            .limit(1).execute()
        return bool(res.data)
    except Exception:
        return False


def _is_nightly_pending(chat_id: str) -> bool:
    """True if nightly revision was sent in the last 30 minutes (difficulty reply window)."""
    from datetime import datetime, timezone, timedelta
    from bot.supabase_client import get_sb
    try:
        window = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        res = get_sb().table("conversations")\
            .select("id").eq("chat_id", chat_id).eq("role", "assistant")\
            .gte("created_at", window)\
            .ilike("content", "%How's the difficulty%")\
            .limit(1).execute()
        return bool(res.data)
    except Exception:
        return False


def _reschedule_drill(chat_id: str, minutes: int = 45) -> None:
    """Move the active fact_drill job's next_run_at to now + minutes.
    Creates a new job if none exists."""
    from datetime import datetime, timezone, timedelta
    from bot.supabase_client import get_sb
    next_run = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    try:
        res = get_sb().table("scheduled_jobs")\
            .update({"next_run_at": next_run.isoformat()})\
            .eq("chat_id", chat_id).eq("job_type", "fact_drill").eq("active", True)\
            .execute()
        if not res.data:
            from bot.scheduler import schedule_job
            schedule_job(chat_id, "fact_drill", minutes, next_run_at=next_run)
    except Exception as e:
        print(f"[handler] _reschedule_drill failed: {e}")


async def _maybe_fire_overdue_drill(chat_id: str) -> None:
    """If a fact_drill job is overdue and the user just messaged in, send the drill now
    instead of waiting for the background scheduler tick."""
    from datetime import datetime, timezone, timedelta
    from bot.supabase_client import get_sb
    try:
        now = datetime.now(timezone.utc)
        res = get_sb().table("scheduled_jobs")\
            .select("*")\
            .eq("chat_id", chat_id).eq("job_type", "fact_drill").eq("active", True)\
            .lte("next_run_at", now.isoformat())\
            .limit(1).execute()
        if not res.data:
            return
        job = res.data[0]
        from bot.scheduler import _generate_fact_drill
        content, content_hash = _generate_fact_drill(job)
        if content:
            await send_message(chat_id, content)
            next_run = now + timedelta(minutes=job.get("interval_minutes", 120))
            get_sb().table("scheduled_jobs").update({
                "next_run_at": next_run.isoformat(),
                "last_content_hash": content_hash,
            }).eq("id", job["id"]).execute()
    except Exception as e:
        print(f"[handler] _maybe_fire_overdue_drill failed: {e}")


async def handle_message(chat_id: str, sender: str, user_text: str, is_group: bool = False) -> str | None:
    save_message(chat_id, "user", user_text)
    update_streak(chat_id)

    # Fire overdue drill immediately when the user comes back (skip if mid-session)
    if not (has_active_quiz(chat_id) or has_active_mock_test(chat_id)
            or has_active_study_session(chat_id) or has_active_passage_quiz(chat_id)):
        await _maybe_fire_overdue_drill(chat_id)

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
            # Auto-schedule 2-hour fact drills for new users (no time restriction).
            # schedule_job deactivates any existing same-type job first, so re-onboarding
            # won't create duplicates.
            try:
                from bot.scheduler import schedule_job, _next_0330_utc
                schedule_job(chat_id, "fact_drill", 120)
                schedule_job(chat_id, "morning_kickoff", 1440, next_run_at=_next_0330_utc())
            except Exception as e:
                print(f"[handler] failed to auto-schedule jobs for {chat_id}: {e}")
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

    # --- Difficulty reply (after nightly revision) ---
    if lower in {"1", "2", "3"} and not has_active_quiz(chat_id) and not has_active_mock_test(chat_id):
        if _is_nightly_pending(chat_id):
            pref = {"1": "easy", "2": "just_right", "3": "hard"}[lower]
            from bot.supabase_client import get_sb as _gsb_diff
            _gsb_diff().table("user_profiles").update({"difficulty_preference": pref})\
                .eq("chat_id", chat_id).execute()
            ack = {
                "easy": "Got it — I'll give you more confidence-building questions 💪",
                "just_right": "Perfect, keeping the same difficulty 👍",
                "hard": "Challenge mode ON 🔥 I'll push you harder!",
            }
            reply = ack[pref]
            save_message(chat_id, "assistant", reply)
            return reply

    # --- Morning kickoff responses (START / SKIP / HARD) ---
    if not has_active_quiz(chat_id) and not has_active_mock_test(chat_id):
        if lower in {"start", "▶️ start", "begin", "let's go", "lets go"} and _morning_kickoff_pending(chat_id):
            from bot.quiz import start_batch_quiz
            text, q_data = start_batch_quiz(chat_id, 5)
            await _quiz_reply(chat_id, "Let's go! 🔥 Here are your 5 questions:", None)
            await send_message(chat_id, text)
            return None

        if lower in {"skip", "⏭ skip", "skip today"} and _morning_kickoff_pending(chat_id):
            reply = "No problem — rest day it is. Come back tonight for revision! 💪"
            save_message(chat_id, "assistant", reply)
            return reply

        if lower in {"hard", "💪 hard", "hard mode"} and _morning_kickoff_pending(chat_id):
            from bot.supabase_client import get_sb as _gsb_hard
            _gsb_hard().table("user_profiles").update({"difficulty_preference": "hard"})\
                .eq("chat_id", chat_id).execute()
            from bot.quiz import start_batch_quiz
            text, q_data = start_batch_quiz(chat_id, 5)
            reply = "Challenge mode ON 🔥 Questions set to hard difficulty!"
            save_message(chat_id, "assistant", reply)
            await send_message(chat_id, reply)
            await send_message(chat_id, text)
            return None

    # --- Start auto drills ---
    start_auto_drill_triggers = {
        "start auto drills", "start auto drill",
        "start drills", "start drill",
        "auto drills on", "auto drill on",
        "start fact drills", "start fact drill",
        "schedule drills", "schedule drill",
    }
    if any(t in lower for t in start_auto_drill_triggers):
        from bot.scheduler import schedule_job
        schedule_job(chat_id, "fact_drill", 120)
        reply = (
            "Auto drills started! ✅\n\n"
            "You'll get a new fact every 2 hours. "
            "Say *drill me* anytime for an on-demand drill, or *stop auto drills* to cancel."
        )
        save_message(chat_id, "assistant", reply)
        return reply

    # --- Stop auto drills ---
    stop_auto_drill_triggers = {
        "stop auto drills", "stop auto drill",
        "stop drills", "stop drill",
        "auto drills off", "auto drill off",
        "cancel drills", "cancel drill",
        "pause drills", "pause drill",
    }
    if any(t in lower for t in stop_auto_drill_triggers):
        from bot.supabase_client import get_sb as _get_sb
        _get_sb().table("scheduled_jobs")\
            .update({"active": False})\
            .eq("chat_id", chat_id).eq("job_type", "fact_drill")\
            .execute()
        reply = "Auto drills paused. ✅ Say *start auto drills* or *drill me* to resume."
        save_message(chat_id, "assistant", reply)
        return reply

    # --- "Got it" → quiz on the last sent fact topic ---
    got_it_triggers = {"got it", "gotit", "got it!", "ready", "test me", "test me on this",
                       "quiz me on this", "send question", "yes test me", "ok test me", "i got it"}
    if any(t in lower for t in got_it_triggers):
        from bot.supabase_client import get_sb as _gsb
        from bot.quiz import _generate
        try:
            job_res = _gsb().table("scheduled_jobs")\
                .select("subject")\
                .eq("chat_id", chat_id).eq("job_type", "fact_drill").eq("active", True)\
                .limit(1).execute()
            topic = (job_res.data[0].get("subject") or "") if job_res.data else ""
            if not topic:
                from bot.quiz import _get_adaptive_topic
                topic = _get_adaptive_topic(chat_id, "")
            q = _generate(topic)
            q_data = {"question": q["question"], "options": q["options"], "topic": q.get("_topic", topic)}
            _gsb().table("quiz_sessions").upsert({
                "chat_id": chat_id, "exam": "DRILL", "subject": topic,
                "question": q["question"], "options": q["options"],
                "correct_answer": q["correct"], "explanation": q["explanation"],
                "active": True, "score": 0, "total": 0,
            }, on_conflict="chat_id").execute()
            await _quiz_reply(chat_id, f"Here's your question on *{topic}* 🎯", q_data)
        except Exception as e:
            print(f"[handler] got_it quiz failed: {e}")
            await send_message(chat_id, "Couldn't load a question right now — try *drill me* instead!")
        return None

    # --- HPSC blueprint mock trigger ---
    # --- On-demand fact drill trigger ---
    drill_triggers = {"drill me", "fact drill", "2 hour drill", "daily drill", "give me a drill"}
    if any(t in lower for t in drill_triggers):
        from bot.scheduler import _generate_fact_with_question_context
        from bot.quiz import _get_adaptive_topic, _generate
        await send_message(chat_id, "Loading your drill... 🧠")
        try:
            topic = _get_adaptive_topic(chat_id, "")
            q = _generate(topic)
            fact = _generate_fact_with_question_context(q["question"])
            text_part = f"⏰ *Drill — {topic}*"
            if fact:
                text_part += f"\n\n{fact}"
            text_part += "\n\nTest yourself 👇"
            q_data = {"question": q["question"], "options": q["options"], "topic": q.get("_topic", topic)}
            from bot.supabase_client import get_sb
            get_sb().table("quiz_sessions").upsert({
                "chat_id": chat_id, "exam": "DRILL", "subject": q.get("_topic", topic),
                "question": q["question"], "options": q["options"],
                "correct_answer": q["correct"], "explanation": q["explanation"],
                "active": True, "score": 0, "total": 0,
            }, on_conflict="chat_id").execute()
            await _quiz_reply(chat_id, text_part, q_data)
        except Exception as e:
            print(f"[handler] drill me failed: {e}")
            await send_message(chat_id, "Couldn't load drill right now. Try again!")
        return None

    # --- Rapid fire mode ---
    rapid_fire_triggers = {"rapid fire", "rapidfire", "rapid fire mode", "speed round", "5 questions fast", "quick fire"}
    if any(t in lower for t in rapid_fire_triggers):
        if has_active_mock_test(chat_id):
            await send_message(chat_id, "Finish your current test first! 💪")
            return None
        from bot.quiz import start_rapid_fire
        await send_message(chat_id, "⚡ *Rapid Fire* — 5 questions incoming! No stopping.")
        try:
            text, q_data = start_rapid_fire(chat_id)
            await _quiz_reply(chat_id, text, q_data)
        except Exception as e:
            print(f"[handler] rapid_fire failed: {e}")
            await send_message(chat_id, "Couldn't start rapid fire right now. Try again!")
        return None

    hpsc_mock_triggers = {"hpsc mock", "blueprint mock", "full mock test", "paper 1 mock", "100 question mock", "hpsc full mock"}
    if any(t in lower for t in hpsc_mock_triggers):
        from bot.quiz import start_hpsc_mock
        await send_message(chat_id, "Starting your HPSC Blueprint Mock... generating questions now. 🧠")
        try:
            text_part, q_data = start_hpsc_mock(chat_id, n=25)
            if q_data is None:
                await send_message(chat_id, text_part)
            else:
                await _quiz_reply(chat_id, text_part, q_data)
        except Exception as e:
            print(f"[handler] hpsc_mock failed: {e}")
            await send_message(chat_id, "Sorry, I had trouble generating the mock test. Please try again in a moment!")
        return None

    # --- Haryana special drill trigger ---
    haryana_triggers = {"haryana special", "haryana quiz", "haryana drill", "haryana only", "haryana culture quiz"}
    if any(t in lower for t in haryana_triggers):
        from bot.quiz import start_haryana_special
        await send_message(chat_id, "Loading Haryana special drill — these are the cutoff-deciding topics! 🏛️")
        try:
            text_part, q_data = start_haryana_special(chat_id, n=10)
            if q_data is None:
                await send_message(chat_id, text_part)
            else:
                await _quiz_reply(chat_id, text_part, q_data)
        except Exception as e:
            print(f"[handler] haryana_special failed: {e}")
            await send_message(chat_id, "Sorry, had trouble generating those questions. Please try again!")
        return None

    # --- Active mock test intercept ---
    if has_active_mock_test(chat_id):
        if lower in STOP_PHRASES:
            from bot.supabase_client import get_sb
            get_sb().table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
            await _quiz_reply(chat_id, "Mock test ended.", None)
            return None
        if lower in SKIP_PHRASES:
            text, q_data = check_mock_answer(chat_id, "X")
            await _quiz_reply(chat_id, text, q_data)
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
        if lower in SKIP_PHRASES:
            await _quiz_reply(chat_id, *check_study_answer(chat_id, "X"))
            return None
        if _is_answer(user_text):
            await _quiz_reply(chat_id, *check_study_answer(chat_id, user_text))
            return None

    # --- Mid-quiz intercept ---
    if has_active_quiz(chat_id):
        if lower in STOP_PHRASES:
            await _quiz_reply(chat_id, *stop_quiz(chat_id))
            return None

        # CONF/ERR state: waiting for confidence/error-type reply — must check BEFORE _is_answer
        if _is_conf_waiting(chat_id):
            if lower in {"1", "2", "3"}:
                is_drill = _get_drill_session(chat_id)
                text, q_data = record_confidence(chat_id, lower)
                await _quiz_reply(chat_id, text, q_data)
                if is_drill:
                    _reschedule_drill(chat_id, 45)
                return None
            elif lower not in STOP_PHRASES and lower not in SKIP_PHRASES:
                # Any other reply (not stop/skip) while pending → re-prompt
                re_prompt = "_Reply *1*, *2*, or *3* to continue (or *skip* to move on)_"
                save_message(chat_id, "assistant", re_prompt)
                await send_message(chat_id, re_prompt)
                return None

        if lower in SKIP_PHRASES:
            is_drill = _get_drill_session(chat_id)
            if _is_conf_waiting(chat_id):
                record_confidence(chat_id, "skip")  # clear state, don't send next Q
            await _quiz_reply(chat_id, *check_answer(chat_id, "X"))
            if is_drill:
                _reschedule_drill(chat_id, 45)
            return None
        if _is_answer(user_text):
            is_drill = _get_drill_session(chat_id)
            await _quiz_reply(chat_id, *check_answer(chat_id, user_text))
            if is_drill:
                _reschedule_drill(chat_id, 45)
            return None

    # --- Tool loop (with pending-question reminder if off-topic) ---
    augmented_text = user_text
    try:
        if has_active_quiz(chat_id) or has_active_mock_test(chat_id):
            from bot.supabase_client import get_sb as _get_sb2
            sq = _get_sb2().table("quiz_sessions").select("question,options")\
                .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
            if sq.data:
                _q = sq.data[0]
                _opts = "\n".join(f"{k}. {v}" for k, v in (_q.get("options") or {}).items())
                augmented_text = (
                    f"{user_text}\n\n"
                    f"[System note — not from user: There is a pending quiz question the student hasn't answered yet. "
                    f"Answer their question above first, then gently remind them at the end: "
                    f"'By the way, your quiz question is still waiting 👆'\n"
                    f"Pending question:\n{_q['question']}\n{_opts}]"
                )
    except Exception:
        pass

    reply = await run_tool_loop(chat_id, augmented_text)
    save_message(chat_id, "assistant", reply)
    return reply
