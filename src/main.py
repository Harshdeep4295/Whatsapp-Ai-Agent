import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from bot.whatsapp import parse_webhook, send_message
from bot.handler import handle_message
from bot.scheduler import start_scheduler, stop_scheduler
from config import WHATSAPP_VERIFY_TOKEN

# In-memory dedup: track last 200 processed message IDs to skip Meta duplicate deliveries
_seen_message_ids: set = set()
_seen_order: list = []

def _is_duplicate(msg_id: str) -> bool:
    if not msg_id:
        return False
    if msg_id in _seen_message_ids:
        return True
    _seen_message_ids.add(msg_id)
    _seen_order.append(msg_id)
    if len(_seen_order) > 200:
        old = _seen_order.pop(0)
        _seen_message_ids.discard(old)
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health():
    return {"status": "running"}

@app.get("/webhook")
def verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Forbidden", status_code=403)

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    # Extract message ID for dedup before parsing
    try:
        msg_id = body["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
        if _is_duplicate(msg_id):
            print(f"[webhook] duplicate message {msg_id}, skipping")
            return {"status": "ok"}
    except (KeyError, IndexError, TypeError):
        pass

    result = parse_webhook(body)
    if result:
        chat_id, sender, text, is_group = result
        print(f"[webhook] ← {sender} | {text!r}")
        reply = await handle_message(chat_id, sender, text, is_group)
        if reply is not None:
            await send_message(chat_id if is_group else sender, reply)
    return {"status": "ok"}
