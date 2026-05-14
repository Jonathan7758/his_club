"""
Telegram Bot Handler v4.0
TG命令处理 + 消息路由 + session绑定
依赖: session_manager.py
"""
from session_manager import SessionManager, SessionState, CONTENT_ACCEPTING_STATES


class TGBotHandler:
    def __init__(self, session_manager: SessionManager):
        self.sm = session_manager
        self._chat_sessions = {}

    def _get_session_id(self, chat_id: int) -> str | None:
        return self._chat_sessions.get(chat_id)

    def _set_session(self, chat_id: int, session_id: str):
        self._chat_sessions[chat_id] = session_id

    def _clear_session(self, chat_id: int):
        self._chat_sessions.pop(chat_id, None)

    def handle_command(self, chat_id: int, command: str, args: str = "") -> str:
        cmd = command.strip("/").lower()

        if cmd in ("start", "help"):
            return self._cmd_welcome()
        elif cmd == "analysis":
            return self._cmd_analysis(chat_id)
        elif cmd == "status":
            return self._cmd_status(chat_id)
        elif cmd == "restart":
            return self._cmd_restart(chat_id)
        elif cmd == "export":
            return self._cmd_export(chat_id)
        elif cmd == "close":
            return self._cmd_close(chat_id)
        else:
            return f"未知命令: /{command}。可用的命令: /analysis /status /restart /export"

    def handle_message(self, chat_id: int, text: str) -> str:
        text = text.strip()
        session_id = self._get_session_id(chat_id)

        if text == "开始分析":
            return self._on_trigger_analysis(chat_id, session_id)

        if text == "确认":
            return self._on_confirm(chat_id, session_id)

        if session_id is None:
            return "请先输入 /analysis 启动分析会话。"

        session = self.sm.get_session(session_id)
        if session is None:
            return "会话已失效，请输入 /analysis 重新开始。"

        if session["status"] in CONTENT_ACCEPTING_STATES:
            result = self.sm.add_content(session_id, text)
            return (
                f"✅ 已收到消息 #{result['message_count']}，"
                f"共 {result['char_count']:,} 字。继续发送或输入「开始分析」。"
            )

        return "当前状态不允许输入内容。输入 /status 查看状态，或 /restart 重新开始。"

    def _cmd_welcome(self) -> str:
        return (
            "欢迎使用历史公众号系列分析引擎 v4.0\n\n"
            "可用命令:\n"
            "/analysis — 启动新的系列分析\n"
            "/status — 查看当前分析状态\n"
            "/restart — 重置当前会话\n"
            "/export — 导出系列设计文档\n"
            "/close — 关闭已完成的分析会话\n\n"
            "使用方式: 输入 /analysis，然后发送你要分析的内容，"
            "最后输入「开始分析」触发分析流程。"
        )

    def _cmd_analysis(self, chat_id: int) -> str:
        existing = self._get_session_id(chat_id)
        if existing:
            session = self.sm.get_session(existing)
            if session and session["status"] not in (SessionState.COMPLETED, SessionState.CLOSED):
                return (
                    f"已有分析会话正在进行中 (状态: {session['status']})。\n"
                    "请先输入 /restart 重置，或继续当前会话。"
                )
            elif session and session["status"] == SessionState.COMPLETED:
                return (
                    "有一个已完成的分析会话尚未关闭。\n"
                    "输入 /close 关闭它，或 /export 导出，或 /restart 重新开始。"
                )

        session = self.sm.create_session(tg_chat_id=chat_id)
        self._set_session(chat_id, session["id"])

        return (
            "请发送您要分析的内容。可以是微信公众号系列文章的初步分析文本。\n"
            "如果内容较长，请分段发送。输入完成后，请发送：开始分析"
        )

    def _cmd_status(self, chat_id: int) -> str:
        session_id = self._get_session_id(chat_id)
        if not session_id:
            return "当前没有分析会话。输入 /analysis 开始。"

        session = self.sm.get_session(session_id)
        if not session:
            return "会话数据丢失，请 /restart 重新开始。"

        status_labels = {
            SessionState.WAITING_CONTENT: "等待内容输入",
            SessionState.COLLECTING: "收集中",
            SessionState.SUMMARIZING: "提取主题中",
            SessionState.ANALYZING: "分析中",
            SessionState.CONFIRM_SCORE: "等待确认评分",
            SessionState.DESIGNING: "设计中",
            SessionState.CONFIRM_DESIGN: "等待确认设计",
            SessionState.SUB_SCORING: "子主题评分中",
            SessionState.COMPLETED: "已完成",
            SessionState.CLOSED: "已关闭",
        }

        lines = [
            f"状态: {status_labels.get(session['status'], session['status'])}",
            f"消息数: {session['message_count']}",
            f"总字数: {session['char_count']:,}",
        ]

        if session.get("main_topic"):
            lines.append(f"主主题: {session['main_topic']}")

        if session.get("key_points"):
            lines.append(f"关键论点: {len(session['key_points'])} 条")

        if session.get("scores"):
            s = session["scores"]
            lines.append(f"综合评分: {s.get('total_score', 'N/A')}")

        if session.get("sub_series"):
            lines.append(f"子系列数: {len(session['sub_series'])} 个")

        return "\n".join(lines)

    def _cmd_restart(self, chat_id: int) -> str:
        session_id = self._get_session_id(chat_id)
        if session_id:
            try:
                self.sm.restart(session_id)
            except KeyError:
                pass
        self._clear_session(chat_id)
        return "会话已重置。输入 /analysis 开始新的分析。"

    def _cmd_export(self, chat_id: int) -> str:
        session_id = self._get_session_id(chat_id)
        if not session_id:
            return "没有可导出的会话。"
        if self.sm.is_doc_ready(session_id):
            return "文档已就绪，正在生成导出..."
        return "分析尚未完成，无法导出。输入 /status 查看进度。"

    def _cmd_close(self, chat_id: int) -> str:
        session_id = self._get_session_id(chat_id)
        if not session_id:
            return "没有可关闭的会话。"
        try:
            self.sm.close_session(session_id)
            return "✅ 会话已关闭。感谢使用！输入 /analysis 可开始新的分析。"
        except ValueError as e:
            return f"还不能关闭：{e}"

    def _on_trigger_analysis(self, chat_id: int, session_id: str | None) -> str:
        if not session_id:
            return "请先输入 /analysis 启动会话，然后发送分析内容。"

        try:
            self.sm.trigger_analysis(session_id)
        except ValueError as e:
            return f"无法开始分析：{e}"

        session = self.sm.get_session(session_id)
        preview = session["content"][:200].replace("\n", " ")

        return (
            "🔍 正在提取主题...\n\n"
            f"📋 内容预览: {preview}...\n\n"
            f"共 {session['char_count']:,} 字，正在分析中..."
        )

    def _on_confirm(self, chat_id: int, session_id: str | None) -> str:
        if not session_id:
            return "当前没有分析会话。"

        session = self.sm.get_session(session_id)
        if not session:
            return "会话已失效。"

        state = session["status"]

        if state == SessionState.SUMMARIZING:
            try:
                self.sm.confirm_topic(session_id)
            except ValueError as e:
                return str(e)
            return "✅ 主题已确认。📊 开始多维度分析..."

        if state == SessionState.CONFIRM_SCORE:
            try:
                self.sm.confirm_score(session_id)
            except ValueError as e:
                return str(e)
            return "✅ 评分已确认。📐 正在设计子系列拆分..."

        if state == SessionState.CONFIRM_DESIGN:
            try:
                self.sm.confirm_design(session_id)
            except ValueError as e:
                return str(e)
            return "✅ 设计已确认。📊 正在对每个子主题独立评分..."

        return f"当前状态 ({state}) 不需要确认操作。"
