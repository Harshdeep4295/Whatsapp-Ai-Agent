import json
import random
import re
from datetime import datetime, timezone


def _extract_letter(user_answer: str) -> str:
    """Extract A/B/C/D from answers like 'C', 'C.', 'Q1 C', 'B. Rice', etc."""
    m = re.search(r'\b([A-D])\b', user_answer.upper())
    if m:
        return m.group(1)
    return user_answer.strip().upper()[0] if user_answer.strip() else "X"
from bot.supabase_client import get_sb
from bot.llm import create_completion

sb = get_sb()

# HCS Prelims syllabus topics — questions will be drawn from these
HCS_GS_TOPICS = [
    "Indian History and Culture",
    "Haryana History and Culture",
    "Indian Geography",
    "Haryana Geography",
    "Indian Polity and Constitution",
    "Panchayati Raj and Local Governance",
    "Indian Economy and Development",
    "Haryana Economy and Agriculture",
    "Science and Technology",
    "Environment and Ecology",
    "Current Affairs — National",
    "Current Affairs — Haryana",
    "General Science",
    "Important Government Schemes",
]

HCS_CSAT_TOPICS = [
    "Blood Relations (coded family trees, generation-based reasoning)",
    "Number Coding (3-digit code language, symbol substitution)",
    "Complex Arrangement (families, ordering, seating, classification)",
    "Reading Comprehension (passage-based inference and vocabulary)",
    "Basic Numeracy (percentages, ratios, averages, profit-loss)",
    "Data Interpretation (tables, bar charts, pie charts)",
    "Logical Reasoning (syllogisms, analogies, series completion)",
    "Decision Making and Problem Solving",
]

HARYANA_SPECIAL_TOPICS = [
    "Haryana folk culture and traditions (Bhumia/Khera village deity, Ghethi/Laggar/Basan/Nohra folk vocabulary)",
    "Haryana heritage sites (Aram-i-Kausar Narnaul, Bhai ki Baoli Meham, Tomb of Sheikh Tayyab Kaithal)",
    "1857 Revolution leaders in Haryana (Rao Tularam in Ahirwal, Dhanu Singh in Faridabad, Imam Ali Qalandar in Hansi)",
    "Haryana geography — rivers, districts, dams, KMP Expressway, mountain passes",
    "Haryana government schemes 2024-25 (agriculture welfare, women empowerment, education)",
    "Haryana economy and agriculture — cotton farming crisis, GSDP growth, irrigation networks",
    "Medieval history of Haryana — Mughal period, Sultanate connections, local chieftains",
    "Haryana environment — Aravalli Green Wall project, forest cover data, water conservation",
    "Haryana art, festivals, prominent personalities and awards 2024-25",
]

# HCS Mains Topics (from mains.py — imported here for reference)
HCS_MAINS_TOPICS = {
    "GS1": [
        "Indian Heritage and Culture",
        "Modern Indian History (1857–1947)",
        "Post-Independence India",
        "Indian Society",
        "Haryana History",
        "Haryana Society and Culture",
        "Urbanization and Social Change",
        "Role of Women and Women's Organizations",
        "Communalism, Regionalism, Secularism",
    ],
    "GS2": [
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
    ],
    "GS3": [
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
    ],
    "GS4": [
        "Ethics and Human Interface",
        "Attitude and Aptitude",
        "Emotional Intelligence",
        "Contributions of Moral Thinkers",
        "Civil Service Values and Ethics",
        "Accountability and Ethics in Government",
        "Probity in Governance",
        "Case Studies on Above Issues",
    ],
}

HPSC_GS_BLUEPRINT = {
    "Indian History and Culture":     22,
    "Indian Polity and Constitution": 18,
    "General Science":                18,
    "Indian Geography":               15,
    "Indian Economy and Development": 12,
    "Haryana History and Culture":     4,
    "Science and Technology":          4,
    "Important Government Schemes":    3,
    "Haryana Geography":               2,
    "Art and Culture":                 2,
}  # Counts from actual 2023 HPSC GS paper — sum = 100

MCQ_PROMPT = """Generate ONE HCS (Haryana Civil Services) Prelims exam style MCQ strictly on this topic: {subject}

The question must:
- Be relevant to the HCS Prelims syllabus
- Match actual HPSC exam style and difficulty
- Test conceptual understanding, not just trivia
- For CSAT topics: test reasoning/aptitude skills
- For GS topics: test factual + analytical knowledge about India/Haryana
- **IMPORTANT: Use ONLY text-based data. NO charts, pie charts, bar graphs, diagrams, images, or visual elements.**
- **For Data Interpretation: embed the table/numbers DIRECTLY in the question text using simple ASCII format if needed.**

CRITICAL VALIDATION:
1. The "correct" field MUST be exactly one of: A, B, C, or D (uppercase, single character)
2. The correct answer MUST match one of the option values in your JSON
3. Your explanation MUST clearly show why that specific option (A/B/C/D) is correct
4. VERIFY: Does option[correct] exist? If "correct":"C", then options must have a "C" key.
5. **NO references to: pie chart, bar chart, graph, diagram, image, figure, visual, see the chart, refer to the graph, etc.**

Return ONLY valid JSON, nothing else:
{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"2-3 sentences: why the correct answer is right, the key concept a student must remember, and why wrong options are traps"}}"""

MCQ_STMT_PROMPT = """Generate ONE HCS (Haryana Civil Services) Prelims exam style statement-correctness question strictly on this topic: {subject}

Format EXACTLY like real HPSC questions:
- Start with "Consider the following statements about [topic]:"
- Give exactly 3 numbered statements
- End with "How many of the above statements are correct?"
- Options MUST always be exactly: A) None  B) Only one  C) Only two  D) All three

The statements must:
- Mix correct and incorrect facts (avoid making all 3 correct or all 3 wrong)
- Test precise factual knowledge — dates, distinctions, locations, conditions
- Include plausible incorrect statements that common misconceptions produce
- Match actual HPSC GS paper difficulty and style

CRITICAL: The "correct" field MUST be exactly one of: A, B, C, or D (uppercase, single character). Count the correct statements and return the matching option.

Return ONLY valid JSON, nothing else:
{{"question":"Consider the following statements about [specific aspect]:\\n1. [statement]\\n2. [statement]\\n3. [statement]\\n\\nHow many of the above statements are correct?","options":{{"A":"None","B":"Only one","C":"Only two","D":"All three"}},"correct":"B","explanation":"[2-3 sentences: which statements are correct and why, the core concept, and a memory tip]"}}"""

MCQ_AR_PROMPT = """Generate ONE HCS (Haryana Civil Services) Prelims exam style assertion-reason question strictly on this topic: {subject}

Format EXACTLY like real HPSC questions:
- Assertion (A): [a factual statement about the topic]
- Reason (R): [a statement that may or may not correctly explain the assertion]
- Options MUST always be exactly:
  A) Both A and R are true, and R correctly explains A
  B) Both A and R are true, but R does NOT correctly explain A
  C) A is false, but R is true
  D) A is true, but R is false

The assertion and reason must:
- Test analytical thinking, not just recall
- Use common exam misconceptions as traps (e.g. A is true but the given reason is wrong)
- Be grounded in actual HCS/UPSC-level facts
- Match actual HPSC GS paper style

CRITICAL: The "correct" field MUST be exactly one of: A, B, C, or D (uppercase, single character).

Return ONLY valid JSON, nothing else:
{{"question":"Assertion (A): [assertion text]\\nReason (R): [reason text]","options":{{"A":"Both A and R are true, and R correctly explains A","B":"Both A and R are true, but R does NOT correctly explain A","C":"A is false, but R is true","D":"A is true, but R is false"}},"correct":"C","explanation":"[2-3 sentences: what is true/false in A and R, the underlying concept, and why this combination is a classic exam trap]"}}"""

MCQ_MATCH_PROMPT = """Generate ONE HCS (Haryana Civil Services) Prelims exam style match-list question strictly on this topic: {subject}

Format EXACTLY like real HPSC questions:
- "Match List I with List II:"
- List I: 4 items labeled (a), (b), (c), (d)
- List II: 4 items labeled (i), (ii), (iii), (iv)
- "Select the correct answer using the codes below:"
- Options MUST use letter-number pair format

Match pairs must:
- Cover named entities (rulers→capitals, acts→years, rivers→states, scientists→discoveries)
- Have exactly one correct complete matching
- Use plausible wrong pairings as distractors
- Match actual HPSC GS paper difficulty

CRITICAL: The "correct" field MUST be exactly one of: A, B, C, or D (uppercase, single character). Verify the matches are correct before assigning.

Return ONLY valid JSON, nothing else:
{{"question":"Match List I with List II:\\n\\nList I\\n(a) [item1]\\n(b) [item2]\\n(c) [item3]\\n(d) [item4]\\n\\nList II\\n(i) [match1]\\n(ii) [match2]\\n(iii) [match3]\\n(iv) [match4]\\n\\nSelect the correct answer using the codes below:","options":{{"A":"a-i, b-ii, c-iii, d-iv","B":"a-ii, b-i, c-iv, d-iii","C":"a-iii, b-iv, c-i, d-ii","D":"a-iv, b-iii, c-ii, d-i"}},"correct":"B","explanation":"[2-3 sentences: the correct matches and why, plus one fact that helps remember the pairing]"}}"""

MCQ_COMPARISON_PROMPT = """Generate ONE HCS (Haryana Civil Services) Prelims exam style MCQ strictly on this topic: {subject}

The question MUST be comparison-style — the student previously confused two similar options on this topic.
- Compare two entities (leaders, acts, rivers, events, districts, schemes) on a specific attribute
- Format: "Which of the following correctly distinguishes [X] from [Y]?" or "Which statement correctly compares..."
- Options should differ in which entity has which attribute — classic confusion trap
- Match actual HPSC GS paper difficulty

CRITICAL: The "correct" field MUST be exactly one of: A, B, C, or D (uppercase, single character).

Return ONLY valid JSON, nothing else:
{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"2-3 sentences: the exact distinction, why the other options are wrong, memory tip for the comparison"}}"""

MOCK_TEST_PROMPT = """Generate exactly {n} HCS (Haryana Civil Services) Prelims style MCQs {topic_constraint}.

Each question must:
- Match actual HPSC exam style and test conceptual understanding
- Use ONLY text-based data (NO charts, pie charts, bar graphs, diagrams, or images)
- For Data Interpretation: embed table/numbers DIRECTLY in the question text

Return ONLY a valid JSON array, nothing else:
[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"one clear sentence","topic":"topic name"}}]"""

STUDY_OVERVIEW_PROMPT = """You are Yudhister, a professor with 20+ years of experience teaching HCS (Haryana Civil Services) exam aspirants.

A student wants to study: "{topic}"

Write a study session intro that covers:
1. What this topic is and its 2-3 key sub-areas (be specific — name them)
2. Why it matters for HCS Prelims (typical question count or exam importance)
3. 2-3 actual important facts or concepts a student must remember
4. End with: "Let's test your knowledge with 3 warm-up questions!"

Keep it under 150 words. Friendly and specific."""

PASSAGE_PROMPT = """You are Yudhister, a professor with 20+ years of HCS exam teaching experience. A complete beginner wants to learn about: "{topic}"

Write a clear, engaging educational passage (200-250 words) that:
- Assumes ZERO prior knowledge — explain every term used
- Covers 3-4 key facts/concepts a beginner must know
- Uses simple language (10th standard level)
- Has short paragraphs (2-3 sentences each)
- Ends with: "📌 Key takeaway: [one sentence summary]"

No bullet points. No headings. Just flowing, readable text."""

PASSAGE_MCQ_PROMPT = """Based ONLY on the passage below, generate exactly 3 MCQs that test reading comprehension.

Passage:
{passage}

Rules:
- Every question must be answerable ONLY from information in the passage
- Do NOT test general knowledge — only what the passage says
- One correct answer, three plausible wrong options
- Keep questions simple and direct

Return ONLY valid JSON array, nothing else:
[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"A","explanation":"The passage states that..."}}]"""


def _get_adaptive_topic(chat_id: str, subject: str) -> str:
    """Pick topic adaptively based on user_progress and difficulty_preference."""
    if subject and subject.lower() not in ["general", "general studies", "", "hcs"]:
        return subject

    all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS

    try:
        res = sb.table("user_progress").select("topic,correct,total")\
            .eq("chat_id", chat_id).execute()
        progress = {row["topic"]: row for row in (res.data or [])}
    except Exception:
        progress = {}

    # Read difficulty preference
    difficulty = "just_right"
    try:
        prof = sb.table("user_profiles").select("difficulty_preference")\
            .eq("chat_id", chat_id).limit(1).execute()
        if prof.data and prof.data[0].get("difficulty_preference"):
            difficulty = prof.data[0]["difficulty_preference"]
    except Exception:
        pass

    weighted = []
    for topic in all_topics:
        p = progress.get(topic)
        if p is None or p["total"] == 0:
            weight = 2  # untried — always some coverage
        else:
            pct = p["correct"] / p["total"]
            if difficulty == "hard":
                # Target 60-80% range — challenging but not crushing
                if 0.60 <= pct <= 0.80:
                    weight = 4
                elif pct > 0.80:
                    weight = 2  # mastered — less frequent in hard mode
                else:
                    weight = 1  # below 60% — too discouraging for hard mode
            elif difficulty == "easy":
                # Target 30-50% range — confidence building
                if 0.30 <= pct <= 0.50:
                    weight = 4
                elif pct < 0.30:
                    weight = 1  # crushing difficulty — avoid
                else:
                    weight = 2
            else:
                # Default: weak topics prioritized
                if pct < 0.6:
                    weight = 3
                elif pct > 0.8:
                    weight = 1
                else:
                    weight = 2
        weighted.extend([topic] * weight)

    return random.choice(weighted)


def _update_progress(
    chat_id: str,
    topic: str,
    is_correct: bool,
    question_text: str = "",
    options: dict = None,
    correct_answer: str = "",
    user_answer: str = "",
    explanation: str = "",
    source: str = "quiz",
):
    """Upsert user_progress for this topic."""
    try:
        res = sb.table("user_progress").select("correct,total")\
            .eq("chat_id", chat_id).eq("topic", topic).execute()
        if res.data:
            row = res.data[0]
            sb.table("user_progress").update({
                "correct": row["correct"] + (1 if is_correct else 0),
                "total": row["total"] + 1,
                "last_attempted": datetime.now(timezone.utc).isoformat(),
            }).eq("chat_id", chat_id).eq("topic", topic).execute()
        else:
            sb.table("user_progress").insert({
                "chat_id": chat_id, "topic": topic,
                "correct": 1 if is_correct else 0,
                "total": 1,
            }).execute()
    except Exception as e:
        print(f"[quiz] progress update failed: {e}")

    try:
        sb.table("user_answer_history").insert({
            "chat_id": chat_id,
            "topic": topic,
            "question_text": question_text,
            "options": options or {},
            "correct_answer": correct_answer,
            "user_answer": user_answer,
            "is_correct": is_correct,
            "explanation": explanation,
            "source": source,
        }).execute()
    except Exception as e:
        print(f"[quiz] answer history insert failed: {e}")


def _generate(subject: str, hint: str | None = None) -> dict:
    topic = subject
    # CSAT/aptitude topics need simple MCQ format, not GS recall formats
    csat_topic = any(
        kw in subject.lower()
        for kw in ["comprehension", "reasoning", "numeracy", "interpretation",
                   "decision", "aptitude", "blood relation", "coding", "arrangement",
                   "problem solving", "data"]
    )
    r = random.random()
    if hint == "comparison" and not csat_topic:
        prompt = MCQ_COMPARISON_PROMPT  # user confused last time — force comparison question
    elif csat_topic:
        prompt = MCQ_PROMPT          # simple MCQ for aptitude/reasoning
    elif r < 0.55:
        prompt = MCQ_STMT_PROMPT     # ~55% statement-correctness
    elif r < 0.90:
        prompt = MCQ_MATCH_PROMPT    # ~35% match-list (mirrors real GS paper)
    else:
        prompt = MCQ_AR_PROMPT       # ~10% assertion-reason
    raw = create_completion(
        messages=[{"role": "user", "content": prompt.format(subject=topic)}],
        max_tokens=400,
        temperature=0.85,
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())
    result["_topic"] = topic

    # Validate and fix correct answer if invalid
    correct = result.get("correct", "").upper().strip()
    options = result.get("options", {})

    if correct not in ["A", "B", "C", "D"]:
        # Invalid correct answer — pick first available option as fallback
        valid_options = [k for k in options.keys() if k in ["A", "B", "C", "D"]]
        if valid_options:
            result["correct"] = valid_options[0]
            print(f"[quiz] WARNING: Invalid correct answer '{correct}' for '{topic}' — using '{valid_options[0]}' instead")
        else:
            result["correct"] = "A"  # Last resort fallback
            print(f"[quiz] ERROR: No valid options found for '{topic}'")
    else:
        result["correct"] = correct

    # CRITICAL: Verify correct answer option actually exists
    if result["correct"] not in options:
        valid_options = [k for k in options.keys() if k in ["A", "B", "C", "D"]]
        if valid_options:
            result["correct"] = valid_options[0]
            print(f"[quiz] CRITICAL: Correct answer '{result['correct']}' not in options {list(options.keys())} — using '{valid_options[0]}'")

    return result


def _validate_question(q: dict, _attempt: int = 0, _max_attempts: int = 5) -> dict:
    """Recursively validate and fix questions. ALWAYS returns a valid question or raises error after max attempts."""

    # Check 1: correct field is A/B/C/D
    correct = q.get("correct", "").upper().strip()
    if correct not in ["A", "B", "C", "D"]:
        if _attempt >= _max_attempts:
            raise ValueError(f"[quiz] CRITICAL: Could not generate valid question after {_max_attempts} attempts. LLM returned invalid correct field: '{correct}'")
        print(f"[quiz] FAIL: Invalid correct field '{correct}' — regenerating (attempt {_attempt + 1}/{_max_attempts})")
        q = _generate(q.get("_topic", ""))
        return _validate_question(q, _attempt + 1, _max_attempts)

    # Check 2: correct answer exists in options
    options = q.get("options", {})
    if correct not in options:
        if _attempt >= _max_attempts:
            raise ValueError(f"[quiz] CRITICAL: Correct answer '{correct}' not in options {list(options.keys())} after {_max_attempts} attempts")
        print(f"[quiz] FAIL: Correct answer '{correct}' not in options {list(options.keys())} — regenerating (attempt {_attempt + 1}/{_max_attempts})")
        q = _generate(q.get("_topic", ""))
        return _validate_question(q, _attempt + 1, _max_attempts)

    # Check 3: all four options present
    valid_opts = [k for k in options.keys() if k in ["A", "B", "C", "D"]]
    if len(valid_opts) < 4:
        if _attempt >= _max_attempts:
            raise ValueError(f"[quiz] CRITICAL: Missing options. Found {len(valid_opts)}/4 after {_max_attempts} attempts")
        print(f"[quiz] FAIL: Missing options (found {len(valid_opts)}/4) — regenerating (attempt {_attempt + 1}/{_max_attempts})")
        q = _generate(q.get("_topic", ""))
        return _validate_question(q, _attempt + 1, _max_attempts)

    # Check 4: NO visual/chart elements required (WhatsApp doesn't support images)
    question_text = (q.get("question", "") + " " + " ".join(options.values())).lower()
    forbidden_words = ["pie chart", "bar chart", "bar graph", "line graph", "diagram", "figure",
                      "image", "visual", "graph", "chart", "see the", "refer to the figure",
                      "shown below", "given below", "following diagram", "following graph"]
    for forbidden in forbidden_words:
        if forbidden in question_text:
            if _attempt >= _max_attempts:
                raise ValueError(f"[quiz] CRITICAL: Question requires visual element '{forbidden}' after {_max_attempts} attempts. Cannot display in WhatsApp.")
            print(f"[quiz] FAIL: Question requires visual '{forbidden}' (WhatsApp text-only) — regenerating (attempt {_attempt + 1}/{_max_attempts})")
            q = _generate(q.get("_topic", ""))
            return _validate_question(q, _attempt + 1, _max_attempts)

    # Question passed ALL checks ✅
    if _attempt > 0:
        print(f"[quiz] ✅ Valid question generated on attempt {_attempt + 1}")
    return q


def _fmt(q: dict) -> str:
    topic = q.get("_topic", q.get("topic", ""))
    topic_line = f"_Topic: {topic}_\n\n" if topic else ""
    opts = "\n".join(f"*{k}.* {v}" for k, v in q["options"].items())
    return f"{topic_line}{q['question']}\n\n{opts}\n\n_Reply A, B, C, or D_"


def _mock_report(questions: list, answers: list, n: int, mode: str = "standard") -> str:
    correct_count = sum(1 for a in answers if a["correct"])
    pct = int(correct_count / n * 100)

    topic_stats: dict = {}
    wrong_qs = []
    for a in answers:
        t = a.get("topic", "General")
        if t not in topic_stats:
            topic_stats[t] = {"correct": 0, "total": 0}
        topic_stats[t]["total"] += 1
        if a["correct"]:
            topic_stats[t]["correct"] += 1
        else:
            idx = a["q"]
            if idx < len(questions):
                wrong_qs.append((idx + 1, questions[idx]))

    if pct >= 80:
        verdict = "Excellent work! 🔥 You're exam-ready on these topics."
    elif pct >= 60:
        verdict = "Good attempt! 💪 A bit more revision on the weak areas and you're there."
    elif pct >= 40:
        verdict = "Keep pushing! 📚 Focus on the topics below — they're costing you marks."
    else:
        verdict = "Don't be discouraged — every wrong answer shows you exactly what to study next. 💪"

    header = "*Rapid Fire Complete!* ⚡" if mode == "rapid_fire" else "*Mock Test Complete!* 🏁"
    report = f"{header}\n\nScore: *{correct_count}/{n}* ({pct}%)\n\n{verdict}\n\n"

    weak = [t for t, s in topic_stats.items() if s["total"] > 0 and s["correct"] / s["total"] < 0.6]
    if weak:
        report += f"*Topics to revise:* {', '.join(weak)}\n\n"

    # Show up to 4 wrong answers with their concept explanation
    if wrong_qs:
        report += "*Questions to review:*\n"
        for q_num, q in wrong_qs[:4]:
            short_q = q.get("question", "")[:80].split("\n")[0]
            explanation = q.get("explanation", "")
            correct_letter = q.get("correct", "")
            correct_text = q.get("options", {}).get(correct_letter, "")
            report += f"\n*Q{q_num}* {short_q}…\n✅ {correct_letter}: {correct_text}\n💡 {explanation}\n"

    return report


# ── Regular Quiz ────────────────────────────────────────────────────────────

def start_quiz(chat_id: str, exam: str, subject: str) -> tuple[str, dict]:
    topic = _get_adaptive_topic(chat_id, subject)
    try:
        q = _generate(topic)
        q = _validate_question(q)  # Ensure question is valid before sending
    except Exception as e:
        print(f"[quiz] ERROR generating valid question for {topic}: {e}")
        return "Sorry, I'm having trouble generating questions right now. Please try again in a moment!", None

    sb.table("quiz_sessions").upsert({
        "chat_id": chat_id, "exam": "HCS", "subject": q.get("_topic", topic),
        "question": q["question"], "options": q["options"],
        "correct_answer": q["correct"], "explanation": q["explanation"],
        "active": True, "score": 0, "total": 0,
    }, on_conflict="chat_id").execute()
    return (
        "Alright, HCS quiz time! 🎯",
        {"question": q["question"], "options": q["options"], "topic": q.get("_topic", topic)},
    )


def check_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    res = sb.table("quiz_sessions").select("*")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    if not res.data:
        return "No active quiz. Send *quiz me* to start one!", None

    s = res.data[0]
    letter = _extract_letter(user_answer)
    correct = s["correct_answer"]
    is_right = letter == correct
    new_score = s["score"] + (1 if is_right else 0)
    new_total = s["total"] + 1

    # Log answer for debugging mismatches
    print(f"[quiz] {chat_id}: Q='{s.get('subject', 'unknown')}' User='{letter}' Correct='{correct}' Match={is_right}")

    _update_progress(
        chat_id,
        s["subject"],
        is_right,
        question_text=s["question"],
        options=s["options"],
        correct_answer=s["correct_answer"],
        user_answer=letter,
        explanation=s.get("explanation", ""),
        source="quiz",
    )

    if is_right:
        result = f"*Correct!* 🎉\n\n{s['explanation']}"
        result += f"\n\n_Score: {new_score}/{new_total}_"
        result += "\n\n*Was this:*\n1. Guess\n2. Logic\n3. Memory\n\n_(or skip to continue)_"
    else:
        result = (
            f"*Not quite — the answer is {correct}.* {s['options'][correct]}\n\n"
            f"💡 *Concept:* {s['explanation']}\n\n"
            f"_Score: {new_score}/{new_total}_"
        )
        result += "\n\n*Why did you get this wrong?*\n1. Didn't know\n2. Confused options\n3. Silly mistake\n\n_(or skip to continue)_"

    # Check if last error was "confusion" — use comparison question next time
    next_hint = None
    try:
        last_err = sb.table("user_answer_history").select("error_type")\
            .eq("chat_id", chat_id)\
            .order("attempted_at", desc=True).limit(1).execute()
        if last_err.data and last_err.data[0].get("error_type") == "confusion":
            next_hint = "comparison"
    except Exception:
        pass

    next_topic = _get_adaptive_topic(chat_id, "")
    try:
        next_q = _generate(next_topic, hint=next_hint)
        next_q = _validate_question(next_q)  # Ensure next question is valid before storing
    except Exception as e:
        print(f"[quiz] ERROR generating next question for {next_topic}: {e}")
        # Fallback: deactivate quiz and return error
        sb.table("quiz_sessions").update({"active": False}).eq("chat_id", chat_id).execute()
        result_msg = (
            f"{'*Correct!* 🎉' if is_right else f'*Not quite — the answer is {correct}.*'}\n\n"
            f"{s['explanation']}\n\n"
            f"_Score: {new_score}/{new_total}_\n\n"
            "⚠️ I'm having trouble generating the next question. "
            "Please try *quiz me* again in a moment!"
        )
        _update_progress(
            chat_id, s["subject"], is_right,
            question_text=s["question"], options=s["options"],
            correct_answer=correct, user_answer=letter,
            explanation=s.get("explanation", ""), source="quiz"
        )
        return result_msg, None

    # Tag session: CONF if correct, ERR if wrong — next question already saved
    base_exam = (s.get("exam") or "HCS").split(":")[0]
    new_tag = f"{base_exam}:CONF" if is_right else f"{base_exam}:ERR"
    sb.table("quiz_sessions").update({
        "question": next_q["question"], "options": next_q["options"],
        "correct_answer": next_q["correct"], "explanation": next_q["explanation"],
        "subject": next_q.get("_topic", next_topic),
        "score": new_score, "total": new_total,
        "exam": new_tag,
    }).eq("chat_id", chat_id).execute()

    # Return None for q_data — next question sent only after confidence reply
    return result, None


def stop_quiz(chat_id: str) -> tuple[str, None]:
    res = sb.table("quiz_sessions").select("score,total")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    sb.table("quiz_sessions").update({"active": False}).eq("chat_id", chat_id).execute()
    if res.data:
        d = res.data[0]
        pct = int(d["score"] / d["total"] * 100) if d["total"] else 0
        msg = "Amazing! 🔥" if pct >= 80 else "Good effort! Keep going 💪" if pct >= 50 else "Keep practicing, you'll get there! 📚"
        return f"Quiz done!\n\nFinal score: *{d['score']}/{d['total']}* ({pct}%)\n\n{msg}", None
    return "Quiz ended.", None


def has_active_quiz(chat_id: str) -> bool:
    res = sb.table("quiz_sessions").select("id")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    return bool(res.data)


def _is_conf_waiting(chat_id: str) -> bool:
    """True if quiz session is in CONF or ERR state (waiting for follow-up reply)."""
    try:
        res = sb.table("quiz_sessions").select("exam")\
            .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
        exam = (res.data[0].get("exam") or "") if res.data else ""
        return ":CONF" in exam or ":ERR" in exam
    except Exception:
        return False


def record_confidence(chat_id: str, reply: str) -> tuple[str, dict | None]:
    """Store confidence/error_type from user reply, restore session state, return next question."""
    try:
        res = sb.table("quiz_sessions").select("*")\
            .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
        if not res.data:
            return "No active quiz.", None
        s = res.data[0]
        exam = s.get("exam") or ""

        # Map reply to label
        if ":CONF" in exam:
            label_map = {"1": "guess", "2": "logic", "3": "memory"}
            field = "confidence"
        else:
            label_map = {"1": "no_knowledge", "2": "confusion", "3": "silly"}
            field = "error_type"

        label = label_map.get(reply)  # None if "skip"

        # Update most recent user_answer_history row
        if label:
            try:
                hist_res = sb.table("user_answer_history").select("id")\
                    .eq("chat_id", chat_id)\
                    .order("attempted_at", desc=True).limit(1).execute()
                if hist_res.data:
                    sb.table("user_answer_history").update({field: label})\
                        .eq("id", hist_res.data[0]["id"]).execute()
            except Exception as e:
                print(f"[quiz] record_confidence update failed: {e}")

        # Restore base exam tag
        base_exam = exam.split(":")[0]
        sb.table("quiz_sessions").update({"exam": base_exam})\
            .eq("chat_id", chat_id).execute()

        # Return next question (already saved in session by check_answer)
        q_data = {
            "question": s["question"],
            "options": s["options"],
            "topic": s.get("subject", ""),
        }
        intro = "📚 Next one:"
        return intro, q_data

    except Exception as e:
        print(f"[quiz] record_confidence failed: {e}")
        return "Let's continue!", None


def start_batch_quiz(chat_id: str, n: int = 5, topic: str = None) -> tuple[str, None]:
    """Generate n questions, send them all as a numbered list in one message.
    Answers are processed one by one via check_mock_answer (reuses mock_tests table)."""
    if topic:
        topic_constraint = f"strictly on the topic: {topic}"
    else:
        all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS
        topics_str = ", ".join(all_topics)
        topic_constraint = f"across different topics from this list: {topics_str}"
    raw = create_completion(
        messages=[{"role": "user", "content": MOCK_TEST_PROMPT.format(n=n, topic_constraint=topic_constraint)}],
        max_tokens=n * 220,
        temperature=0.85,
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        questions = json.loads(raw.strip())
    except Exception as e:
        print(f"[quiz] start_batch_quiz json parse failed: {e}")
        return "Sorry, I had trouble generating that quiz. Please try again!", None

    # Deactivate any existing mock test
    sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
    sb.table("mock_tests").insert({
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "current_idx": 0,
        "active": True,
    }).execute()

    # Format all questions in one message
    lines = [f"*Quiz Round — {n} Questions* 📋\n"]
    for i, q in enumerate(questions, 1):
        topic = q.get("topic", "")
        topic_line = f"_{topic}_\n" if topic else ""
        opts = "\n".join(f"*{k}.* {v}" for k, v in q["options"].items())
        lines.append(f"*Q{i}.* {topic_line}{q['question']}\n{opts}")
    lines.append("\n_Answer Q1 first — reply A, B, C, or D_")

    return "\n\n".join(lines), None


# ── Mock Test ────────────────────────────────────────────────────────────────

def start_mock_test(chat_id: str, n: int = 10, topic: str = None) -> tuple[str, dict]:
    if topic:
        topic_constraint = f"strictly on the topic: {topic}"
    else:
        all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS
        topics_str = ", ".join(all_topics)
        topic_constraint = f"across different topics from this list: {topics_str}"

    questions = []
    try:
        raw = create_completion(
            messages=[{"role": "user", "content": MOCK_TEST_PROMPT.format(n=n, topic_constraint=topic_constraint)}],
            max_tokens=n * 220,
            temperature=0.85,
        )
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        questions = json.loads(raw.strip())
    except Exception as e:
        print(f"[quiz] start_mock_test batch failed: {e} — falling back to single-question generation")

    # Fallback: generate questions one by one if batch failed or returned too few
    if len(questions) < n:
        all_topics = HCS_GS_TOPICS + HCS_CSAT_TOPICS
        while len(questions) < n:
            try:
                t = random.choice(all_topics)
                q = _generate(t)
                q["topic"] = q.get("_topic", t)
                questions.append(q)
            except Exception:
                break

    if not questions:
        return "Sorry, couldn't generate the mock test right now. Please try again in a moment!", None

    questions = questions[:n]
    sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
    sb.table("mock_tests").insert({
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "current_idx": 0,
        "active": True,
    }).execute()

    q = questions[0]
    return (
        f"*Mock Test — {n} Questions* 📝\n\nQuestion 1/{n}:",
        {"question": q["question"], "options": q["options"], "topic": q.get("topic", "")},
    )


def check_mock_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    res = sb.table("mock_tests").select("*")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    if not res.data:
        return "No active mock test. Send *mock test* to start one!", None

    test = res.data[0]
    questions = test["questions"]
    answers = list(test["answers"])
    idx = test["current_idx"]
    n = len(questions)

    q = questions[idx]
    letter = _extract_letter(user_answer)
    correct = q["correct"]
    is_right = letter == correct

    topic = q.get("topic", "General")
    answers.append({"q": idx, "answer": letter, "correct": is_right, "topic": topic})
    _update_progress(
        chat_id,
        topic,
        is_right,
        question_text=q.get("question", ""),
        options=q.get("options", {}),
        correct_answer=correct,
        user_answer=letter,
        explanation=q.get("explanation", ""),
        source="mock",
    )

    test_mode = test.get("mode", "standard")
    if test_mode == "rapid_fire":
        feedback = "✅" if is_right else f"❌ _(correct: {correct}. {q['options'][correct]})_"
    elif is_right:
        feedback = f"*Correct!* ✅\n\n{q['explanation']}"
    else:
        feedback = (
            f"*Not quite — answer is {correct}.* {q['options'][correct]}\n\n"
            f"💡 *Concept:* {q['explanation']}"
        )

    next_idx = idx + 1

    if next_idx >= n:
        sb.table("mock_tests").update({
            "answers": answers, "active": False, "current_idx": next_idx
        }).eq("id", test["id"]).execute()
        return feedback + "\n\n" + _mock_report(questions, answers, n, mode=test_mode), None
    else:
        sb.table("mock_tests").update({
            "answers": answers, "current_idx": next_idx
        }).eq("id", test["id"]).execute()
        next_q = questions[next_idx]
        return (
            feedback + f"\n\nQuestion {next_idx + 1}/{n}:",
            {"question": next_q["question"], "options": next_q["options"], "topic": next_q.get("topic", "")},
        )


def has_active_mock_test(chat_id: str) -> bool:
    res = sb.table("mock_tests").select("id")\
        .eq("chat_id", chat_id).eq("active", True).limit(1).execute()
    return bool(res.data)


def start_rapid_fire(chat_id: str) -> tuple[str, dict | None]:
    """5-question rapid fire: minimal feedback between questions, full report at end."""
    text, q_data = start_mock_test(chat_id, n=5, topic=None)
    # Tag the mock test as rapid_fire to suppress mid-question explanations
    try:
        sb.table("mock_tests").update({"mode": "rapid_fire"})\
            .eq("chat_id", chat_id).eq("active", True).execute()
    except Exception as e:
        print(f"[quiz] start_rapid_fire mode tag failed: {e}")
    header = "*Rapid Fire* ⚡\n\n5 questions. No stopping. Let's go!\n\nQ1:"
    return header, q_data


def _scale_blueprint(n: int) -> list:
    """Return a list of n topic strings following HPSC paper blueprint proportions."""
    total_weight = sum(HPSC_GS_BLUEPRINT.values())
    result = []
    remainders = []
    for topic, weight in HPSC_GS_BLUEPRINT.items():
        exact = n * weight / total_weight
        floor_count = int(exact)
        result.extend([topic] * floor_count)
        remainders.append((exact - floor_count, topic))
    # Fill remaining slots by largest fractional remainder
    shortage = n - len(result)
    remainders.sort(key=lambda x: -x[0])
    for i in range(shortage):
        result.append(remainders[i][1])
    return result


def start_hpsc_mock(chat_id: str, n: int = 25) -> tuple[str, dict]:
    """Start a blueprint-weighted HPSC mock test.
    Generates n questions following the real HPSC paper topic distribution."""
    topic_list = _scale_blueprint(n)

    # Build topic constraint string for the LLM showing required distribution
    from collections import Counter
    counts = Counter(topic_list)
    parts = [f"{count}q on '{topic}'" for topic, count in counts.most_common()]
    topic_constraint = "with EXACTLY this topic distribution: " + ", ".join(parts)

    # Generate in batches of 10 for reliability
    batch_size = 10
    all_questions = []
    i = 0
    while i < len(topic_list):
        batch_topics = topic_list[i:i+batch_size]
        batch_counts = Counter(batch_topics)
        batch_parts = [f"{c}q on '{t}'" for t, c in batch_counts.most_common()]
        batch_constraint = "with EXACTLY this topic distribution: " + ", ".join(batch_parts)
        batch_n = len(batch_topics)
        try:
            raw = create_completion(
                messages=[{"role": "user", "content": MOCK_TEST_PROMPT.format(
                    n=batch_n, topic_constraint=batch_constraint
                )}],
                max_tokens=batch_n * 220,
                temperature=0.85,
            )
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            batch_questions = json.loads(raw.strip())
            all_questions.extend(batch_questions)
        except Exception as e:
            print(f"[quiz] hpsc_mock batch {i}-{i+batch_size} failed: {e} — falling back to _generate()")
            for t in batch_topics:
                try:
                    q = _generate(t)
                    q["topic"] = q.get("_topic", t)
                    all_questions.append(q)
                except Exception:
                    pass
        i += batch_size

    if not all_questions:
        return "Sorry, couldn't generate the mock test right now. Please try again in a moment!", None

    questions = all_questions[:n]  # trim to exactly n in case of LLM overcounting

    sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
    sb.table("mock_tests").insert({
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "current_idx": 0,
        "active": True,
    }).execute()

    q = questions[0]
    return (
        f"*HPSC Blueprint Mock — {n} Questions* 📝\n_Topics match real exam distribution_\n\nQuestion 1/{n}:",
        {"question": q["question"], "options": q["options"], "topic": q.get("topic", "")},
    )


def has_active_hpsc_mock(chat_id: str) -> bool:
    # Reuses the same mock_tests table — just delegates to has_active_mock_test
    return has_active_mock_test(chat_id)


def start_haryana_special(chat_id: str, n: int = 10) -> tuple[str, dict]:
    """Start a Haryana-only quiz covering folk culture, heritage, 1857 leaders, geography etc.
    These are the differentiator topics that decide exam cutoffs."""
    # Build topic list cycling through HARYANA_SPECIAL_TOPICS
    topic_list = [HARYANA_SPECIAL_TOPICS[i % len(HARYANA_SPECIAL_TOPICS)] for i in range(n)]
    random.shuffle(topic_list)

    topic_constraint = f"strictly on Haryana-specific topics — rotate across these sub-topics: {', '.join(HARYANA_SPECIAL_TOPICS)}"
    raw = create_completion(
        messages=[{"role": "user", "content": MOCK_TEST_PROMPT.format(
            n=n, topic_constraint=topic_constraint
        )}],
        max_tokens=n * 220,
        temperature=0.85,
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    questions = json.loads(raw.strip())

    sb.table("mock_tests").update({"active": False}).eq("chat_id", chat_id).execute()
    sb.table("mock_tests").insert({
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "current_idx": 0,
        "active": True,
    }).execute()

    q = questions[0]
    return (
        f"*Haryana Special Drill — {n} Questions* 🏛️\n_Folk culture, heritage sites, 1857 leaders, geography — the cutoff deciders_\n\nQuestion 1/{n}:",
        {"question": q["question"], "options": q["options"], "topic": q.get("topic", "Haryana")},
    )


# ── Study Session ────────────────────────────────────────────────────────────

def start_study_session(chat_id: str, topic: str) -> str:
    from bot.memory import set_study_session, set_current_topic
    overview = create_completion(
        messages=[{"role": "user", "content": STUDY_OVERVIEW_PROMPT.format(topic=topic)}],
        max_tokens=300,
        temperature=0.7,
    )

    set_current_topic(chat_id, topic)
    set_study_session(chat_id, {"topic": topic, "q_count": 0, "correct": 0, "max_q": 3})

    try:
        first_q = _generate(topic)
        first_q = _validate_question(first_q)  # Ensure question is valid before sending
    except Exception as e:
        print(f"[quiz] ERROR generating study question for {topic}: {e}")
        return f"Sorry, I'm having trouble generating study questions on {topic}. Please try again!", None

    session_q = {"question": first_q["question"], "options": first_q["options"],
                 "correct": first_q["correct"], "explanation": first_q["explanation"],
                 "topic": topic}
    # Store pending question in study_session
    from bot.memory import get_study_session
    sess = get_study_session(chat_id)
    sess["pending_q"] = session_q
    set_study_session(chat_id, sess)

    return (
        f"{overview}\n\n*Question 1/3:*",
        {"question": first_q["question"], "options": first_q["options"], "topic": topic},
    )


def check_study_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    from bot.memory import get_study_session, set_study_session, set_current_topic
    sess = get_study_session(chat_id)
    if not sess or "pending_q" not in sess:
        return "No active study session. Say *let's study [topic]* to start one!", None

    q = sess["pending_q"]
    letter = _extract_letter(user_answer)
    correct = q["correct"]
    is_right = letter == correct

    _update_progress(
        chat_id,
        q["topic"],
        is_right,
        question_text=q.get("question", ""),
        options=q.get("options", {}),
        correct_answer=q.get("correct", ""),
        user_answer=letter,
        explanation=q.get("explanation", ""),
        source="study",
    )

    if is_right:
        feedback = f"*Correct!* 🎉\n{q['explanation']}"
    else:
        feedback = f"*Not quite.* Answer: *{correct}*: {q['options'][correct]}\n{q['explanation']}"

    sess["q_count"] += 1
    if is_right:
        sess["correct"] += 1
    q_count = sess["q_count"]
    max_q = sess["max_q"]
    topic = sess["topic"]

    if q_count >= max_q:
        correct_count = sess["correct"]
        pct = int(correct_count / max_q * 100)
        set_study_session(chat_id, None)
        set_current_topic(chat_id, None)
        msg = "Great job! 🔥" if pct >= 80 else "Good effort! 💪" if pct >= 50 else "More practice needed! 📚"
        summary = f"\n\n*Session Summary — {topic}*\nScore: *{correct_count}/{max_q}* ({pct}%) {msg}"
        return feedback + summary, None
    else:
        try:
            next_q_data = _generate(topic)
            next_q_data = _validate_question(next_q_data)  # Ensure question is valid before storing
        except Exception as e:
            print(f"[quiz] ERROR generating next study question for {topic}: {e}")
            set_study_session(chat_id, None)
            set_current_topic(chat_id, None)
            return (
                feedback + "\n\n⚠️ I had trouble generating the next question. "
                "The session has ended. Say *study [topic]* to start a new one!",
                None
            )
        sess["pending_q"] = {
            "question": next_q_data["question"], "options": next_q_data["options"],
            "correct": next_q_data["correct"], "explanation": next_q_data["explanation"],
            "topic": topic,
        }
        set_study_session(chat_id, sess)
        return (
            feedback + f"\n\n*Question {q_count + 1}/{max_q}:*",
            {"question": next_q_data["question"], "options": next_q_data["options"], "topic": topic},
        )


def has_active_study_session(chat_id: str) -> bool:
    from bot.memory import get_study_session
    sess = get_study_session(chat_id)
    return bool(sess and "pending_q" in sess)


# ── Passage Quiz ─────────────────────────────────────────────────────────────

def start_passage_quiz(chat_id: str, topic: str) -> tuple[str, dict]:
    """Generate a beginner passage on the topic, then 3 MCQs from it. Returns (passage_text, first_q_dict)."""
    from bot.memory import set_study_session, set_current_topic

    # Step 1: generate passage
    passage = create_completion(
        messages=[{"role": "user", "content": PASSAGE_PROMPT.format(topic=topic)}],
        max_tokens=400,
        temperature=0.7,
    )

    # Step 2: generate 3 MCQs from the passage
    raw = create_completion(
        messages=[{"role": "user", "content": PASSAGE_MCQ_PROMPT.format(passage=passage)}],
        max_tokens=600,
        temperature=0.6,
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    questions = json.loads(raw.strip())

    # Step 3: store session
    set_current_topic(chat_id, topic)
    set_study_session(chat_id, {
        "mode": "passage",
        "topic": topic,
        "passage_text": passage,
        "questions": questions,
        "q_idx": 0,
        "correct": 0,
        "max_q": len(questions),
    })

    first_q = questions[0]
    return (
        f"📖 *Let's learn {topic} from scratch!*\n\n{passage}\n\n*Now let's see what you understood 👇*\n\n*Question 1/{len(questions)}:*",
        {"question": first_q["question"], "options": first_q["options"], "topic": topic},
    )


def check_passage_answer(chat_id: str, user_answer: str) -> tuple[str, dict | None]:
    """Check answer for passage quiz. Questions come from pre-generated list, not re-generated."""
    from bot.memory import get_study_session, set_study_session, set_current_topic

    sess = get_study_session(chat_id)
    if not sess or sess.get("mode") != "passage":
        return "No active passage quiz. Say *teach me [topic] from scratch* to start!", None

    questions = sess["questions"]
    q_idx = sess["q_idx"]
    q = questions[q_idx]

    letter = _extract_letter(user_answer)
    correct = q["correct"]
    is_right = letter == correct

    _update_progress(
        chat_id, sess["topic"], is_right,
        question_text=q["question"], options=q["options"],
        correct_answer=correct, user_answer=letter,
        explanation=q.get("explanation", ""), source="passage_quiz",
    )

    if is_right:
        feedback = f"*Correct!* 🎉\n_{q.get('explanation', '')}_"
    else:
        feedback = f"*Not quite.* Answer: *{correct}* — {q['options'][correct]}\n_{q.get('explanation', '')}_"

    sess["q_idx"] += 1
    if is_right:
        sess["correct"] += 1
    new_idx = sess["q_idx"]
    max_q = sess["max_q"]
    topic = sess["topic"]

    if new_idx >= max_q:
        correct_count = sess["correct"]
        pct = int(correct_count / max_q * 100)
        set_study_session(chat_id, None)
        set_current_topic(chat_id, None)
        msg = "You're getting it! 🔥" if pct >= 80 else "Good start! 💪" if pct >= 50 else "Re-read the passage and try again! 📚"
        return (
            f"{feedback}\n\n*Passage Quiz Done!*\nScore: *{correct_count}/{max_q}* ({pct}%) {msg}\n\n"
            f"_Say *teach me {topic} from scratch* to do another round, or *quiz me on {topic}* for harder questions._",
            None,
        )
    else:
        set_study_session(chat_id, sess)
        next_q = questions[new_idx]
        return (
            feedback + f"\n\n*Question {new_idx + 1}/{max_q}:*",
            {"question": next_q["question"], "options": next_q["options"], "topic": topic},
        )


def has_active_passage_quiz(chat_id: str) -> bool:
    from bot.memory import get_study_session
    sess = get_study_session(chat_id)
    return bool(sess and sess.get("mode") == "passage")


def verify_answer_mismatch(chat_id: str, reported_correct: str) -> str:
    """Log answer mismatch report for later review. Returns confirmation."""
    try:
        res = sb.table("user_answer_history").select("*")\
            .eq("chat_id", chat_id)\
            .order("attempted_at", desc=True).limit(1).execute()
        if res.data:
            record = res.data[0]
            sb.table("user_answer_history").update({
                "reported_correct": reported_correct,
                "mismatch_flag": True
            }).eq("id", record["id"]).execute()
            return (
                f"✅ Mismatch logged for review:\n"
                f"*Question:* {record['question_text'][:100]}…\n"
                f"*Bot said:* {record['correct_answer']}\n"
                f"*You say:* {reported_correct}\n\n"
                f"Thanks for catching that! We're tracking this to improve the system."
            )
    except Exception as e:
        print(f"[quiz] verify_answer_mismatch failed: {e}")
    return "Could not log mismatch. Please try again!"
