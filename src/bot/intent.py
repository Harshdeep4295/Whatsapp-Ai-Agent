import json
from bot.llm import get_client

INTENT_PROMPT = """Classify this message. Return ONLY valid JSON, nothing else.

Intents: SYLLABUS, PAPER, QUIZ, ANSWER, EXPLAIN, NEWS, STUDY_PLAN, GENERAL

Example: {"intent": "QUIZ", "exam": "HCS", "subject": "Polity", "year": null}

Rules:
- ANSWER = user replied A/B/C/D or short answer to a quiz question
- PAPER = user wants past/previous year question paper
- SYLLABUS = user wants topics list or syllabus
- Default exam to HCS if not mentioned
- Extract year if mentioned (e.g. 2023)"""

def detect_intent(text: str) -> dict:
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
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"intent": "GENERAL", "exam": "HCS", "subject": "", "year": None}
