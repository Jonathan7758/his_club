"""
SessionManager 测试 — RED Phase
测试状态机全流程: 创建 → 内容收集 → 触发分析 → 确认主题 → 
评分 → 确认评分 → 系列设计 → 确认设计 → 子评分 → 完成
"""
import pytest
from src.session_manager import SessionManager, SessionState


class TestSessionCreation:
    def test_create_session_returns_id_and_default_state(self):
        mgr = SessionManager()
        session = mgr.create_session(tg_chat_id=12345)

        assert "id" in session
        assert session["tg_chat_id"] == 12345
        assert session["status"] == SessionState.WAITING_CONTENT
        assert session["content"] == ""
        assert session["message_count"] == 0
        assert session["char_count"] == 0

    def test_create_session_unique_ids(self):
        mgr = SessionManager()
        s1 = mgr.create_session(tg_chat_id=111)
        s2 = mgr.create_session(tg_chat_id=222)

        assert s1["id"] != s2["id"]

    def test_get_session_returns_none_for_unknown(self):
        mgr = SessionManager()
        assert mgr.get_session("nonexistent") is None


class TestContentCollection:
    def test_add_content_transitions_to_collecting(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)

        result = mgr.add_content(s["id"], "安史之乱是中国历史上...")

        assert result["status"] == SessionState.COLLECTING
        assert result["message_count"] == 1
        assert "安史之乱" in result["content"]

    def test_add_content_increments_counts(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)

        mgr.add_content(s["id"], "第一段内容")
        result = mgr.add_content(s["id"], "第二段内容")

        assert result["message_count"] == 2
        assert result["char_count"] > 0
        assert "第一段内容" in result["content"]
        assert "第二段内容" in result["content"]

    def test_add_content_rejects_in_non_collecting_states(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)

        mgr.add_content(s["id"], "内容1")
        mgr.trigger_analysis(s["id"])

        with pytest.raises(ValueError, match="不能添加内容"):
            mgr.add_content(s["id"], "内容2")


class TestAnalysisTrigger:
    def test_trigger_without_content_raises(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)

        with pytest.raises(ValueError, match="没有内容"):
            mgr.trigger_analysis(s["id"])

    def test_trigger_transitions_to_summarizing(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "安史之乱的前因后果分析...")

        result = mgr.trigger_analysis(s["id"])

        assert result["status"] == SessionState.SUMMARIZING
        assert result["content"] == "安史之乱的前因后果分析..."


class TestTopicConfirmation:
    def test_set_main_topic_stores_topic_and_points(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "唐宋变革分析...")
        mgr.trigger_analysis(s["id"])

        result = mgr.set_main_topic(
            s["id"],
            topic="唐宋变革的多维度分析",
            key_points=["政治制度演变", "经济中心南移", "文化转型"]
        )

        assert result["main_topic"] == "唐宋变革的多维度分析"
        assert len(result["key_points"]) == 3

    def test_confirm_topic_transitions_to_analyzing(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试内容")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "测试主题", ["论点1"])

        result = mgr.confirm_topic(s["id"])

        assert result["status"] == SessionState.ANALYZING

    def test_confirm_topic_rejects_without_topic_set(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])

        with pytest.raises(ValueError, match="尚未设置主主题"):
            mgr.confirm_topic(s["id"])

    def test_confirm_topic_rejects_in_wrong_state(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])

        with pytest.raises(ValueError, match="不允许的操作"):
            mgr.confirm_topic(s["id"])


class TestScoring:
    def test_set_scores_stores_and_transitions(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])

        scores = {
            "hot_score": {"value": 7.2, "evidence": "搜狗微信128篇"},
            "unique_score": {"value": 8.5, "evidence": "7维中5维未覆盖"},
            "spread_score": {"value": 7.8, "evidence": "博弈冲突度7.2"},
            "total_score": 7.83
        }
        result = mgr.set_scores(s["id"], scores)

        assert result["status"] == SessionState.CONFIRM_SCORE
        assert result["scores"]["hot_score"]["value"] == 7.2
        assert result["scores"]["total_score"] == 7.83

    def test_confirm_score_transitions_to_designing(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0
        })

        result = mgr.confirm_score(s["id"])

        assert result["status"] == SessionState.DESIGNING

    def test_confirm_score_rejects_without_scores_set(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])

        with pytest.raises(ValueError, match="尚未设置评分"):
            mgr.confirm_score(s["id"])


class TestSubSeriesDesign:
    def test_set_sub_series_stores_designs(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0
        })
        mgr.confirm_score(s["id"])

        sub_series = [
            {
                "dimension": "政治制度",
                "name": "权力的代价",
                "viewpoint": "核心观点",
                "outline": ["一", "二", "三"],
                "quotes": ["金句1", "金句2"]
            }
        ]
        result = mgr.set_sub_series(s["id"], sub_series)

        assert result["status"] == SessionState.CONFIRM_DESIGN
        assert len(result["sub_series"]) == 1
        assert result["sub_series"][0]["dimension"] == "政治制度"

    def test_confirm_design_transitions_to_sub_scoring(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0
        })
        mgr.confirm_score(s["id"])
        mgr.set_sub_series(s["id"], [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])

        result = mgr.confirm_design(s["id"])

        assert result["status"] == SessionState.SUB_SCORING


class TestSubScoringAndCompletion:
    def test_set_sub_scores_transitions_to_completed(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0
        })
        mgr.confirm_score(s["id"])
        mgr.set_sub_series(s["id"], [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])
        mgr.confirm_design(s["id"])

        sub_scores = [
            {
                "sub_index": 0,
                "hot_score": 6.5,
                "unique_score": 9.0,
                "spread_score": 7.5,
                "total_score": 7.8
            }
        ]
        result = mgr.set_sub_scores(s["id"], sub_scores)

        assert result["status"] == SessionState.COMPLETED
        assert result["sub_scores"][0]["total_score"] == 7.8

    def test_is_doc_ready_true_when_completed(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])
        mgr.confirm_topic(s["id"])
        mgr.set_scores(s["id"], {
            "hot_score": {"value": 5, "evidence": ""},
            "unique_score": {"value": 5, "evidence": ""},
            "spread_score": {"value": 5, "evidence": ""},
            "total_score": 5.0
        })
        mgr.confirm_score(s["id"])
        mgr.set_sub_series(s["id"], [{"dimension": "政治", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}])
        mgr.confirm_design(s["id"])
        mgr.set_sub_scores(s["id"], [{"sub_index": 0, "hot_score": 5, "unique_score": 5, "spread_score": 5, "total_score": 5}])

        assert mgr.is_doc_ready(s["id"]) is True

    def test_is_doc_ready_false_before_completed(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试")

        assert mgr.is_doc_ready(s["id"]) is False


class TestRestartAndEdgeCases:
    def test_restart_resets_to_waiting_content(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "测试内容")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论点"])

        result = mgr.restart(s["id"])

        assert result["status"] == SessionState.WAITING_CONTENT
        assert result["content"] == ""
        assert result["message_count"] == 0
        assert result["char_count"] == 0

    def test_restart_nonexistent_raises(self):
        mgr = SessionManager()

        with pytest.raises(KeyError):
            mgr.restart("nonexistent")

    def test_message_split_calculation(self):
        mgr = SessionManager()

        chunks = mgr.split_long_content("A" * 5000, max_len=4096)

        assert len(chunks) == 2
        assert chunks[0] == "A" * 4096
        assert chunks[1] == "A" * (5000 - 4096)

    def test_message_split_short_content(self):
        mgr = SessionManager()

        chunks = mgr.split_long_content("短内容", max_len=4096)

        assert len(chunks) == 1
        assert chunks[0] == "短内容"

    def test_get_session_stats(self):
        mgr = SessionManager()
        s = mgr.create_session(tg_chat_id=12345)
        mgr.add_content(s["id"], "第一段")
        mgr.add_content(s["id"], "第二段")
        mgr.trigger_analysis(s["id"])
        mgr.set_main_topic(s["id"], "主题", ["论1", "论2"])

        stats = mgr.get_session(s["id"])

        assert stats["status"] == SessionState.SUMMARIZING
        assert stats["message_count"] == 2
        assert stats["main_topic"] == "主题"
        assert len(stats["key_points"]) == 2
