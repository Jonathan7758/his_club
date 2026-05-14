"""
SessionManager + DB 持久化集成测试 — RED Phase
使用依赖注入模式，通过 mock DB 接口测试持久化逻辑
"""
import pytest
from unittest.mock import MagicMock
from src.session_manager import SessionManager, SessionState


def make_mock_db():
    db = MagicMock()
    db.save_analysis_session = MagicMock()
    db.load_analysis_session = MagicMock(return_value=None)
    db.find_active_sessions_by_chat = MagicMock(return_value=[])
    db.mark_session_closed = MagicMock()
    return db


class TestAutoSave:
    def test_create_session_saves_to_db(self):
        db = make_mock_db()
        mgr = SessionManager(db=db)
        s = mgr.create_session(tg_chat_id=12345)

        db.save_analysis_session.assert_called()
        assert db.save_analysis_session.call_args[0][0]["tg_chat_id"] == 12345

    def test_add_content_saves_to_db(self):
        db = make_mock_db()
        mgr = SessionManager(db=db)
        s = mgr.create_session(tg_chat_id=12345)
        db.save_analysis_session.reset_mock()

        mgr.add_content(s["id"], "测试内容")

        db.save_analysis_session.assert_called()
        assert db.save_analysis_session.call_args[0][0]["status"] == SessionState.COLLECTING

    def test_trigger_analysis_saves(self):
        db = make_mock_db()
        mgr = SessionManager(db=db)
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        db.save_analysis_session.reset_mock()

        mgr.trigger_analysis(s["id"])

        db.save_analysis_session.assert_called()

    def test_autosave_called_on_all_state_changes(self):
        db = make_mock_db()
        mgr = SessionManager(db=db)
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试内容测试内容测试内容")

        call_count_before = db.save_analysis_session.call_count

        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "测试主题", ["论点1"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0,
        })

        assert db.save_analysis_session.call_count > call_count_before


class TestInterruptRecovery:
    def test_restore_session_from_db(self):
        db_data = {
            "id": "restore_001",
            "tg_chat_id": 999,
            "status": SessionState.COLLECTING,
            "content": "已收集的内容",
            "char_count": 7,
            "message_count": 2,
            "main_topic": "测试主题",
            "key_points": ["论点1"],
            "scores": None,
            "sub_series": None,
            "sub_scores": None,
        }
        db = make_mock_db()
        db.load_analysis_session = MagicMock(return_value=db_data)

        mgr = SessionManager(db=db)
        restored = mgr.restore_session("restore_001")

        assert restored["status"] == SessionState.COLLECTING
        assert restored["content"] == "已收集的内容"
        assert restored["main_topic"] == "测试主题"
        db.load_analysis_session.assert_called_with("restore_001")

    def test_get_session_falls_back_to_db(self):
        db_data = {
            "id": "fallback_001",
            "tg_chat_id": 999,
            "status": SessionState.ANALYZING,
            "content": "内容",
            "char_count": 2,
            "message_count": 1,
            "main_topic": None,
            "key_points": None,
            "scores": None,
            "sub_series": None,
            "sub_scores": None,
        }
        db = make_mock_db()
        db.load_analysis_session = MagicMock(return_value=db_data)

        mgr = SessionManager(db=db)
        session = mgr.get_session("fallback_001")

        assert session is not None
        assert session["status"] == SessionState.ANALYZING

    def test_find_interrupted_session_by_chat(self):
        db_data = [{"id": "interrupted_001", "tg_chat_id": 555, "status": SessionState.ANALYZING}]
        db = make_mock_db()
        db.find_active_sessions_by_chat = MagicMock(return_value=db_data)

        mgr = SessionManager(db=db)
        sessions = mgr.find_active_by_chat(555)

        assert len(sessions) == 1
        assert sessions[0]["id"] == "interrupted_001"

    def test_has_active_session_returns_true(self):
        db = make_mock_db()
        db.find_active_sessions_by_chat = MagicMock(return_value=[{"id": "x", "status": SessionState.COLLECTING}])

        mgr = SessionManager(db=db)
        assert mgr.has_active_session(777) is True

    def test_has_active_session_returns_false(self):
        db = make_mock_db()
        db.find_active_sessions_by_chat = MagicMock(return_value=[])

        mgr = SessionManager(db=db)
        assert mgr.has_active_session(777) is False


class TestCloseSession:
    def test_close_session_transitions_to_closed(self):
        db = make_mock_db()
        mgr = SessionManager(db=db)
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0,
        })
        mgr.confirm_score(s["id"])
        mgr.set_sub_series(s["id"], [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])
        mgr.confirm_design(s["id"])
        mgr.set_sub_scores(s["id"], [{"sub_index": 0, "hot_score": 5, "unique_score": 5, "spread_score": 5, "total_score": 5}])
        db.save_analysis_session.reset_mock()

        result = mgr.close_session(s["id"])

        assert result["status"] == SessionState.CLOSED
        db.save_analysis_session.assert_called()
        db.mark_session_closed.assert_called_with(s["id"])

    def test_close_rejects_non_completed(self):
        db = make_mock_db()
        mgr = SessionManager(db=db)
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")

        with pytest.raises(ValueError, match="COMPLETED"):
            mgr.close_session(s["id"])
