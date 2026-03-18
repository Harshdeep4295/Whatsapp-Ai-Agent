from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

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
