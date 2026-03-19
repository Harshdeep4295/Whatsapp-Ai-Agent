import json
from bot.llm import get_client, SYSTEM_PROMPT

MAX_ROUNDS = 5

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "start_quiz",
            "description": "Start a practice MCQ quiz. Use when user says 'quiz me', 'practice', 'test me', or asks for questions.",
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
            "description": "Start a full mock test with multiple questions answered one by one. Optionally restrict to a single topic.",
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
            "description": "Start a guided study session on a topic — teach + quiz combined.",
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
                    "year": {"type": "integer"}
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
    messages = [
        *[{"role": m["role"], "content": m["content"]} for m in history],
        {"role": "user", "content": user_text}
    ]
    client = get_client()

    for _ in range(MAX_ROUNDS):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system}, *messages],
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.7,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

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

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = await execute_tool(tc.function.name, args, chat_id)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result)
            })

    return "I got confused — could you rephrase that?"
