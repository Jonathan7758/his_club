"""
History Series Analysis API v4.0
TG驱动的系列分析引擎 — 保留监控/图谱/分析端点，移除生成类端点，新增TG webhook
"""
import os
import sys
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

_script_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _parent_dir)
sys.path.insert(0, _script_dir)
from env_loader import load_env
load_env()


def create_app(session_manager=None, tg_handler=None):
    app = FastAPI(title="History Series Analysis API v4.0")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "version": "4.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/tg/webhook")
    async def tg_webhook(request: Request):
        if tg_handler is None:
            return JSONResponse({"status": "error", "detail": "TG handler not configured"}, status_code=500)

        try:
            body = await request.json()
        except Exception:
            return {"status": "error", "detail": "Invalid JSON"}

        message = body.get("message", {})
        if not message:
            return {"status": "error", "detail": "No message field"}

        chat = message.get("chat", {})
        chat_id = chat.get("id") if chat else None
        text = message.get("text", "")

        if not chat_id or not text:
            return {"status": "error", "detail": "Missing chat_id or text"}

        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0]
            reply = tg_handler.handle_command(chat_id, cmd, parts[1] if len(parts) > 1 else "")
        else:
            reply = tg_handler.handle_message(chat_id, text)

        return {"status": "ok", "reply": reply}

    @app.get("/monitor/health")
    def monitor_health():
        return {"status": "ok", "version": "4.0"}

    @app.get("/monitor/errors")
    def monitor_errors():
        return {"errors": []}

    @app.post("/monitor/cleanup")
    def monitor_cleanup():
        return {"status": "ok", "cleaned": 0}

    @app.get("/analyze/{topic}")
    def analyze_topic(topic: str):
        return {"topic": topic, "status": "analysis endpoint reserved"}

    @app.get("/engines/analyze/{topic}")
    def engines_analyze(topic: str):
        return {"topic": topic, "status": "engines endpoint reserved"}

    @app.get("/graph/stats")
    def graph_stats():
        return {"status": "ok"}

    @app.get("/graph/centrality")
    def graph_centrality():
        return {"entities": []}

    @app.get("/graph/clusters")
    def graph_clusters():
        return {"clusters": []}

    @app.get("/graph/gaps")
    def graph_gaps():
        return {"gaps": []}

    @app.post("/analytics/diagnose")
    async def analytics_diagnose(request: Request):
        body = await request.json()
        return {"diagnosis": "reserved", "input_received": len(str(body))}

    @app.post("/analytics/diagnose/url")
    async def analytics_diagnose_url(request: Request):
        body = await request.json()
        return {"diagnosis": "reserved", "url": body.get("url", "")}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
