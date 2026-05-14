"""
Feishu Bot Runner v4.0
飞书 Bot 启动入口 — 官方 FeishuChannel + WebSocket
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    if not app_id or not app_secret:
        print("Error: LARK_APP_ID and LARK_APP_SECRET must be set")
        sys.exit(1)

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

    channel.on("message", on_message)

    print("Feishu bot connecting via WebSocket...")
    await channel.connect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
