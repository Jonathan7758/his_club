"""
Feishu Bot Runner v4.0
飞书 Bot 启动入口 — 使用 lark-oapi Channel 原生 connect()
"""
import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def main():
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    if not app_id or not app_secret:
        print("Error: LARK_APP_ID and LARK_APP_SECRET must be set")
        sys.exit(1)

    import nest_asyncio
    nest_asyncio.apply()

    from lark_oapi.channel import FeishuChannel
    from session_manager import SessionManager
    from feishu_bot import FeishuBotHandler

    sm = SessionManager()
    handler = FeishuBotHandler(sm)
    channel = FeishuChannel(app_id=app_id, app_secret=app_secret)

    async def on_message(msg):
        text = (msg.content_text or "").strip()
        print(f"[msg] chat={msg.chat_id} text={text[:120]}")
        if not text:
            return
        try:
            reply = handler.handle_message(chat_id=msg.chat_id, text=text)
            if reply:
                await channel.send(msg.chat_id, {"text": reply[:4096]})
        except Exception as e:
            print(f"[error] {e}")
            import traceback
            traceback.print_exc()

    channel.on("message", on_message)

    def shutdown(signum, frame):
        print("Shutting down...")
        asyncio.ensure_future(channel.disconnect())

    import signal
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Feishu bot connecting via WebSocket...")
    await channel.connect()
    print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
