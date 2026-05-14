"""
Session状态机 v4.0
管理TG用户的完整分析会话生命周期
状态: WAITING_CONTENT → COLLECTING → SUMMARIZING → ANALYZING
    → CONFIRM_SCORE → DESIGNING → CONFIRM_DESIGN → SUB_SCORING → COMPLETED
"""
import uuid
import hashlib
from enum import Enum
from datetime import datetime, timezone


class SessionState(str, Enum):
    WAITING_CONTENT = "WAITING_CONTENT"
    COLLECTING = "COLLECTING"
    SUMMARIZING = "SUMMARIZING"
    ANALYZING = "ANALYZING"
    CONFIRM_SCORE = "CONFIRM_SCORE"
    DESIGNING = "DESIGNING"
    CONFIRM_DESIGN = "CONFIRM_DESIGN"
    SUB_SCORING = "SUB_SCORING"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


CONTENT_ACCEPTING_STATES = {SessionState.WAITING_CONTENT, SessionState.COLLECTING}


class SessionManager:
    def __init__(self, db=None):
        self.sessions = {}
        self.db = db

    def _new_id(self) -> str:
        raw = str(uuid.uuid4())
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_db_data(self, s: dict) -> dict:
        return {
            "id": s["id"],
            "tg_chat_id": s["tg_chat_id"],
            "status": s["status"],
            "raw_content": s.get("content", ""),
            "main_topic": s.get("main_topic"),
            "key_points": s.get("key_points") or [],
            "scores": s.get("scores"),
            "sub_series": s.get("sub_series"),
            "sub_scores": s.get("sub_scores"),
            "doc_md": s.get("doc_md"),
        }

    def _autosave(self, s: dict):
        if self.db and hasattr(self.db, "save_analysis_session"):
            try:
                self.db.save_analysis_session(self._build_db_data(s))
            except Exception:
                pass

    def create_session(self, tg_chat_id: int) -> dict:
        sid = self._new_id()
        session = {
            "id": sid,
            "tg_chat_id": tg_chat_id,
            "status": SessionState.WAITING_CONTENT,
            "content": "",
            "message_count": 0,
            "char_count": 0,
            "main_topic": None,
            "key_points": None,
            "scores": None,
            "sub_series": None,
            "sub_scores": None,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self.sessions[sid] = session
        self._autosave(session)
        return dict(session)

    def get_session(self, session_id: str) -> dict | None:
        s = self.sessions.get(session_id)
        if s:
            return dict(s)
        return self.restore_session(session_id)

    def add_content(self, session_id: str, content: str) -> dict:
        s = self.sessions[session_id]

        if s["status"] not in CONTENT_ACCEPTING_STATES:
            raise ValueError(f"不能添加内容，当前状态: {s['status']}")

        s["content"] += content
        s["message_count"] += 1
        s["char_count"] = len(s["content"])
        s["status"] = SessionState.COLLECTING
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def trigger_analysis(self, session_id: str) -> dict:
        s = self.sessions[session_id]

        if not s["content"].strip():
            raise ValueError("没有内容可分析")

        if s["status"] not in CONTENT_ACCEPTING_STATES:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["status"] = SessionState.SUMMARIZING
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def set_main_topic(self, session_id: str, topic: str, key_points: list[str]) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.SUMMARIZING:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["main_topic"] = topic
        s["key_points"] = key_points
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def confirm_topic(self, session_id: str) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.SUMMARIZING:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        if not s["main_topic"]:
            raise ValueError("尚未设置主主题")

        s["status"] = SessionState.ANALYZING
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def set_scores(self, session_id: str, scores: dict) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.ANALYZING:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["scores"] = scores
        s["status"] = SessionState.CONFIRM_SCORE
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def confirm_score(self, session_id: str) -> dict:
        s = self.sessions[session_id]

        if not s["scores"]:
            raise ValueError("尚未设置评分")

        if s["status"] != SessionState.CONFIRM_SCORE:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["status"] = SessionState.DESIGNING
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def set_sub_series(self, session_id: str, sub_series: list[dict]) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.DESIGNING:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["sub_series"] = sub_series
        s["status"] = SessionState.CONFIRM_DESIGN
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def confirm_design(self, session_id: str) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.CONFIRM_DESIGN:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["status"] = SessionState.SUB_SCORING
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def set_sub_scores(self, session_id: str, sub_scores: list[dict]) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.SUB_SCORING:
            raise ValueError(f"不允许的操作，当前状态: {s['status']}")

        s["sub_scores"] = sub_scores
        s["status"] = SessionState.COMPLETED
        s["updated_at"] = self._now()

        self._autosave(s)
        return dict(s)

    def is_doc_ready(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if not s:
            return False
        return s["status"] == SessionState.COMPLETED

    def close_session(self, session_id: str) -> dict:
        s = self.sessions[session_id]

        if s["status"] != SessionState.COMPLETED:
            raise ValueError(f"只能关闭 COMPLETED 状态的 session，当前: {s['status']}")

        s["status"] = SessionState.CLOSED
        s["updated_at"] = self._now()

        self._autosave(s)
        if self.db and hasattr(self.db, "mark_session_closed"):
            try:
                self.db.mark_session_closed(session_id)
            except Exception:
                pass

        return dict(s)

    def restore_session(self, session_id: str) -> dict | None:
        if not self.db or not hasattr(self.db, "load_analysis_session"):
            return None
        try:
            db = self.db.load_analysis_session(session_id)
            if not db:
                return None

            session = {
                "id": db["id"],
                "tg_chat_id": db.get("tg_chat_id", 0),
                "status": db.get("status", SessionState.WAITING_CONTENT),
                "content": db.get("content", ""),
                "message_count": db.get("message_count", 0),
                "char_count": db.get("char_count", 0),
                "main_topic": db.get("main_topic"),
                "key_points": db.get("key_points"),
                "scores": db.get("scores"),
                "sub_series": db.get("sub_series"),
                "sub_scores": db.get("sub_scores"),
                "created_at": db.get("created_at", self._now()),
                "updated_at": db.get("updated_at", self._now()),
            }
            self.sessions[session_id] = session
            return dict(session)
        except Exception:
            return None

    def find_active_by_chat(self, tg_chat_id: int) -> list[dict]:
        if not self.db or not hasattr(self.db, "find_active_sessions_by_chat"):
            return []
        try:
            return self.db.find_active_sessions_by_chat(tg_chat_id)
        except Exception:
            return []

    def has_active_session(self, tg_chat_id: int) -> bool:
        return len(self.find_active_by_chat(tg_chat_id)) > 0

    def restart(self, session_id: str) -> dict:
        """重置session到初始状态但保留ID和tg_chat_id"""
        s = self.sessions[session_id]
        tg_chat_id = s["tg_chat_id"]

        s.update({
            "status": SessionState.WAITING_CONTENT,
            "content": "",
            "message_count": 0,
            "char_count": 0,
            "main_topic": None,
            "key_points": None,
            "scores": None,
            "sub_series": None,
            "sub_scores": None,
            "updated_at": self._now(),
        })

        return dict(s)

    def split_long_content(self, content: str, max_len: int = 4096) -> list[str]:
        """将超长内容拆分为多个chunk"""
        if len(content) <= max_len:
            return [content]

        chunks = []
        for i in range(0, len(content), max_len):
            chunks.append(content[i:i + max_len])
        return chunks
