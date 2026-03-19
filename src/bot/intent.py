import json
from bot.llm import get_client

INTENT_PROMPT = """Classify this message from an HCS (Haryana Civil Services) exam prep student. Return ONLY valid JSON, nothing else.

Intents: SYLLABUS, PAPER, QUIZ, EXPLAIN, NEWS, STUDY_PLAN, SCHEDULE, CANCEL_SCHEDULE, MOCK_TEST, STUDY_SESSION, PROGRESS, GENERAL

Example: {"intent": "QUIZ", "subject": "CSAT", "year": null, "schedule_text": null, "count": null}

Rules:
- QUIZ = user wants a practice question, MCQ, or says "quiz me", "practice", "test me", "give me a question"
- MOCK_TEST = user wants a mock test, full test, or "give me X questions mock test". Extract count from message (default 10).
- STUDY_SESSION = user wants a guided study session — "let's study X", "study session on X", "teach me X"
- PAPER = user wants past/previous year question paper
- SYLLABUS = user wants topics list, syllabus, or what to study
- EXPLAIN = user wants a concept explained — "what is", "how does", "why", "explain", "tell me about"
- STUDY_PLAN = user wants a study plan, schedule, timetable, or "how to prepare"
- SCHEDULE = ONLY when user explicitly wants AUTOMATED recurring messages (e.g. "send me every hour", "remind me daily at 8am"). NEVER classify one-word replies like "yes", "sure", "ok" as SCHEDULE.
- CANCEL_SCHEDULE = user wants to stop scheduled updates ("stop updates", "cancel reminders")
- NEWS = user explicitly asks for current affairs or news updates
- PROGRESS = user wants to see their stats, progress, score history, streak, or what to focus on — "my progress", "how am I doing", "show my stats", "my score", "my weak topics", "what should I study"
- GENERAL = greetings, "yes", "sure", "ok", "continue", "go on", "thanks", vague replies, or anything not fitting above

Critical:
- Short words like "yes", "sure", "ok", "okay", "go on", "continue", "great", "thanks", "yep" are ALWAYS GENERAL
- subject = specific HCS topic (e.g. "CSAT", "Polity", "Haryana GK", "Reasoning", "Economy", "History")
- If no specific subject mentioned, set subject to null
- Extract year if mentioned (e.g. 2023, 2024, 2026)
- For SCHEDULE: put full scheduling phrase in schedule_text
- For MOCK_TEST: put number of questions in count (integer, default 10 if not specified)"""

def detect_intent(text: str) -> dict:
    # Short/common continuation words — always GENERAL, skip LLM call
    short_words = {"yes", "sure", "ok", "okay", "yep", "yeah", "yup", "no", "nope",
                   "great", "thanks", "thank you", "go on", "continue", "got it",
                   "good", "nice", "cool", "fine", "alright", "right", "correct",
                   "hmm", "hm", "oh", "ah", "interesting", "understood", "i see"}
    if text.strip().lower() in short_words:
        return {"intent": "GENERAL", "subject": None, "year": None, "schedule_text": None, "count": None}

    client = get_client()
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": text}
            ],
            max_tokens=80,
            temperature=0,
        )
        result = json.loads(response.choices[0].message.content)
        result.setdefault("count", None)
        return result
    except Exception:
        return {"intent": "GENERAL", "subject": None, "year": None, "schedule_text": None, "count": None}
