"""
API v4.0 测试 — RED Phase
测试: 健康检查 / TG webhook / 保留端点 / 移除端点验证
使用 FastAPI TestClient
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from src.session_manager import SessionManager, SessionState
from src.tg_bot import TGBotHandler


@pytest.fixture
def client():
    sm = SessionManager()
    handler = TGBotHandler(sm)
    from src.api import create_app
    app = create_app(session_manager=sm, tg_handler=handler)
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["version"] == "4.0"

    def test_health_has_timestamp(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data


class TestTGWebhook:
    def test_webhook_returns_ok(self, client):
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "chat": {"id": 12345},
                "text": "/start",
                "date": 1715200000,
            }
        }
        response = client.post("/tg/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "error")

    def test_webhook_handles_analysis_command(self, client):
        payload = {
            "update_id": 2,
            "message": {
                "message_id": 2,
                "chat": {"id": 12345},
                "text": "/analysis",
                "date": 1715200000,
            }
        }
        response = client.post("/tg/webhook", json=payload)
        assert response.status_code == 200

    def test_webhook_handles_text_message(self, client):
        # First start analysis
        client.post("/tg/webhook", json={
            "update_id": 1,
            "message": {
                "message_id": 1,
                "chat": {"id": 12345},
                "text": "/analysis",
                "date": 1715200000,
            }
        })

        response = client.post("/tg/webhook", json={
            "update_id": 2,
            "message": {
                "message_id": 2,
                "chat": {"id": 12345},
                "text": "安史之乱分析内容",
                "date": 1715200000,
            }
        })
        assert response.status_code == 200
        data = response.json()
        reply = data.get("reply", "")
        assert "已收到" in reply

    def test_webhook_invalid_payload(self, client):
        response = client.post("/tg/webhook", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


class TestRetainedEndpoints:
    def test_monitor_health(self, client):
        response = client.get("/monitor/health")
        assert response.status_code == 200

    def test_monitor_errors(self, client):
        response = client.get("/monitor/errors")
        assert response.status_code == 200

    def test_graph_stats(self, client):
        response = client.get("/graph/stats")
        assert response.status_code == 200

    def test_graph_centrality(self, client):
        response = client.get("/graph/centrality")
        assert response.status_code == 200

    def test_graph_clusters(self, client):
        response = client.get("/graph/clusters")
        assert response.status_code == 200

    def test_graph_gaps(self, client):
        response = client.get("/graph/gaps")
        assert response.status_code == 200


class TestRemovedEndpoints:
    def test_generate_not_found(self, client):
        response = client.post("/generate", json={"topic": "test"})
        assert response.status_code == 404

    def test_hotspot_generate_not_found(self, client):
        response = client.post("/hotspot/generate", json={})
        assert response.status_code == 404

    def test_mirofish_generate_not_found(self, client):
        response = client.post("/mirofish/generate", json={})
        assert response.status_code == 404

    def test_wechat_endpoints_not_found(self, client):
        for ep in ["/wechat/status", "/wechat/push", "/wechat/stats", "/wechat/drafts"]:
            response = client.get(ep)
            assert response.status_code == 404, f"{ep} should be 404"

    def test_dashboard_not_found(self, client):
        response = client.get("/dashboard")
        assert response.status_code == 404

    def test_stats_not_found(self, client):
        response = client.get("/stats")
        assert response.status_code == 404


class TestAnalysisEndpoint:
    def test_analyze_topic(self, client):
        response = client.get("/analyze/安史之乱")
        assert response.status_code == 200

    def test_analyze_engines(self, client):
        response = client.get("/engines/analyze/安史之乱")
        assert response.status_code == 200
