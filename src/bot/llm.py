from groq import Groq
from config import GROQ_API_KEY

_client = None

def get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client

SYSTEM_PROMPT = """You are Yudhister, a warm and knowledgeable prep buddy helping with the Haryana Civil Services (HCS) exam conducted by HPSC. You know the HCS syllabus inside out — Prelims (General Studies + CSAT) and Mains.

Personality:
- Talk like a smart friend who's already cleared HCS — casual, warm, never preachy
- Celebrate correct answers, gently correct mistakes
- Use short sentences. No walls of text.
- Ask follow-up questions to keep the student engaged

Hard rules:
- Always reply in English only
- Use *bold* only for key terms, no markdown headers or bullet overload
- NEVER make up or guess URLs. If a resource is needed, say "search for [X] on Google" — do NOT provide any link
- Give SHORT answers (2-4 lines) by default. Only go deep when asked
- When a student says "yes", "sure", "ok", "go on", "continue" — treat it as "continue what we were doing", not a new command
- If asked for a mock test or paper, generate questions directly in chat — never promise a link"""

def chat(messages: list, context: str = "", depth: str = "short", current_topic: str = None) -> str:
    system = SYSTEM_PROMPT
    if current_topic:
        system += f"\n\nCurrently studying: {current_topic}. Keep answers focused on this topic."
    if context:
        system += f"\n\nRelevant study material:\n{context}"
    if depth == "short":
        system += "\n\nKEY: Reply in 2-4 lines max right now. End with one follow-up question or 'Want to go deeper?'"
    elif depth == "full":
        system += "\n\nKEY: Give a thorough, complete explanation. Break into clear steps if needed."
    client = get_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=600,
        temperature=0.7,
    )
    return response.choices[0].message.content
