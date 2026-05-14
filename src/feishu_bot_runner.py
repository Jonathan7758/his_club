"""
Feishu Bot Runner v4.0
飞书 Bot 启动入口 — 使用 lark-oapi Channel 模块 (WebSocket)
无需公网地址, 飞书服务器在国内可直接连接
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_manager import SessionManager
from feishu_bot import FeishuBotHandler


async def main():
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

    print("Feishu bot connecting via WebSocket...")
    await channel.connect()


if __name__ == "__main__":
    asyncio.run(main())
