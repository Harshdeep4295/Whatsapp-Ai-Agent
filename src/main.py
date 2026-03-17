import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from bot.whatsapp import parse_webhook, send_message
from bot.handler import handle_message
from bot.scheduler import start_scheduler, stop_scheduler
from config import WHATSAPP_VERIFY_TOKEN

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
    result = parse_webhook(body)
    if result:
        chat_id, sender, text, is_group = result
        reply = await handle_message(chat_id, sender, text, is_group)
        # In groups reply to group; in DMs reply to sender
        await send_message(chat_id if is_group else sender, reply)
    return {"status": "ok"}
