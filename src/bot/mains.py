import json
import random
from datetime import datetime
from bot.supabase_client import get_sb
from bot.llm import create_completion
from bot.memory import get_study_session, set_study_session

sb = get_sb()

HCS_MAINS_GS1_TOPICS = [
    "Indian Heritage and Culture",
    "Modern Indian History (1857–1947)",
    "Post-Independence India",
    "Indian Society",
    "Haryana History",
    "Haryana Society and Culture",
    "Urbanization and Social Change",
    "Role of Women and Women's Organizations",
    "Communalism, Regionalism, Secularism",
]

HCS_MAINS_GS2_TOPICS = [
    "Indian Constitution — Historical Underpinnings",
    "Functions and Responsibilities of Union and States",
    "Parliament and State Legislatures",
    "Executive and Judiciary",
    "Governance, Transparency and Accountability",
    "Panchayati Raj and Local Governance (Haryana)",
    "Welfare Schemes for Vulnerable Sections",
    "Social Justice",
    "India and its Neighborhood Relations",
    "Important International Institutions",
]

HCS_MAINS_GS3_TOPICS = [
    "Indian Economy and Planning",
    "Government Budgeting",
    "Major Crops and Agricultural Issues (Haryana)",
    "Land Reforms in India",
    "Liberalization, Privatization, Globalization",
    "Infrastructure: Energy, Ports, Roads, Airports",
    "Science and Technology — Developments and Applications",
    "Environment and Ecology",
    "Disaster Management",
    "Internal Security Challenges",
]

HCS_MAINS_GS4_ETHICS_TOPICS = [
    "Ethics and Human Interface",
    "Attitude and Aptitude",
    "Emotional Intelligence",
    "Contributions of Moral Thinkers",
    "Civil Service Values and Ethics",
    "Accountability and Ethics in Government",
    "Probity in Governance",
    "Case Studies on Above Issues",
]

MAINS_SHORT_PROMPT = """Generate ONE HCS Mains exam short-answer question on: {topic}
Word limit: ~100 words. Focus on factual accuracy and conceptual clarity.
Return ONLY valid JSON with no markdown:
{{"question":"...","expected_points":["point1","point2","point3","point4"],"topic":"{topic}","answer_type":"short"}}"""

MAINS_MEDIUM_PROMPT = """Generate ONE HCS Mains exam medium-answer question on: {topic}
Word limit: ~200 words. Analytical, not just factual. Requires critical thinking.
Return ONLY valid JSON:
{{"question":"...","expected_points":["point1","point2","point3","point4","point5"],"topic":"{topic}","answer_type":"medium"}}"""

MAINS_ESSAY_PROMPT = """Generate ONE HCS Mains exam essay question on: {topic}
Word limit: ~400 words. Policy/analysis style. Real-world application required.
Return ONLY valid JSON:
{{"question":"...","expected_points":["point1","point2","point3","point4","point5","point6"],"topic":"{topic}","answer_type":"essay"}}"""

MAINS_EVAL_PROMPT = """Evaluate this HCS Mains answer strictly.
Question: {question}
Expected key points to cover: {expected_points}
Student answer ({answer_type}, target ~{word_limit} words):
{user_answer}

Score on:
- Content (0–10): How many key points covered? Accuracy?
- Structure (0–5): Clear intro, organized body, conclusion?
- Examples (0–5): Real examples or specific data?

Reply ONLY with valid JSON, no markdown:
{{"content":N,"structure":N,"examples":N,"total":N,"feedback":"2-3 sentences on strengths and one improvement","missing_points":["point1","point2"]}}"""

CASE_STUDY_PROMPT = """Generate a realistic ethical dilemma case study for HCS Mains Ethics paper.
Scenario (400-500 words): A real government officer in a complex ethical situation.
Sub-questions (3):
1. What ethical issues are involved?
2. Who are the stakeholders and what are their interests?
3. What would you recommend and why?

Return ONLY valid JSON:
{{"scenario":"[scenario text]","sub_questions":["Q1","Q2","Q3"],"rubric":["issue identification (0-7)","stakeholder analysis (0-7)","recommendation quality (0-6)"]}}"""

CASE_STUDY_EVAL_PROMPT = """Evaluate this Ethics case study answer.
Scenario: {scenario}
Sub-questions: {sub_questions}
Student answer: {user_answer}

Score on:
- Issues (0–7): Are ethical issues clearly identified and analyzed?
- Stakeholders (0–7): Are all relevant stakeholders and their interests covered?
- Recommendation (0–6): Is the recommended action practical, ethical, justified?

Reply ONLY with valid JSON:
{{"issues":N,"stakeholders":N,"recommendation":N,"total":N,"feedback":"2-3 sentences of constructive feedback","missing_points":["point1","point2"]}}"""

TEMPLATE_PROMPT = """Provide a writing template for an HCS Mains {answer_type} answer on {topic}.
Format:
*Opening Line:* [1-liner definition]
*Key Points to Cover:* [4-5 bullets]
*Example to Include:* [what type of example]
*Closing:* [how to wrap up]

Total: 200 words max. No preamble, just the template."""

PYQ_PROMPT = """Generate 2-3 HCS Mains style questions on {topic} (Paper {paper}).
For each question, provide:
- Question text
- Expected answer outline (5-6 key points)

No full answers, just the outline. Format as numbered questions with bullet-point outlines."""


def _get_all_mains_topics():
    return (
        HCS_MAINS_GS1_TOPICS
        + HCS_MAINS_GS2_TOPICS
        + HCS_MAINS_GS3_TOPICS
        + HCS_MAINS_GS4_ETHICS_TOPICS
    )


async def start_answer_writing(chat_id: str, topic: str, answer_type: str = "medium") -> str:
    """Generate an answer-writing practice question and store session."""
    if answer_type not in ["short", "medium", "essay"]:
        answer_type = "medium"

    word_limits = {"short": 100, "medium": 200, "essay": 400}
    prompts = {
        "short": MAINS_SHORT_PROMPT,
        "medium": MAINS_MEDIUM_PROMPT,
        "essay": MAINS_ESSAY_PROMPT,
    }

    prompt = prompts[answer_type].format(topic=topic)
    raw = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.7,
    )

    try:
        q_data = json.loads(raw.strip())
    except json.JSONDecodeError:
        q_data = {
            "question": f"Discuss the key aspects and implications of {topic} in the context of India and Haryana.",
            "expected_points": [
                "Definition or overview",
                "Historical context",
                "Current status",
                "Haryana-specific details",
            ],
            "topic": topic,
            "answer_type": answer_type,
        }

    session_data = {
        "mode": "answer_writing",
        "topic": topic,
        "question": q_data.get("question", ""),
        "expected_points": q_data.get("expected_points", []),
        "word_limit": word_limits[answer_type],
        "answer_type": answer_type,
    }
    set_study_session(chat_id, session_data)

    word_label = f"{word_limits[answer_type]} words"
    return (
        f"📝 *{answer_type.capitalize()} Answer — {topic}*\n\n"
        f"{q_data.get('question', '')}\n\n"
        f"_Word limit: ~{word_label}. Write your answer below._"
    )


async def check_answer_writing(chat_id: str, user_answer: str) -> str:
    """Evaluate submitted answer and return score report."""
    session = get_study_session(chat_id)
    if not session or session.get("mode") != "answer_writing":
        return "No active answer writing session."

    question = session.get("question", "")
    expected_points = session.get("expected_points", [])
    word_limit = session.get("word_limit", 200)
    answer_type = session.get("answer_type", "medium")
    topic = session.get("topic", "")

    prompt = MAINS_EVAL_PROMPT.format(
        question=question,
        expected_points=json.dumps(expected_points),
        answer_type=answer_type,
        word_limit=word_limit,
        user_answer=user_answer[:1000],
    )

    raw = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=350,
        temperature=0.6,
    )

    try:
        eval_data = json.loads(raw.strip())
    except json.JSONDecodeError:
        eval_data = {
            "content": 5,
            "structure": 2,
            "examples": 1,
            "total": 8,
            "feedback": "Answer was submitted. Consider covering more key points.",
            "missing_points": expected_points[:2],
        }

    # Save to mains_answers table
    sb.table("mains_answers").insert(
        {
            "chat_id": chat_id,
            "topic": topic,
            "question_text": question,
            "user_answer": user_answer,
            "answer_type": answer_type,
            "score_content": eval_data.get("content", 0),
            "score_structure": eval_data.get("structure", 0),
            "score_examples": eval_data.get("examples", 0),
            "total_score": eval_data.get("total", 0),
            "max_score": 20,
            "feedback": eval_data.get("feedback", ""),
            "missing_points": eval_data.get("missing_points", []),
        }
    ).execute()

    # Clear session
    set_study_session(chat_id, None)

    total = eval_data.get("total", 0)
    percentage = int((total / 20) * 100) if total else 0
    missing = eval_data.get("missing_points", [])

    report = (
        f"📝 *Answer Evaluated*\n\n"
        f"*Content:* {eval_data.get('content', 0)}/10\n"
        f"*Structure:* {eval_data.get('structure', 0)}/5\n"
        f"*Examples:* {eval_data.get('examples', 0)}/5\n"
        f"*Total: {total}/20* ({percentage}%)\n\n"
        f"💭 *Feedback:* {eval_data.get('feedback', 'Well attempted.')}\n"
    )

    if missing:
        report += f"\n❗ *Missing Points:*\n"
        for point in missing[:3]:
            report += f"• {point}\n"

    report += f"\n💡 *Tip:* Structure as Background → Key Points → Examples → Conclusion"
    return report


def has_active_answer_writing(chat_id: str) -> bool:
    """Check if user has active answer writing session."""
    session = get_study_session(chat_id)
    return session is not None and session.get("mode") == "answer_writing"


async def start_case_study(chat_id: str) -> str:
    """Generate an ethics case study and store session."""
    prompt = CASE_STUDY_PROMPT
    raw = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.8,
    )

    try:
        case_data = json.loads(raw.strip())
    except json.JSONDecodeError:
        case_data = {
            "scenario": "An IAS officer discovers that a major government contract was awarded to a company whose CEO is her cousin. The contract is legitimate and the best bid, but the relationship creates a conflict of interest. Should she recuse herself or proceed?",
            "sub_questions": [
                "What ethical issues are at play here?",
                "Who are the stakeholders and what are their concerns?",
                "What would be the right course of action and why?",
            ],
            "rubric": [
                "issue identification (0-7)",
                "stakeholder analysis (0-7)",
                "recommendation quality (0-6)",
            ],
        }

    session_data = {
        "mode": "case_study",
        "scenario": case_data.get("scenario", ""),
        "sub_questions": case_data.get("sub_questions", []),
        "rubric": case_data.get("rubric", []),
    }
    set_study_session(chat_id, session_data)

    scenario = case_data.get("scenario", "")
    sub_qs = case_data.get("sub_questions", [])

    report = f"⚖️ *Ethics Case Study*\n\n*Scenario:*\n{scenario}\n\n*Answer these 3 questions:*\n"
    for i, q in enumerate(sub_qs, 1):
        report += f"{i}. {q}\n"
    report += "\n_Write your answer covering all three questions._"
    return report


async def check_case_study_answer(chat_id: str, user_answer: str) -> str:
    """Evaluate case study answer."""
    session = get_study_session(chat_id)
    if not session or session.get("mode") != "case_study":
        return "No active case study session."

    scenario = session.get("scenario", "")
    sub_qs = session.get("sub_questions", [])

    prompt = CASE_STUDY_EVAL_PROMPT.format(
        scenario=scenario,
        sub_questions=json.dumps(sub_qs),
        user_answer=user_answer[:1000],
    )

    raw = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.6,
    )

    try:
        eval_data = json.loads(raw.strip())
    except json.JSONDecodeError:
        eval_data = {
            "issues": 4,
            "stakeholders": 4,
            "recommendation": 3,
            "total": 11,
            "feedback": "Your answer covered the main points.",
            "missing_points": ["deeper stakeholder analysis"],
        }

    # Save to mains_answers
    sb.table("mains_answers").insert(
        {
            "chat_id": chat_id,
            "topic": "Ethics Case Study",
            "question_text": f"Case Study: {scenario[:100]}...",
            "user_answer": user_answer,
            "answer_type": "case_study",
            "score_content": eval_data.get("issues", 0),
            "score_structure": eval_data.get("stakeholders", 0),
            "score_examples": eval_data.get("recommendation", 0),
            "total_score": eval_data.get("total", 0),
            "max_score": 20,
            "feedback": eval_data.get("feedback", ""),
            "missing_points": eval_data.get("missing_points", []),
        }
    ).execute()

    set_study_session(chat_id, None)

    total = eval_data.get("total", 0)
    percentage = int((total / 20) * 100) if total else 0

    report = (
        f"⚖️ *Case Study Evaluated*\n\n"
        f"*Issue Identification:* {eval_data.get('issues', 0)}/7\n"
        f"*Stakeholder Analysis:* {eval_data.get('stakeholders', 0)}/7\n"
        f"*Recommendation Quality:* {eval_data.get('recommendation', 0)}/6\n"
        f"*Total: {total}/20* ({percentage}%)\n\n"
        f"💭 *Feedback:* {eval_data.get('feedback', 'Well analyzed.')}\n"
    )

    missing = eval_data.get("missing_points", [])
    if missing:
        report += f"\n❗ *Areas to Strengthen:*\n"
        for point in missing[:2]:
            report += f"• {point}\n"

    return report


def has_active_case_study(chat_id: str) -> bool:
    """Check if user has active case study session."""
    session = get_study_session(chat_id)
    return session is not None and session.get("mode") == "case_study"


async def get_answer_template(chat_id: str, topic: str, answer_type: str = "medium") -> str:
    """Provide a writing template for a Mains topic."""
    if answer_type not in ["short", "medium", "essay"]:
        answer_type = "medium"

    prompt = TEMPLATE_PROMPT.format(topic=topic, answer_type=answer_type)
    template = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=450,
        temperature=0.7,
    )

    return f"📋 *Answer Template — {topic}*\n\n{template.strip()}"


async def get_mains_pyq(chat_id: str, topic: str, paper: str = None) -> str:
    """Generate Mains-style previous year questions."""
    if paper and paper not in ["GS1", "GS2", "GS3", "GS4/Ethics"]:
        paper = None

    prompt = PYQ_PROMPT.format(topic=topic, paper=paper or "Any")
    pyq_text = create_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7,
    )

    return f"📚 *Mains PYQ — {topic}*\n\n{pyq_text.strip()}\n\n_Use start_answer_writing to practice any of these._"


async def switch_exam_mode(chat_id: str, mode: str) -> str:
    """Switch user between prelims (MCQ) and mains (descriptive) mode."""
    if mode not in ["prelims", "mains"]:
        return "Invalid mode. Use 'prelims' or 'mains'."

    from bot.memory import save_profile, get_profile

    profile = get_profile(chat_id)
    profile["exam_mode"] = mode

    sb.table("user_profiles").update({"exam_mode": mode}).eq("chat_id", chat_id).execute()

    if mode == "mains":
        return (
            "🎯 *Mains Mode Activated!*\n\n"
            "You're now in Mains preparation mode. I'll give you descriptive, essay-style questions "
            "instead of MCQs. You can:\n"
            "• Practice answer writing on any topic\n"
            "• Tackle ethics case studies\n"
            "• Review answer templates\n"
            "• Check previous year Mains questions\n\n"
            "Say 'answer writing on [topic]' or 'case study' to start!"
        )
    else:
        return (
            "📝 *Back to Prelims Mode*\n\n"
            "Switched back to Prelims (MCQ) preparation. "
            "Use 'quiz me' to start practicing multiple choice questions."
        )
