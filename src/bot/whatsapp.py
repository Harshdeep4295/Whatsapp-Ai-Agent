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
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        msg = entry["messages"][0]
        if msg["type"] != "text":
            return None
        return msg["from"], msg["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return None
