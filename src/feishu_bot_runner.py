"""
Feishu Bot Runner v4.0
飞书 Bot 启动入口 — 使用 lark-oapi Channel 模块 (WebSocket)
"""
import os
import sys
import asyncio
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_manager import SessionManager
from feishu_bot import FeishuBotHandler

channel = None
loop_running = True


async def main():
    global channel
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
        print(f"[msg] chat={msg.chat_id} sender={msg.sender_id} text={text[:80]}")

        if not text:
            return

        try:
            reply = handler.handle_message(chat_id=msg.chat_id, text=text)

            if reply:
                await channel.send(
                    msg.chat_id,
                    {"text": reply[:4096]},
                    {"reply_to": msg.message_id},
                )
        except Exception as e:
            print(f"[error] {e}")
            import traceback
            traceback.print_exc()

    channel.on("message", on_message)

    def shutdown():
        global loop_running
        loop_running = False
        if channel:
            asyncio.ensure_future(channel.disconnect())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, shutdown)
        except NotImplementedError:
            pass

    print("Feishu bot connecting via WebSocket...")
    await channel.connect_until_ready()
    print("Feishu bot ready.")

    while loop_running:
        await asyncio.sleep(1)

    if channel:
        await channel.disconnect()
    print("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
