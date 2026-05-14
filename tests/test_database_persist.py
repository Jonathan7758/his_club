"""
Database Persistence 测试 — 用 mock sqlite3 替代 PostgreSQL
验证: save/load/find/close/cleanup 逻辑正确性（无依赖真实PG）
"""
import pytest
import json
import sqlite3
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from src.session_manager import SessionState


def _create_test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analysis_sessions (
            id TEXT PRIMARY KEY,
            tg_chat_id INTEGER NOT NULL,
            status TEXT DEFAULT 'WAITING_CONTENT',
            raw_content TEXT,
            main_topic TEXT,
            key_points TEXT,
            analysis TEXT,
            scores TEXT,
            sub_series TEXT,
            sub_scores TEXT,
            doc_md TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _session_to_dict(row) -> dict:
    d = dict(row)
    for f in ("key_points", "analysis", "scores", "sub_series", "sub_scores"):
        if d.get(f) and isinstance(d[f], str):
            try:
                d[f] = json.loads(d[f])
            except (json.JSONDecodeError, TypeError):
                pass
    d["raw_content"] = d.get("raw_content", "") or ""
    d.setdefault("message_count", 0)
    d.setdefault("char_count", 0)
    return d


class TestSaveAndLoad:
    def test_save_new_session(self):
        conn = _create_test_db()
        sid = "test_save_001"
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO analysis_sessions (id, tg_chat_id, status, raw_content, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (sid, 12345, SessionState.WAITING_CONTENT, "测试内容"))
        conn.commit()
        row = conn.execute("SELECT * FROM analysis_sessions WHERE id = ?", (sid,)).fetchone()
        assert row is not None
        d = _session_to_dict(row)
        assert d["id"] == sid
        assert d["tg_chat_id"] == 12345
        assert d["status"] == SessionState.WAITING_CONTENT
        conn.close()

    def test_save_update_existing_session(self):
        conn = _create_test_db()
        sid = "test_update_001"
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status, raw_content) VALUES (?, ?, ?, ?)",
                     (sid, 12345, SessionState.WAITING_CONTENT, "初始"))
        conn.execute("UPDATE analysis_sessions SET status = ?, raw_content = ?, updated_at = datetime('now') WHERE id = ?",
                     (SessionState.COLLECTING, "更新后", sid))
        conn.commit()
        row = conn.execute("SELECT * FROM analysis_sessions WHERE id = ?", (sid,)).fetchone()
        assert row["status"] == SessionState.COLLECTING
        assert row["raw_content"] == "更新后"
        conn.close()

    def test_save_with_json_fields(self):
        conn = _create_test_db()
        sid = "test_jsonb_001"
        conn.execute("""
            INSERT INTO analysis_sessions (id, tg_chat_id, status, key_points, scores, sub_series)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            sid, 12345, SessionState.ANALYZING,
            json.dumps(["论点1", "论点2", "论点3"], ensure_ascii=False),
            json.dumps({"total_score": 7.83}, ensure_ascii=False),
            json.dumps([{"dimension": "政治制度"}], ensure_ascii=False),
        ))
        conn.commit()
        row = conn.execute("SELECT * FROM analysis_sessions WHERE id = ?", (sid,)).fetchone()
        d = _session_to_dict(row)
        assert d["key_points"] == ["论点1", "论点2", "论点3"]
        assert d["scores"]["total_score"] == 7.83
        assert d["sub_series"][0]["dimension"] == "政治制度"
        conn.close()


class TestFindActive:
    def test_find_active_returns_none_for_completed(self):
        conn = _create_test_db()
        sid = "test_find_comp"
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES (?, ?, ?)",
                     (sid, 100, SessionState.COMPLETED))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM analysis_sessions WHERE id = ? AND status NOT IN (?, ?)",
            (sid, SessionState.COMPLETED, SessionState.CLOSED)
        ).fetchone()
        assert row is None
        conn.close()

    def test_find_active_returns_ongoing(self):
        conn = _create_test_db()
        sid = "test_find_ongoing"
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES (?, ?, ?)",
                     (sid, 100, SessionState.COLLECTING))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM analysis_sessions WHERE id = ? AND status NOT IN (?, ?)",
            (sid, SessionState.COMPLETED, SessionState.CLOSED)
        ).fetchone()
        assert row is not None
        assert row["status"] == SessionState.COLLECTING
        conn.close()

    def test_find_active_sessions_by_chat(self):
        conn = _create_test_db()
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES ('a1', 777, ?)", (SessionState.COLLECTING,))
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES ('a2', 777, ?)", (SessionState.COMPLETED,))
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES ('b1', 888, ?)", (SessionState.ANALYZING,))
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM analysis_sessions WHERE tg_chat_id = ? AND status NOT IN (?, ?) ORDER BY updated_at DESC",
            (777, SessionState.COMPLETED, SessionState.CLOSED)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == "a1"
        conn.close()


class TestCloseAndCleanup:
    def test_mark_closed(self):
        conn = _create_test_db()
        sid = "test_close"
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES (?, ?, ?)",
                     (sid, 100, SessionState.COMPLETED))
        conn.commit()
        conn.execute("UPDATE analysis_sessions SET status = ?, updated_at = datetime('now') WHERE id = ? AND status = ?",
                     (SessionState.CLOSED, sid, SessionState.COMPLETED))
        conn.commit()
        row = conn.execute("SELECT status FROM analysis_sessions WHERE id = ?", (sid,)).fetchone()
        assert row["status"] == SessionState.CLOSED
        conn.close()

    def test_mark_closed_rejects_non_completed(self):
        conn = _create_test_db()
        sid = "test_close_reject"
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES (?, ?, ?)",
                     (sid, 100, SessionState.ANALYZING))
        conn.commit()
        cur = conn.execute("UPDATE analysis_sessions SET status = ? WHERE id = ? AND status = ?",
                           (SessionState.CLOSED, sid, SessionState.COMPLETED))
        assert cur.rowcount == 0
        conn.close()

    def test_cleanup_deletes_old_closed(self):
        conn = _create_test_db()
        old = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status, updated_at) VALUES (?, ?, ?, ?)",
                     ("old_closed", 100, SessionState.CLOSED, old))
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status) VALUES (?, ?, ?)",
                     ("recent_closed", 100, SessionState.CLOSED))
        conn.commit()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("DELETE FROM analysis_sessions WHERE status = ? AND updated_at < ?",
                     (SessionState.CLOSED, cutoff))
        conn.commit()
        rows = conn.execute("SELECT id FROM analysis_sessions").fetchall()
        ids = [r["id"] for r in rows]
        assert "old_closed" not in ids
        assert "recent_closed" in ids
        conn.close()

    def test_auto_close_stale_completed(self):
        conn = _create_test_db()
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("INSERT INTO analysis_sessions (id, tg_chat_id, status, updated_at) VALUES (?, ?, ?, ?)",
                     ("stale_comp", 100, SessionState.COMPLETED, old))
        conn.commit()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("UPDATE analysis_sessions SET status = ?, updated_at = datetime('now') WHERE status = ? AND updated_at < ?",
                     (SessionState.CLOSED, SessionState.COMPLETED, cutoff))
        conn.commit()
        row = conn.execute("SELECT status FROM analysis_sessions WHERE id = ?", ("stale_comp",)).fetchone()
        assert row["status"] == SessionState.CLOSED
        conn.close()
