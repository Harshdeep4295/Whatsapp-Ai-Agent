import httpx
from config import WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN

GRAPH_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

async def send_message(to: str, text: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4000]},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(GRAPH_URL, json=payload, headers=HEADERS)
        if r.status_code != 200:
            print(f"[whatsapp] send failed {r.status_code}: {r.text}")


async def send_interactive_quiz(to: str, question: str, options: dict, topic: str = ""):
    """Send quiz question as an interactive list with A/B/C/D tappable rows."""
    rows = [{"id": k, "title": f"{k}. {v[:72]}"} for k, v in options.items()]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": (topic or "HCS Quiz")[:60]},
            "body": {"text": question[:1024]},
            "footer": {"text": "Tap to select your answer"},
            "action": {
                "button": "Choose Answer",
                "sections": [{"title": "Options", "rows": rows}],
            },
        },
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(GRAPH_URL, json=payload, headers=HEADERS)
        if r.status_code != 200:
            print(f"[whatsapp] interactive quiz send failed {r.status_code}: {r.text}")


def parse_webhook(body: dict) -> tuple | None:
    """
    Returns (chat_id, sender_phone, text, is_group).
    chat_id = group_id for groups, sender phone for DMs.
    Handles both text messages and interactive replies (list/button taps).
    """
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        msg = entry["messages"][0]
        sender = msg["from"]
        msg_type = msg["type"]

        # Extract text from plain text or interactive tap responses
        if msg_type == "text":
            text = msg["text"]["body"]
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            itype = interactive.get("type")
            if itype == "list_reply":
                text = interactive["list_reply"]["id"]   # "A", "B", "C", or "D"
            elif itype == "button_reply":
                text = interactive["button_reply"]["id"]
            else:
                return None
        else:
            return None

        # Group detection: use explicit group field only.
        # NOTE: msg["context"]["from"] fires on ALL DM replies (it's the quoted message sender,
        # not a group indicator) — do NOT use it for group detection.
        group_id = None
        if msg.get("group"):
            group_id = msg["group"].get("id")

        is_group = group_id is not None
        chat_id = group_id if is_group else sender

        return chat_id, sender, text, is_group
    except (KeyError, IndexError, TypeError):
        return None
