import json
import re
import random
from groq import BadRequestError
from bot.llm import get_client, SYSTEM_PROMPT

_QUIZ_TOOLS = {"start_quiz", "start_mock_test", "start_study_session", "start_passage_quiz"}
_ENCOURAGEMENTS = [
    "Good luck! 🎯",
    "You've got this! 💪",
    "Let's go! 🔥",
    "Give it your best! ⭐",
    "All the best! 🙌",
]
# These tools return already-formatted output — no LLM round-trip needed
_DIRECT_RETURN_TOOLS = {
    "get_current_affairs",
    "get_user_progress",
    "get_wrong_answers",
    "cancel_scheduled_updates",
    "set_exam_date",
    "schedule_updates",
}


def _parse_text_tool_calls(content: str) -> list:
    """Parse Llama text-format tool calls: <function=name{...}</function>"""
    results = []
    for m in re.finditer(r'<function=(\w+)(\{[^<>]*\})?', content):
        name = m.group(1)
        args_str = m.group(2) or '{}'
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}
        results.append((name, args))
    return results


def _strip_text_tool_calls(text: str) -> str:
    """Remove any leftover <function=...> syntax from LLM output."""
    return re.sub(r'<function=\w+[^>]*>.*?(?:</function>|$)', '', text, flags=re.DOTALL).strip()

MAX_ROUNDS = 5

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "start_quiz",
            "description": "Start a practice MCQ quiz. Use ONLY when user explicitly requests quiz questions e.g. 'quiz me', 'give me questions', 'practice questions', 'test me on Polity'. Do NOT call for vague messages like 'I want to prepare', 'help me study', 'want to start' — answer those conversationally by asking what they need.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "HCS topic e.g. 'Polity', 'Haryana GK'. Omit if not specified."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_mock_test",
            "description": "Start a full timed mock test. Use ONLY when user explicitly says 'mock test', 'full test', 'give me X questions mock'. Do NOT call for 'I want to prepare' or general study requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_count": {"type": "integer", "description": "Number of questions (1-50, default 10)"},
                    "topic": {"type": "string", "description": "Optional. Restrict all questions to this HCS topic e.g. 'Polity', 'Haryana History', 'Economy'. Omit for mixed topics."}
                },
                "required": ["question_count"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_study_session",
            "description": "Start a guided study session (overview + 3 questions) on a topic. Call this when a study topic is clear — either stated directly ('study Polity') OR confirmed through conversation ('help me revise' → back-and-forth → topic is known). Do NOT wait for the user to restate the topic — if you've determined it, call this tool now.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to study"}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_passage_quiz",
            "description": "Teach a topic from scratch with a reading passage + 3 comprehension questions. Call when user says they know nothing / want basics / 'explain from scratch' / 'I\\'m a beginner' — even if topic came up during conversation, not the opening message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The HCS topic to teach from scratch e.g. 'Panchayati Raj', 'Haryana Geography', 'Indian Economy'"}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_affairs",
            "description": "Fetch latest current affairs / news relevant to HCS exam preparation.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_syllabus_or_paper",
            "description": "Retrieve syllabus topics or past year paper content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content_type": {"type": "string", "enum": ["syllabus", "paper"]},
                    "subject": {"type": "string"},
                    "year": {"type": "string", "description": "4-digit year e.g. '2023'. Omit for latest."}
                },
                "required": ["content_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_progress",
            "description": "Show the user their accuracy by topic, streak, and weak areas.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_updates",
            "description": "Set up recurring automated messages (quiz, news, nightly revision, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_type": {"type": "string", "enum": ["quiz", "current_affairs", "weekly_report", "nightly_revision", "study_material"]},
                    "interval_text": {"type": "string", "description": "e.g. 'daily', 'every 6 hours', 'every morning'"}
                },
                "required": ["job_type", "interval_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_updates",
            "description": "Cancel all active scheduled updates for this user.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
    ,
    {
        "type": "function",
        "function": {
            "name": "get_wrong_answers",
            "description": "Show the user questions they got wrong, with the correct answer and explanation. Use when user says 'show my wrong answers', 'what did I get wrong', 'review my mistakes', or 'wrong answers on [topic]'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Optional HCS topic to filter by e.g. 'Polity', 'Haryana History'. Omit to show wrong answers across all topics."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_exam_date",
            "description": "Save the user's HCS exam date so the bot can show a countdown. Use when user says things like 'my exam is on June 15', 'HCS exam date is 2026-06-20', or 'set my exam date'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_date": {
                        "type": "string",
                        "description": "Exam date in ISO format YYYY-MM-DD e.g. '2026-06-15'"
                    }
                },
                "required": ["exam_date"]
            }
        }
    }
]


def _build_system(current_topic: str, rag_context: str) -> str:
    system = SYSTEM_PROMPT
    if current_topic:
        system += f"\n\nCurrently studying: {current_topic}. Keep answers focused on this topic."
    if rag_context:
        system += f"\n\nRelevant study material:\n{rag_context}"
    return system


async def run_tool_loop(chat_id: str, user_text: str) -> str:
    from bot.memory import get_history, get_current_topic
    from bot.rag import retrieve
    from bot.tools import execute_tool

    history = get_history(chat_id)
    current_topic = get_current_topic(chat_id)
    rag_context = retrieve(user_text) if len(user_text) > 10 else ""

    system = _build_system(current_topic, rag_context)
    MAX_HISTORY = 8
    trimmed = history[-MAX_HISTORY:] if len(history) > MAX_HISTORY else history
    messages = [
        *[{"role": m["role"], "content": m["content"]} for m in trimmed],
        {"role": "user", "content": user_text}
    ]
    client = get_client()

    for _ in range(MAX_ROUNDS):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system}, *messages],
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                max_tokens=1024,
                temperature=0.7,
            )
        except BadRequestError:
            fallback = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system}, *messages[-3:]],
                max_tokens=512,
                temperature=0.7,
            )
            return fallback.choices[0].message.content or "Something went wrong, please try again."
        msg = response.choices[0].message

        if not msg.tool_calls:
            content = msg.content or ""
            text_calls = _parse_text_tool_calls(content)
            if not text_calls:
                return _strip_text_tool_calls(content)
            # Execute text-format tool calls as if they were structured
            for i, (name, args) in enumerate(text_calls):
                result = await execute_tool(name, args, chat_id)
                result_str = str(result)
                if name in _QUIZ_TOOLS:
                    if result_str.startswith("Tool error:"):
                        return result_str
                    from bot.whatsapp import send_message
                    from bot.memory import save_message as _save_message
                    _save_message(chat_id, "assistant", result_str)
                    await send_message(chat_id, result_str)
                    return random.choice(_ENCOURAGEMENTS)
                if name in _DIRECT_RETURN_TOOLS:
                    return result_str
                # For LLM-formatted tools (e.g. get_syllabus_or_paper): must add a
                # matching assistant message or Groq rejects the orphaned tool message
                call_id = f"text_call_{i}"
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": call_id, "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(args)}}],
                })
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_str})
            continue  # let LLM see tool result (only reached for get_syllabus_or_paper)

        # Serialize tool_calls for message history
        tool_calls_serialized = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments}
            }
            for tc in msg.tool_calls
        ]
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": tool_calls_serialized
        })

        tool_results = {}
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = await execute_tool(tc.function.name, args, chat_id)
            tool_results[tc.function.name] = str(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result)
            })

        tool_names = {tc.function.name for tc in msg.tool_calls}

        # Quiz tools: send quiz content directly to WhatsApp, return encouragement
        if tool_names & _QUIZ_TOOLS:
            quiz_results = [tool_results[n] for n in tool_names & _QUIZ_TOOLS]
            if any(r.startswith("Tool error:") for r in quiz_results):
                return quiz_results[0]
            from bot.whatsapp import send_message
            from bot.memory import save_message as _save_message
            for quiz_content in quiz_results:
                _save_message(chat_id, "assistant", quiz_content)
                await send_message(chat_id, quiz_content)
            return random.choice(_ENCOURAGEMENTS)

        # Direct-return tools: already-formatted output, skip LLM round-trip
        if tool_names & _DIRECT_RETURN_TOOLS:
            for name in tool_names & _DIRECT_RETURN_TOOLS:
                return tool_results[name]

    return "I got confused — could you rephrase that?"
