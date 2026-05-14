"""
Feishu Bot Runner v4.0
"""
import os
import sys
import asyncio
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def patch_ws_client():
    import lark_oapi.ws.client as wsc

    _orig_connect = wsc.Client._connect

    async def _patched_connect(self):
        await _orig_connect(self)
        print("[ws] _connect done, starting event loop")

    wsc.Client._connect = _patched_connect

    def _patched_start(self):
        async def _run():
            try:
                await self._connect()
                print("[ws] connected, entering event loop")
                await asyncio.Event().wait()
            except Exception as e:
                print(f"[ws] disconnected: {e}")

        asyncio.run(_run())

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
                print(f"[send] -> {msg.chat_id}")
                await channel.send(msg.chat_id, {"text": reply[:4096]})
        except Exception as e:
            print(f"[error] {e}")
            import traceback
            traceback.print_exc()

    async def on_reconnecting():
        print("[event] reconnecting...")

    async def on_reconnected():
        print("[event] reconnected")

    def on_error(err):
        print(f"[event] error: {err}")

    channel.on("message", on_message)
    channel.on("reconnecting", on_reconnecting)
    channel.on("reconnected", on_reconnected)
    channel.on("error", on_error)

    def shutdown(signum, frame):
        print("Shutting down...")
        channel.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Feishu bot starting via WebSocket...")
    channel.start()


if __name__ == "__main__":
    main()
