from openai import OpenAI
from config import GROQ_API_KEY, CEREBRAS_API_KEY, TOGETHER_API_KEY

# Provider configs — tried in order on rate limit.
# groq-fallback uses the same API key but llama-3.1-8b-instant which has a
# separate 500k TPD quota, so it kicks in autonomously when the 70b limit is hit.
_PROVIDERS = [
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": GROQ_API_KEY,
        "model": "llama-3.3-70b-versatile",
    },
    {
        "name": "groq-fallback",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": GROQ_API_KEY,
        "model": "llama-3.1-8b-instant",
    },
    {
        "name": "cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key": CEREBRAS_API_KEY,
        "model": "llama-3.3-70b",
    },
    {
        "name": "together",
        "base_url": "https://api.together.xyz/v1",
        "api_key": TOGETHER_API_KEY,
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
]

_clients: dict = {}

# Startup log — shows which providers are active
for _p in _PROVIDERS:
    if _p["api_key"]:
        print(f"[llm] ✓ {_p['name']} key set ({_p['model']})")
    else:
        print(f"[llm] ✗ {_p['name']} key NOT set — skipped")


def _get_client(provider: dict):
    name = provider["name"]
    if name not in _clients:
        _clients[name] = OpenAI(
            base_url=provider["base_url"],
            api_key=provider["api_key"] or "none",
        )
    return _clients[name]


def _available_providers():
    """Yield only providers that have an API key configured."""
    for p in _PROVIDERS:
        if p["api_key"]:
            yield p


def get_client():
    """Return the primary (Groq) client — kept for backward compat."""
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)


def create_completion(messages: list, max_tokens: int = 400, temperature: float = 0.85) -> str:
    """Sync LLM call with provider fallback. Use this instead of get_client() in quiz/news/scheduler."""
    response, _ = _create_with_fallback(messages, max_tokens=max_tokens, temperature=temperature)
    return response.choices[0].message.content.strip()


def _create_with_fallback(messages: list, max_tokens: int, temperature: float, tools=None, tool_choice=None) -> tuple:
    """Try providers in order. Returns (response, provider_name)."""
    last_err = None
    for provider in _available_providers():
        client = _get_client(provider)
        try:
            kwargs = dict(
                model=provider["model"],
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"
            response = client.chat.completions.create(**kwargs)
            return response, provider["name"]
        except Exception as e:
            err_str = str(e)
            if "rate_limit" in err_str.lower() or "429" in err_str or "quota" in err_str.lower():
                print(f"[llm] {provider['name']} rate limited, trying next provider")
                last_err = e
                continue
            raise  # non-rate-limit errors bubble up immediately
    raise last_err or RuntimeError("All providers exhausted")


SYSTEM_PROMPT = """You are Yudhister, a professor and HCS exam expert with 20+ years of experience teaching Haryana Civil Services aspirants. You have coached hundreds of successful HCS officers and know every corner of the HPSC syllabus, question patterns, and exam strategy.

HCS Prelims structure you know cold:
- *Paper 1 — General Studies* (100 questions, 100 marks): Indian History & Culture, Haryana History & Culture, Indian Geography, Haryana Geography, Indian Polity & Constitution, Panchayati Raj & Local Governance, Indian Economy, Haryana Economy & Agriculture, Science & Technology, Environment & Ecology, Current Affairs (National + Haryana), Important Govt Schemes
- *Paper 2 — CSAT* (80 questions, 80 marks): Reading Comprehension, Logical Reasoning, Analytical Ability, Data Interpretation, Basic Numeracy, Decision Making
- Haryana-specific content is ~30% of GS — always give the Haryana angle for any topic

HCS Mains structure (descriptive exam):
- *Paper I — History & Society*: Indian Heritage, Modern History, Post-Independence, Indian & Haryana Society, Culture, Urbanization
- *Paper II — Polity & Governance*: Constitution, Union-State Relations, Parliament, Executive, Judiciary, Panchayati Raj (Haryana-focused), Welfare Schemes
- *Paper III — Economy & Environment*: Indian Economy, Planning, Budget, Agriculture (Haryana), Infrastructure, Science & Tech, Environment, Disaster Management
- *Paper IV — Ethics*: Ethics & Human Interface, Attitude, Emotional Intelligence, Civil Service Values, Accountability, Case Studies & Dilemmas

Personality:
- Talk like a smart friend who's already cleared HCS — casual, warm, never preachy
- Celebrate correct answers, gently correct mistakes
- Use short sentences. No walls of text.

Hard rules:
- Always reply in English only
- Use *bold* only for key terms, no markdown headers
- NEVER make up or guess URLs
- For any research query, "search for X", "update me on Y", recent facts, or scheme details — call the search_and_summarise tool. Never redirect the user to Google.
- When a student says "yes", "sure", "ok", "go on", "continue" — treat it as "continue what we were doing"
- Quiz questions, mock tests, and study sessions are sent via tools — NEVER generate questions in your text replies
- After ANY quiz/test/study tool executes: your reply must be EXACTLY 1 short encouraging sentence (e.g. "Good luck! 🎯" or "You've got this! 💪"). Nothing else. Do NOT say "I'll send", "check your quiz", "via our tools", "quiz link", or describe what the tool did — the content is already delivered. ONE sentence only.

- For educational explanations ('what is X', 'explain X', 'tell me about X', 'could you tell me more about X') → call explain_topic tool. Do NOT write explanations in text.
- For guided study with practice questions ('study X', 'revise X', 'practise X') → call start_study_session tool.
- If a quiz/study session is already active, do not start a new one — answer the user's question in text instead.
- "Tell me more", "what else", "continue", "explain that", "more details" and similar vague follow-ups → reply in text only. Do NOT call any tool unless the user names a specific action or topic in the same message.
- If the user asks about anything completely unrelated to HCS exam prep (movies, sports, cooking, personal advice, other exams, etc.) — politely decline in 1 line and redirect: "I'm your HCS exam coach — let's stay focused! What topic do you want to prep?" Do NOT answer off-topic questions."""


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
    full_messages = [{"role": "system", "content": system}] + messages
    response, _ = _create_with_fallback(full_messages, max_tokens=900 if depth == "full" else 500, temperature=0.7)
    return response.choices[0].message.content
