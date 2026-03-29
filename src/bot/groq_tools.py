import json
import re
from bot.llm import SYSTEM_PROMPT, _create_with_fallback


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
            "description": "Start a guided study session (overview + 3 questions) on a specific topic. Call when a study topic has been established — either named directly ('study Polity', 'teach me Haryana History') OR confirmed through conversation (user said 'help me revise' → you asked → they confirmed a topic). Once the topic is clear, call this immediately — do NOT keep chatting. Still ask for topic if genuinely unknown.",
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
            "description": "Teach a topic from absolute scratch for a complete beginner — generates a simple reading passage on the topic, then asks 3 comprehension questions from that passage. Use when user says 'teach me from scratch', 'explain like I know nothing', 'I have no idea about X', 'zero to hero on X', 'start from basics', 'I am a beginner at X', or similar. Do NOT use for users who just want a quick quiz — use start_quiz for that.",
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
    ,
    {
        "type": "function",
        "function": {
            "name": "start_hpsc_mock",
            "description": "Start a full HPSC blueprint mock test with questions distributed exactly like the real exam paper (History ~22%, Science ~20%, Polity ~15%, Geography ~11%, etc.). Use when user says 'hpsc mock', 'blueprint mock', 'full mock test', '100 question mock', 'paper 1 mock', or asks for a mock that mimics the real exam distribution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_count": {
                        "type": "integer",
                        "description": "Number of questions (default 25, max 50). Scales blueprint proportionally."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_haryana_special",
            "description": "Start a Haryana-only drill covering folk culture (Bhumia, Ghethi), heritage sites, 1857 regional leaders (Rao Tularam, Dhanu Singh), Haryana geography, schemes, and personalities. These are the cutoff-deciding questions absent from national resources. Use when user says 'haryana special', 'haryana quiz', 'haryana drill', 'haryana only', 'haryana culture quiz', or anything about specifically drilling Haryana content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_count": {
                        "type": "integer",
                        "description": "Number of questions (default 10, max 20)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_and_summarise",
            "description": (
                "Search the web for HCS exam-relevant information and return a summarised answer. "
                "Use ONLY when the user asks about an HCS-related topic you cannot answer from memory — "
                "e.g. 'search Haryana budget 2025', 'what's the latest on HPSC notification', "
                "'update me on Haryana agriculture policy', 'find out about [HCS syllabus topic]'. "
                "DO NOT use for general current affairs — use get_current_affairs for that. "
                "DO NOT use for quiz or syllabus questions — use the appropriate quiz tool. "
                "DO NOT use for questions unrelated to HCS exam preparation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query exactly as the user phrased it."
                    }
                },
                "required": ["query"]
            }
        }
    },
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
    for _ in range(MAX_ROUNDS):
        try:
            response, _ = _create_with_fallback(
                [{"role": "system", "content": system}, *messages],
                max_tokens=1024,
                temperature=0.7,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
        except Exception as e:
            err = str(e)
            if "400" in err or "bad_request" in err.lower():
                try:
                    response, _ = _create_with_fallback(
                        [{"role": "system", "content": system}, *messages[-3:]],
                        max_tokens=512,
                        temperature=0.7,
                    )
                    return response.choices[0].message.content or "Something went wrong, please try again."
                except Exception:
                    pass
            return "I'm having trouble right now — please try again in a moment! 🙏"
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
                call_id = f"text_call_{i}"
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": call_id, "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(args)}}],
                })
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_str})
                if result_str.startswith("Tool error:"):
                    return "Something went wrong — could you try again?"
            continue  # let LLM respond naturally

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
            result_str = str(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str
            })
            if result_str.startswith("Tool error:"):
                return "Something went wrong — could you try again?"

    return "I got confused — could you rephrase that?"
