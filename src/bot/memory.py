from bot.supabase_client import get_sb

sb = get_sb()

def save_message(chat_id: str, role: str, content: str):
    sb.table("conversations").insert({
        "chat_id": chat_id, "role": role, "content": content
    }).execute()

def get_history(chat_id: str, limit: int = 15) -> list:
    res = sb.table("conversations")\
        .select("role,content")\
        .eq("chat_id", chat_id)\
        .order("created_at", desc=True)\
        .limit(limit).execute()
    return list(reversed(res.data))

def get_profile(chat_id: str) -> dict:
    res = sb.table("user_profiles").select("*").eq("chat_id", chat_id).execute()
    if res.data:
        return res.data[0]
    return {"chat_id": chat_id, "exam": None, "onboarded": False, "current_topic": None, "study_session": None}

def save_profile(chat_id: str, exam: str | None, onboarded: bool = True):
    data = {"chat_id": chat_id, "onboarded": onboarded}
    if exam is not None:
        data["exam"] = exam
    sb.table("user_profiles").upsert(data).execute()

def get_current_topic(chat_id: str) -> str | None:
    res = sb.table("user_profiles").select("current_topic").eq("chat_id", chat_id).execute()
    if res.data:
        return res.data[0].get("current_topic")
    return None

def set_current_topic(chat_id: str, topic: str | None):
    sb.table("user_profiles").upsert({"chat_id": chat_id, "current_topic": topic}).execute()

def get_study_session(chat_id: str) -> dict | None:
    res = sb.table("user_profiles").select("study_session").eq("chat_id", chat_id).execute()
    if res.data:
        return res.data[0].get("study_session")
    return None

def set_study_session(chat_id: str, session: dict | None):
    sb.table("user_profiles").upsert({"chat_id": chat_id, "study_session": session}).execute()

from datetime import date as _date

def update_streak(chat_id: str):
    """Increment streak if last active was yesterday; reset if gap > 1 day; no-op if already updated today."""
    try:
        today = _date.today().isoformat()
        res = sb.table("user_profiles").select("study_streak,last_active_date").eq("chat_id", chat_id).execute()
        if not res.data:
            sb.table("user_profiles").upsert({
                "chat_id": chat_id, "study_streak": 1, "last_active_date": today
            }).execute()
            return

        row = res.data[0]
        last = row.get("last_active_date")
        streak = row.get("study_streak") or 0

        if last == today:
            return  # already counted today

        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        new_streak = streak + 1 if last == yesterday else 1
        sb.table("user_profiles").update({
            "study_streak": new_streak, "last_active_date": today
        }).eq("chat_id", chat_id).execute()
    except Exception as e:
        print(f"[memory] streak update failed: {e}")
