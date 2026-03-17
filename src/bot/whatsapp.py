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

def parse_webhook(body: dict) -> tuple | None:
    """
    Returns (chat_id, sender_phone, text, is_group).
    chat_id = group_id for groups, sender phone for DMs.
    """
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        msg = entry["messages"][0]
        if msg["type"] != "text":
            return None

        sender = msg["from"]
        text = msg["text"]["body"]

        # Group messages have a "context" with group id, or the recipient is a group JID
        # Meta sends group_id in entry.changes.value.metadata or msg context
        metadata = entry.get("metadata", {})
        group_id = None

        # Check if message came from a group (group JIDs contain @g.us in some SDKs,
        # but Meta Cloud API uses a numeric group ID in msg["context"]["from"] or
        # the "recipient_id" field when the bot is mentioned)
        contacts = entry.get("contacts", [{}])
        recipient_id = metadata.get("display_phone_number")

        # Meta Cloud API: group messages include msg["context"]["from"] pointing to group
        ctx = msg.get("context", {})
        if ctx.get("from") and ctx["from"] != sender:
            group_id = ctx["from"]

        # Alternative: some group payloads include a "group" key
        if not group_id and msg.get("group"):
            group_id = msg["group"].get("id")

        is_group = group_id is not None
        chat_id = group_id if is_group else sender

        return chat_id, sender, text, is_group
    except (KeyError, IndexError, TypeError):
        return None
