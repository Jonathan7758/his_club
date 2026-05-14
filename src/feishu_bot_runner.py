"""
Feishu Bot Runner v4.0
飞书 Bot 启动入口 — 使用 lark-oapi Channel 模块
"""
import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")


def patch_ws_client():
    """Fix lark-oapi 1.6.1 bug: ws/client.py doesn't set_event_loop before run_until_complete"""
    import lark_oapi.ws.client as wsc
    _orig = wsc.Client.start

    def _patched_start(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._connect())
            loop.run_until_complete(self._disconnect())
        except KeyboardInterrupt:
            pass

    wsc.Client.start = _patched_start


def main():
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    if not app_id or not app_secret:
        print("Error: LARK_APP_ID and LARK_APP_SECRET must be set")
        sys.exit(1)

    patch_ws_client()

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
        channel.stop()

    import signal
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Feishu bot starting via WebSocket...")
    channel.start()


if __name__ == "__main__":
    main()
