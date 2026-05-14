"""
集成测试 — 端到端全流程验证 (mock LLM/DB)
测试: TG webhook → session创建 → 内容收集 → 触发分析 → 确认流程 → 导出
"""
import pytest
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.session_manager import SessionManager, SessionState
from src.tg_bot import TGBotHandler
from src.api import create_app


@pytest.fixture
def client():
    sm = SessionManager()
    handler = TGBotHandler(sm)
    app = create_app(session_manager=sm, tg_handler=handler)
    return TestClient(app)


def send_msg(client, chat_id, text):
    return client.post("/tg/webhook", json={
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id},
            "text": text,
            "date": 1715200000,
        }
    })


class TestE2EFlow:
    def test_full_analysis_session_commands(self, client):
        r1 = send_msg(client, 12345, "/analysis")
        assert r1.status_code == 200
        assert "请发送" in r1.json()["reply"]

        r2 = send_msg(client, 12345, "安史之乱的前因后果分析，主要关注政治制度的崩溃")
        assert r2.status_code == 200
        assert "已收到" in r2.json()["reply"]

        r3 = send_msg(client, 12345, "经济财政方面，租庸调制的瓦解也是一大原因")
        assert r3.status_code == 200
        assert "已收到" in r3.json()["reply"]

        r4 = send_msg(client, 12345, "开始分析")
        assert r4.status_code == 200
        assert "分析" in r4.json()["reply"] or "提取" in r4.json()["reply"]

        r5 = send_msg(client, 12345, "/status")
        assert r5.status_code == 200
        assert "提取" in r5.json()["reply"] or "消息数" in r5.json()["reply"]

        r6 = send_msg(client, 12345, "/close")
        assert r6.status_code == 200
        assert "还不能" in r6.json()["reply"]

    def test_restart_and_new_session(self, client):
        send_msg(client, 12346, "/analysis")
        send_msg(client, 12346, "测试内容")

        r = send_msg(client, 12346, "/restart")
        assert r.status_code == 200
        assert "重置" in r.json()["reply"] or "restart" in r.json()["reply"].lower()

        r2 = send_msg(client, 12346, "/analysis")
        assert r2.status_code == 200
        assert "请发送" in r2.json()["reply"]

    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == "4.0"

    def test_webhook_error_handling(self, client):
        r = client.post("/tg/webhook", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

        r2 = client.post("/tg/webhook", data="not json")
        assert r2.status_code == 200

    def test_session_isolation(self, client):
        send_msg(client, 111, "/analysis")
        send_msg(client, 111, "用户1的内容")

        send_msg(client, 222, "/analysis")
        send_msg(client, 222, "用户2的内容")

        r1 = send_msg(client, 111, "/status")
        assert "消息数: 1" in r1.json()["reply"]

        r2 = send_msg(client, 222, "/status")
        assert "消息数: 1" in r2.json()["reply"]
