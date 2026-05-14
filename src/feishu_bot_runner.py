"""
Feishu Bot Runner v4.0
飞书 Bot 启动入口 — 使用 lark-oapi Channel 模块同步 API (WebSocket)
"""
import os
import sys
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_manager import SessionManager
from feishu_bot import FeishuBotHandler


def main():
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")

    if not app_id or not app_secret:
        print("Error: LARK_APP_ID and LARK_APP_SECRET must be set")
        sys.exit(1)

    from lark_oapi.channel import FeishuChannel

    sm = SessionManager()
    handler = FeishuBotHandler(sm)

    channel = FeishuChannel(app_id=app_id, app_secret=app_secret)

    async def on_message(msg):
        text = (msg.content_text or "").strip()
        if not text:
            return

        reply = handler.handle_message(chat_id=msg.chat_id, text=text)

        if reply:
            await channel.send(
                msg.chat_id,
                {"text": reply[:4096]},
                {"reply_to": msg.message_id},
            )

    channel.on("message", on_message)

    def shutdown(signum, frame):
        print("Shutting down...")
        channel.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Feishu bot starting via WebSocket...")
    channel.start()


if __name__ == "__main__":
    main()
