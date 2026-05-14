"""
TG Bot 真实接入测试 — RED Phase
测试: Bot启动入口 / polling模式 / TGBotHandler 集成
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.session_manager import SessionManager, SessionState
from src.tg_bot import TGBotHandler


class TestBotEntryPoint:
    def test_create_bot_app(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        from src.tg_bot_runner import create_bot_app, BotConfig
        config = BotConfig(token="test_token_12345", mode="polling")
        app = create_bot_app(config, handler)

        assert app is not None

    def test_bot_config_defaults(self):
        from src.tg_bot_runner import BotConfig
        config = BotConfig(token="test_token")
        assert config.mode == "polling"
        assert config.token == "test_token"

    def test_bot_config_webhook_mode(self):
        from src.tg_bot_runner import BotConfig
        config = BotConfig(token="test_token", mode="webhook", webhook_url="https://example.com/webhook")
        assert config.mode == "webhook"
        assert config.webhook_url == "https://example.com/webhook"

    def test_bot_handlers_registered(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        from src.tg_bot_runner import create_bot_app, BotConfig
        config = BotConfig(token="test_token")
        app = create_bot_app(config, handler)

        handlers = app.handlers if hasattr(app, 'handlers') else app._handlers if hasattr(app, '_handlers') else []
        assert len(handlers) > 0


class TestBotCommandIntegration:
    def test_start_command_via_handler(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="start")
        assert len(response) > 0
        assert "v4.0" in response or "analysis" in response.lower()

    def test_analysis_command_via_handler(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        response = handler.handle_command(chat_id=12345, command="analysis")
        assert "请发送" in response

    def test_full_flow_commands(self):
        sm = SessionManager()
        handler = TGBotHandler(sm)

        r = handler.handle_command(chat_id=12345, command="analysis")
        assert "请发送" in r

        handler.handle_message(chat_id=12345, text="安史之乱的多维度分析")
        r = handler.handle_message(chat_id=12345, text="开始分析")
        assert "分析" in r or "提取" in r

        r = handler.handle_command(chat_id=12345, command="status")
        assert "提取" in r or "主主题" in r

        r = handler.handle_command(chat_id=12345, command="close")
        assert "还不能" in r  # Not completed yet
