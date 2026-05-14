"""
TG Bot Runner v4.0
Telegram Bot 启动入口 — 支持 polling 和 webhook 两种模式
集成 TGBotHandler + SessionManager
"""
import os
import sys
import asyncio
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@dataclass
class BotConfig:
    token: str
    mode: str = "polling"
    webhook_url: str = ""
    webhook_port: int = 5050
    allowed_updates: list = field(default_factory=lambda: ["message"])


def create_bot_app(config: BotConfig, tg_handler):
    try:
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
    except ImportError:
        raise ImportError("python-telegram-bot not installed. Run: pip install python-telegram-bot")

    app = Application.builder().token(config.token).build()

    async def handle_message(update, context):
        chat_id = update.effective_chat.id
        text = update.message.text or ""

        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            reply = tg_handler.handle_command(chat_id, cmd, args)
        else:
            reply = tg_handler.handle_message(chat_id, text)

        if reply:
            await update.message.reply_text(reply[:4096])

    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    return app


async def run_polling(app):
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message"])
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        await app.stop()


def run_webhook(app, config: BotConfig):
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    fastapi_app = FastAPI()

    @fastapi_app.post("/tg/webhook")
    async def tg_hook(request: Request):
        try:
            body = await request.json()
            await app.update_queue.put(body)
            return JSONResponse({"status": "ok"})
        except Exception as e:
            return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

    @fastapi_app.on_event("startup")
    async def startup():
        await app.initialize()
        await app.start()
        await app.bot.set_webhook(url=config.webhook_url, allowed_updates=config.allowed_updates)

    uvicorn.run(fastapi_app, host="0.0.0.0", port=config.webhook_port)


if __name__ == "__main__":
    from session_manager import SessionManager
    from tg_bot import TGBotHandler

    token = os.getenv("TG_BOT_TOKEN", "")
    mode = os.getenv("TG_BOT_MODE", "polling")
    webhook_url = os.getenv("TG_WEBHOOK_URL", "")

    if not token:
        print("Error: TG_BOT_TOKEN environment variable not set")
        sys.exit(1)

    config = BotConfig(token=token, mode=mode, webhook_url=webhook_url)

    sm = SessionManager()
    handler = TGBotHandler(sm)
    app = create_bot_app(config, handler)

    if mode == "webhook":
        run_webhook(app, config)
    else:
        asyncio.run(run_polling(app))
