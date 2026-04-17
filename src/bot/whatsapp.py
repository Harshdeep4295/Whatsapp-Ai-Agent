import httpx
import json
import logging
from config import WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

GRAPH_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

# Log config on startup
logger.info(f"[WHATSAPP CONFIG] Phone ID: {WHATSAPP_PHONE_NUMBER_ID}")
logger.info(f"[WHATSAPP CONFIG] Graph URL: {GRAPH_URL}")
logger.info(f"[WHATSAPP CONFIG] Token present: {'Yes' if WHATSAPP_ACCESS_TOKEN else 'NO - ERROR!'}")
logger.info(f"[WHATSAPP CONFIG] Token length: {len(WHATSAPP_ACCESS_TOKEN) if WHATSAPP_ACCESS_TOKEN else 0}")
logger.info(f"[WHATSAPP CONFIG] Token first 10 chars: {WHATSAPP_ACCESS_TOKEN[:10] if WHATSAPP_ACCESS_TOKEN else 'N/A'}...")
if not WHATSAPP_ACCESS_TOKEN:
    logger.error("❌ WHATSAPP_ACCESS_TOKEN is NOT SET!")

_CHUNK_LIMIT = 3800  # leave headroom below WhatsApp's 4096 char limit


def _split_message(text: str) -> list[str]:
    """Split text into chunks ≤ _CHUNK_LIMIT, breaking on paragraph then line boundaries."""
    if len(text) <= _CHUNK_LIMIT:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > _CHUNK_LIMIT:
        # Try to break on a double newline (paragraph boundary) within the limit
        split_at = remaining.rfind("\n\n", 0, _CHUNK_LIMIT)
        if split_at == -1:
            # Fall back to single newline
            split_at = remaining.rfind("\n", 0, _CHUNK_LIMIT)
        if split_at == -1:
            # Hard split at limit
            split_at = _CHUNK_LIMIT

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    # Add part indicators if more than one chunk
    if len(chunks) > 1:
        chunks = [f"{c}\n\n_({i+1}/{len(chunks)})_" for i, c in enumerate(chunks)]

    return chunks


async def _send_single(client: httpx.AsyncClient, to: str, text: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    preview = text[:80].replace("\n", " ")

    # Log request details
    logger.info(f"[REQUEST] Sending to: {to} | Text length: {len(text)}ch | Preview: {preview!r}")
    logger.debug(f"[REQUEST] URL: {GRAPH_URL}")
    logger.debug(f"[REQUEST] Payload: {json.dumps(payload, indent=2)}")
    logger.debug(f"[REQUEST] Headers: Authorization: Bearer {WHATSAPP_ACCESS_TOKEN[:10]}..., Content-Type: application/json")

    print(f"[whatsapp] → {to} | {len(text)}ch | {preview!r}")

    try:
        r = await client.post(GRAPH_URL, json=payload, headers=HEADERS)

        # Log response details
        logger.info(f"[RESPONSE] Status Code: {r.status_code}")
        logger.debug(f"[RESPONSE] Headers: {dict(r.headers)}")
        logger.debug(f"[RESPONSE] Body: {r.text}")

        if r.status_code != 200:
            logger.error(f"[ERROR] WhatsApp API returned {r.status_code}: {r.text}")
            print(f"[whatsapp] ✗ send failed {r.status_code}: {r.text}")
            raise RuntimeError(f"WhatsApp API error {r.status_code}: {r.text}")

        logger.info(f"[SUCCESS] Message delivered to {to}")
        print(f"[whatsapp] ✓ delivered")
    except Exception as e:
        logger.exception(f"[EXCEPTION] Error sending message: {str(e)}")
        raise


async def send_message(to: str, text: str):
    parts = _split_message(text)
    async with httpx.AsyncClient() as client:
        for part in parts:
            await _send_single(client, to, part)


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

    logger.info(f"[INTERACTIVE] Sending quiz to: {to} | Topic: {topic} | Question: {question[:60]!r}")
    logger.debug(f"[INTERACTIVE] Payload: {json.dumps(payload, indent=2)}")

    print(f"[whatsapp] → {to} | interactive quiz | {question[:60]!r}")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(GRAPH_URL, json=payload, headers=HEADERS)

            logger.info(f"[INTERACTIVE RESPONSE] Status Code: {r.status_code}")
            logger.debug(f"[INTERACTIVE RESPONSE] Body: {r.text}")

            if r.status_code != 200:
                logger.error(f"[INTERACTIVE ERROR] {r.status_code}: {r.text}")
                print(f"[whatsapp] ✗ interactive quiz send failed {r.status_code}: {r.text}")
                raise RuntimeError(f"WhatsApp API error {r.status_code}: {r.text}")

            logger.info(f"[INTERACTIVE SUCCESS] Quiz delivered to {to}")
            print(f"[whatsapp] ✓ delivered")
        except Exception as e:
            logger.exception(f"[INTERACTIVE EXCEPTION] Error sending quiz: {str(e)}")
            raise


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
