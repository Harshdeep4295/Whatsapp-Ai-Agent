import json
from bot.llm import get_client

INTENT_PROMPT = """Classify this message from an exam prep student. Return ONLY valid JSON, nothing else.

Intents: SYLLABUS, PAPER, QUIZ, ANSWER, EXPLAIN, NEWS, STUDY_PLAN, SCHEDULE, CANCEL_SCHEDULE, GENERAL

Example: {"intent": "QUIZ", "exam": "HCS", "subject": "CSAT", "year": null, "schedule_text": null}

Rules:
- QUIZ = user wants a practice question, MCQ, test question, or says "quiz me", "practice question", "give me a question", "test me" — this includes subject-specific practice like "CSAT question", "Polity MCQ", "reasoning question"
- ANSWER = user replied A/B/C/D or a short answer to a quiz question
- PAPER = user wants past/previous year question paper
- SYLLABUS = user wants topics list, syllabus, or what to study
- EXPLAIN = user wants a concept explained, or asks "what is", "how does", "why"
- STUDY_PLAN = user wants a study plan, schedule, or timetable
- SCHEDULE = user wants recurring automated updates (e.g. "send me every hour", "remind me daily") — extract the scheduling phrase
- CANCEL_SCHEDULE = user wants to stop scheduled updates
- NEWS = user explicitly asks for current affairs or news
- GENERAL = anything else (greetings, off-topic, unclear)
- exam can be ANY exam — UPSC, JEE, NEET, HCS, HPSC, SSC, IBPS, RAS, IELTS, CAT, GMAT, GRE, SAT, AWS, CBSE, or any other
- subject = the specific topic/paper (e.g. "CSAT", "Polity", "Reasoning", "Maths", "GK", "English")
- If no exam mentioned, set exam to null
- Extract year if mentioned
- For SCHEDULE: put the full scheduling phrase in schedule_text AND detect what to schedule (quiz/news/syllabus) in subject"""

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
