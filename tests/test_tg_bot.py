"""
TG Bot Handler 测试 — RED Phase
测试命令解析、消息路由、状态驱动的响应逻辑
"""
import pytest
from src.session_manager import SessionManager, SessionState
from src.tg_bot import TGBotHandler


class TestStartAndHelp:
    def test_start_command_returns_welcome(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="start")

        assert "欢迎" in response or "Hi" in response.lower() or "hello" in response.lower()
        assert "/analysis" in response

    def test_unknown_command_returns_help(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="unknown_cmd")

        assert "未知" in response or "unknown" in response.lower() or "help" in response.lower()


class TestAnalysisStart:
    def test_analysis_creates_session_and_prompts(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="analysis")

        assert "请发送" in response
        assert "开始分析" in response

    def test_analysis_when_session_exists_asks_restart(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试内容")

        response = handler.handle_command(chat_id=12345, command="analysis")

        assert ("已有" in response or "正在" in response or "restart" in response.lower())


class TestContentCollection:
    def test_content_message_accepted_during_collection(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        response = handler.handle_message(chat_id=12345, text="安史之乱的前因后果分析...")

        assert "已收到" in response
        assert "消息" in response

    def test_content_message_outside_session_prompts_analysis(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_message(chat_id=12345, text="随机文本")

        assert "请先输入" in response or "/analysis" in response

    def test_content_message_shows_char_count(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        response = handler.handle_message(chat_id=12345, text="A" * 500)

        assert "500" in response


class TestTriggerAnalysis:
    def test_start_analysis_keyword_triggers(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="安史之乱分析内容...")

        response = handler.handle_message(chat_id=12345, text="开始分析")

        assert "提取" in response or "分析" in response
        assert "主题" in response or "论点" in response

    def test_start_analysis_without_content_fails(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")

        response = handler.handle_message(chat_id=12345, text="开始分析")

        assert "没有内容" in response or "请先发送" in response

    def test_start_analysis_variants(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试内容123")

        for keyword in ["开始分析", "开始分析 ", " 开始分析"]:
            r = handler.handle_message(chat_id=12345, text=keyword)
            assert r is not None


class TestConfirmations:
    def test_keyword_confirm_works_after_topic_extraction(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="安史之乱分析")
        handler.handle_message(chat_id=12345, text="开始分析")
        sm_sess = sm.get_session(handler._get_session_id(12345))
        sm.set_main_topic(sm_sess["id"], "测试主题", ["论1", "论2"])

        response = handler.handle_message(chat_id=12345, text="确认")

        assert "分析" in response or "开始" in response


class TestStatusAndRestart:
    def test_status_shows_waiting_when_no_session(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="status")

        assert "没有" in response or "无" in response or "status" in response.lower()

    def test_status_shows_session_info(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试内容")
        handler.handle_message(chat_id=12345, text="开始分析")
        sm_sess = sm.get_session(handler._get_session_id(12345))
        sm.set_main_topic(sm_sess["id"], "测试主题", ["论1"])

        response = handler.handle_command(chat_id=12345, command="status")

        assert "测试主题" in response
        assert "SUMMARIZING" in response or "提取" in response

    def test_restart_clears_and_returns_to_waiting(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试内容")

        response = handler.handle_command(chat_id=12345, command="restart")

        assert ("重置" in response or "重新" in response or "restart" in response.lower() or "已" in response)
        assert handler._get_session_id(12345) is None
