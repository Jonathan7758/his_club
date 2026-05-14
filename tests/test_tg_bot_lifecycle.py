"""
TG Bot 生命周期测试 — RED Phase
测试: /close 命令 / 中断恢复逻辑 / COMPlETED 超时提示
"""
import pytest
from unittest.mock import MagicMock
from src.session_manager import SessionManager, SessionState
from src.tg_bot import TGBotHandler


def make_mock_session_manager():
    sm = SessionManager()
    return sm


class TestCloseCommand:
    def test_close_command_closes_completed_session(self):
        sm = make_mock_session_manager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试内容")
        handler.handle_message(chat_id=12345, text="开始分析")
        sid = handler._get_session_id(12345)
        sm.set_main_topic(sid, "主题", ["论点"])
        sm.confirm_topic(sid)
        sm.set_scores(sid, {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0,
        })
        sm.confirm_score(sid)
        sm.set_sub_series(sid, [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])
        sm.confirm_design(sid)
        sm.set_sub_scores(sid, [{"sub_index": 0, "hot_score": 5, "unique_score": 5, "spread_score": 5, "total_score": 5}])

        response = handler.handle_command(chat_id=12345, command="close")

        assert "关闭" in response or "CLOSED" in response or "close" in response.lower()
        session = sm.get_session(sid)
        assert session["status"] == SessionState.CLOSED

    def test_close_rejected_when_not_completed(self):
        sm = make_mock_session_manager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试")

        response = handler.handle_command(chat_id=12345, command="close")

        assert "还不能" in response or "无法" in response or "未完成" in response

    def test_close_without_session(self):
        sm = make_mock_session_manager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="close")
        assert "没有" in response or "session" in response.lower() or "close" in response.lower()


class TestInterruptRecoveryBot:
    def test_analysis_detects_existing_active_session(self):
        sm = make_mock_session_manager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="第一段内容")
        sid = handler._get_session_id(12345)

        response = handler.handle_command(chat_id=12345, command="analysis")

        assert "已有" in response or "正在" in response
        assert "restart" in response.lower() or "继续" in response

    def test_start_command_after_close_allows_new_session(self):
        sm = make_mock_session_manager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试内容")
        handler.handle_message(chat_id=12345, text="开始分析")
        sid = handler._get_session_id(12345)
        sm.set_main_topic(sid, "主题", ["论点"])
        sm.confirm_topic(sid)
        sm.set_scores(sid, {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0,
        })
        sm.confirm_score(sid)
        sm.set_sub_series(sid, [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])
        sm.confirm_design(sid)
        sm.set_sub_scores(sid, [{"sub_index": 0, "hot_score": 5, "unique_score": 5, "spread_score": 5, "total_score": 5}])
        handler.handle_command(chat_id=12345, command="close")

        response = handler.handle_command(chat_id=12345, command="analysis")

        assert "请发送" in response


class TestStatusShowsClosureInfo:
    def test_status_shows_closed(self):
        sm = make_mock_session_manager()
        handler = TGBotHandler(sm)

        handler.handle_command(chat_id=12345, command="analysis")
        handler.handle_message(chat_id=12345, text="测试")
        handler.handle_message(chat_id=12345, text="开始分析")
        sid = handler._get_session_id(12345)
        sm.set_main_topic(sid, "主题", ["论点"])
        sm.confirm_topic(sid)
        sm.set_scores(sid, {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0,
        })
        sm.confirm_score(sid)
        sm.set_sub_series(sid, [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])
        sm.confirm_design(sid)
        sm.set_sub_scores(sid, [{"sub_index": 0, "hot_score": 5, "unique_score": 5, "spread_score": 5, "total_score": 5}])
        handler.handle_command(chat_id=12345, command="close")

        response = handler.handle_command(chat_id=12345, command="status")

        assert "关闭" in response or "CLOSED" in response or "close" in response.lower()
