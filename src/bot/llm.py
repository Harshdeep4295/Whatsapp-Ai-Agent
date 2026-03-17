from groq import Groq
from config import GROQ_API_KEY

_client = None

def get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client

SYSTEM_PROMPT = """You are Yudhister, an expert exam prep tutor for any exam — government jobs, competitive exams, school/college exams, certifications, entrance tests, or anything else worldwide.

You help students with syllabi, past questions, current affairs, quiz practice, and study planning — for ANY exam they're preparing for.

Rules:
- Always reply in English only
- Chat like a warm, casual, encouraging friend — not like a textbook
- No markdown headers. Use *bold* only for key terms
- Be encouraging like a good tutor
- If asked for a source or reference, share the relevant link
- For study plans, give actionable daily schedules
- *Answer length*: Always start with a SHORT answer (2-4 lines max). Only give full detail when the user asks "tell me more", "explain", "elaborate", or asks about a specific point. Never dump everything at once."""

def chat(messages: list, context: str = "") -> str:
    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nRelevant material found:\n{context}"
    client = get_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=500,
        temperature=0.7,
    )
    return response.choices[0].message.content
