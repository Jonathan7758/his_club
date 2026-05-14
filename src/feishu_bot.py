"""
Feishu Bot Handler v4.0
飞书消息适配层 — 复用 TGBotHandler 的业务逻辑
"""
from tg_bot import TGBotHandler
from session_manager import SessionManager


class FeishuBotHandler:
    def __init__(self, session_manager: SessionManager):
        self._handler = TGBotHandler(session_manager)

    def _chat_id(self, feishu_id: str) -> int:
        return hash(feishu_id) % (2 ** 31)

    def handle_message(self, chat_id: str, text: str) -> str:
        cid = self._chat_id(chat_id)
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            return self._handler.handle_command(cid, cmd, args)
        return self._handler.handle_message(cid, text)
