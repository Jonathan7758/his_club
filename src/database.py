"""
数据存储层 v1.0
PostgreSQL持久化 — 热点/话题/帖子/评论/生成结果
"""
import json
import os
from datetime import datetime, timezone
import hashlib

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "bettafish"),
    "user": os.getenv("DB_USER", "bettafish"),
    "password": os.getenv("DB_PASS", "bettafish")
}

import psycopg2
import psycopg2.extras

psycopg2.extras.register_uuid()


def _get_conn():
    return psycopg2.connect(**DB_CONFIG)


def _hash_id(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


def init_db():
    """初始化全部表结构"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hot_topics (
            id VARCHAR(16) PRIMARY KEY,
            topic TEXT NOT NULL,
            source_platform TEXT,
            heat_score REAL DEFAULT 0,
            relevance TEXT,
            topic_type TEXT DEFAULT 'scan',
            window_type TEXT DEFAULT 'daily',
            raw_data JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS posts (
            id VARCHAR(16) PRIMARY KEY,
            topic_id VARCHAR(16) REFERENCES hot_topics(id),
            platform TEXT,
            title TEXT,
            content TEXT,
            url TEXT,
            author TEXT,
            published_at TIMESTAMPTZ,
            engagement JSONB DEFAULT '{}',
            raw_data JSONB DEFAULT '{}',
            fetched_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS comments (
            id VARCHAR(16) PRIMARY KEY,
            post_id VARCHAR(16) REFERENCES posts(id),
            platform TEXT,
            author TEXT,
            content TEXT,
            likes INTEGER DEFAULT 0,
            parent_id VARCHAR(16),
            sentiment JSONB DEFAULT '{}',
            published_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS sentiment_labels (
            id VARCHAR(16) PRIMARY KEY,
            target_type TEXT,
            target_id VARCHAR(16),
            label TEXT,
            score REAL,
            source TEXT,
            model_version TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS entity_relations (
            id VARCHAR(16) PRIMARY KEY,
            source_entity TEXT,
            relation TEXT,
            target_entity TEXT,
            context TEXT,
            confidence REAL DEFAULT 0.5,
            extracted_from TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS generations (
            id VARCHAR(16) PRIMARY KEY,
            topic TEXT NOT NULL,
            request_type TEXT DEFAULT 'full',
            angles JSONB,
            article JSONB,
            video_script JSONB,
            fact_check JSONB,
            hot_scan JSONB,
            meta JSONB,
            cost_estimate REAL DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS analysis_sessions (
            id VARCHAR(16) PRIMARY KEY,
            tg_chat_id BIGINT NOT NULL,
            status VARCHAR(20) DEFAULT 'WAITING_CONTENT',
            raw_content TEXT,
            main_topic TEXT,
            key_points JSONB,
            analysis JSONB,
            scores JSONB,
            sub_series JSONB,
            sub_scores JSONB,
            doc_md TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS series_designs (
            id VARCHAR(16) PRIMARY KEY,
            session_id VARCHAR(16) REFERENCES analysis_sessions(id),
            main_topic TEXT NOT NULL,
            sub_topics JSONB NOT NULL,
            full_doc_md TEXT,
            full_doc_json JSONB,
            exported_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_hot_topics_created ON hot_topics(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_hot_topics_window ON hot_topics(window_type, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic_id);
        CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform, fetched_at DESC);
        CREATE INDEX IF NOT EXISTS idx_generations_topic ON generations(topic, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_entity_relations_source ON entity_relations(source_entity);
        CREATE INDEX IF NOT EXISTS idx_entity_relations_target ON entity_relations(target_entity);
        CREATE INDEX IF NOT EXISTS idx_sentiment_target ON sentiment_labels(target_type, target_id);
    """)
    conn.commit()
    cur.close()
    conn.close()
    return True


def save_hotspot_scan(scan_result: dict, window_type: str = "daily") -> int:
    """保存热点扫描结果到 hot_topics 表"""
    conn = _get_conn()
    cur = conn.cursor()
    count = 0
    topics = scan_result.get("history_topics", [])

    for t in topics:
        tid = _hash_id(f"{t.get('topic','')}-{window_type}-{datetime.now().strftime('%Y%m%d')}")
        try:
            cur.execute("""
                INSERT INTO hot_topics (id, topic, source_platform, heat_score, relevance, topic_type, window_type, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET heat_score = EXCLUDED.heat_score
            """, (
                tid,
                t.get("topic", "")[:200],
                t.get("source_platform", "unknown"),
                float(t.get("score", 0)),
                t.get("relevance", "")[:200],
                "scan",
                window_type,
                json.dumps(t, ensure_ascii=False)
            ))
            count += 1
        except Exception as e:
            print(f"  DB save error for {t.get('topic', '?')}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    return count


def save_generation(topic: str, result: dict) -> str:
    """保存完整生成结果"""
    gen_id = _hash_id(f"{topic}-{datetime.now().isoformat()}")
    conn = _get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO generations (id, topic, request_type, angles, article, video_script, fact_check, hot_scan, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                angles = EXCLUDED.angles,
                article = EXCLUDED.article,
                fact_check = EXCLUDED.fact_check,
                meta = EXCLUDED.meta
        """, (
            gen_id,
            topic,
            "full",
            json.dumps(result.get("angles", []), ensure_ascii=False),
            json.dumps(result.get("article", {}), ensure_ascii=False),
            json.dumps(result.get("video_script", {}), ensure_ascii=False),
            json.dumps(result.get("fact_check", {}), ensure_ascii=False),
            json.dumps(result.get("hot_scan", {}), ensure_ascii=False),
            json.dumps(result.get("meta", {}), ensure_ascii=False)
        ))
        conn.commit()
    except Exception as e:
        print(f"  DB save error for generation '{topic}': {e}")
    finally:
        cur.close()
        conn.close()

    return gen_id


def get_recent_hotspots(days: int = 7, limit: int = 20) -> list[dict]:
    """查询近N天的热点话题"""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT topic, source_platform, heat_score, relevance, window_type, created_at
        FROM hot_topics
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        ORDER BY heat_score DESC
        LIMIT %s
    """, (days, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_topic_history(topic: str, limit: int = 5) -> list[dict]:
    """查询某话题的历史生成记录"""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, topic, meta, fact_check, created_at
        FROM generations
        WHERE topic ILIKE %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (f"%{topic}%", limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_hotspot_trends(days: int = 30) -> dict:
    """获取热点趋势统计"""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            DATE(created_at) as day,
            COUNT(*) as topic_count,
            ROUND(AVG(heat_score)::numeric, 1) as avg_score,
            MAX(heat_score) as max_score
        FROM hot_topics
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        GROUP BY DATE(created_at)
        ORDER BY day
    """, (days,))
    daily_stats = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT source_platform, COUNT(*) as cnt, ROUND(AVG(heat_score)::numeric, 1) as avg_score
        FROM hot_topics
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        GROUP BY source_platform
        ORDER BY cnt DESC
    """, (days,))
    platform_stats = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT topic, count(*) as gen_count
        FROM generations
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        GROUP BY topic
        ORDER BY gen_count DESC
        LIMIT 10
    """, (days,))
    top_generated = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "daily_stats": daily_stats,
        "platform_distribution": platform_stats,
        "top_generated_topics": top_generated,
        "period_days": days
    }


def save_post(post_data: dict, topic_id: str = None) -> str:
    """保存原始帖子"""
    post_id = _hash_id(f"{post_data.get('platform','')}-{post_data.get('title','')}-{post_data.get('url','')}")
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO posts (id, topic_id, platform, title, content, url, author, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
            post_id,
            topic_id,
            post_data.get("platform", "unknown"),
            post_data.get("title", "")[:500],
            post_data.get("content", "")[:5000],
            post_data.get("url", ""),
            post_data.get("author", ""),
            json.dumps(post_data, ensure_ascii=False)
        ))
        conn.commit()
    except Exception as e:
        print(f"  DB save error for post: {e}")
    finally:
        cur.close()
        conn.close()
    return post_id


def save_posts_batch(posts_data: list[dict], topic_id: str = None) -> int:
    """批量保存帖子"""
    count = 0
    for p in posts_data:
        pid = save_post(p, topic_id)
        if pid:
            count += 1
    return count


def save_comment(comment_data: dict) -> str:
    """保存单条评论到 comments 表"""
    comment_id = _hash_id(
        f"{comment_data.get('platform','')}-{comment_data.get('author','')}-"
        f"{comment_data.get('content','')[:100]}-{comment_data.get('published_at','')}"
    )
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO comments (id, post_id, platform, author, content, likes, parent_id, sentiment, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
            comment_id,
            comment_data.get("post_id") or None,
            comment_data.get("platform", "unknown"),
            (comment_data.get("author") or "")[:100],
            (comment_data.get("content") or "")[:5000],
            int(comment_data.get("likes", 0)),
            comment_data.get("parent_id") or None,
            json.dumps(comment_data.get("sentiment", {}), ensure_ascii=False),
            comment_data.get("published_at")
        ))
        conn.commit()
    except Exception as e:
        print(f"  DB save error for comment: {e}")
        comment_id = None
    finally:
        cur.close()
        conn.close()
    return comment_id


def save_comments_batch(comments: list[dict]) -> int:
    """批量保存评论"""
    count = 0
    for c in comments:
        cid = save_comment(c)
        if cid:
            count += 1
    return count


def save_entity_relations(relations: list[dict], extracted_from: str = "generation") -> int:
    """批量保存实体关系"""
    conn = _get_conn()
    cur = conn.cursor()
    count = 0
    for r in relations:
        rid = _hash_id(f"{r.get('source_entity','')}-{r.get('relation','')}-{r.get('target_entity','')}-{extracted_from}")
        try:
            cur.execute("""
                INSERT INTO entity_relations (id, source_entity, relation, target_entity, context, confidence, extracted_from)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET confidence = EXCLUDED.confidence
            """, (
                rid,
                r.get("source_entity", "")[:200],
                r.get("relation", "")[:100],
                r.get("target_entity", "")[:200],
                r.get("context", "")[:500],
                float(r.get("confidence", 0.5)),
                extracted_from
            ))
            count += 1
        except Exception as e:
            print(f"  DB save error for relation: {e}")
    conn.commit()
    cur.close()
    conn.close()
    return count


def save_sentiment_labels(labels: list[dict]) -> int:
    """批量保存情感标签"""
    conn = _get_conn()
    cur = conn.cursor()
    count = 0
    for s in labels:
        sid = _hash_id(f"{s.get('target_type','')}-{s.get('target_id','')}-{s.get('label','')}")
        try:
            cur.execute("""
                INSERT INTO sentiment_labels (id, target_type, target_id, label, score, source, model_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET score = EXCLUDED.score
            """, (
                sid,
                s.get("target_type", "unknown")[:50],
                s.get("target_id", "")[:16],
                s.get("label", "")[:50],
                float(s.get("score", 0)),
                s.get("source", "llm"),
                "v1.0"
            ))
            count += 1
        except Exception as e:
            print(f"  DB save error for sentiment: {e}")
    conn.commit()
    cur.close()
    conn.close()
    return count


def link_posts_to_topics(topic_keywords: list[tuple]) -> int:
    """根据关键词将 posts 关联到 hot_topics"""
    conn = _get_conn()
    cur = conn.cursor()
    count = 0
    for tid, keyword in topic_keywords:
        try:
            cur.execute("""
                UPDATE posts SET topic_id = %s
                WHERE topic_id IS NULL AND (title ILIKE %s OR raw_data::text ILIKE %s)
            """, (tid, f"%{keyword}%", f"%{keyword}%"))
            count += cur.rowcount
        except:
            pass
    conn.commit()
    cur.close()
    conn.close()
    return count


def get_comments_for_post(post_id: str, limit: int = 50) -> list[dict]:
    """查询某帖子下的评论"""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, post_id, platform, author, content, likes, sentiment, published_at, fetched_at
        FROM comments
        WHERE post_id = %s
        ORDER BY likes DESC, published_at DESC
        LIMIT %s
    """, (post_id, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_comments_stats(days: int = 7) -> dict:
    """评论数据概览统计"""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT count(*) FROM comments")
    total_comments = cur.fetchone()["count"]
    cur.execute("""
        SELECT platform, count(*) as cnt, round(avg(likes)::numeric, 1) as avg_likes
        FROM comments
        WHERE fetched_at >= NOW() - (%s * INTERVAL '1 day')
        GROUP BY platform
        ORDER BY cnt DESC
    """, (days,))
    platform_stats = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return {"total_comments": total_comments, "platform_distribution": platform_stats, "period_days": days}


def save_analysis_session(session_data: dict) -> str:
    s = session_data
    sid = s.get("id", "")
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO analysis_sessions (id, tg_chat_id, status, raw_content, main_topic, key_points, analysis, scores, sub_series, sub_scores, doc_md, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                raw_content = EXCLUDED.raw_content,
                main_topic = EXCLUDED.main_topic,
                key_points = EXCLUDED.key_points,
                analysis = EXCLUDED.analysis,
                scores = EXCLUDED.scores,
                sub_series = EXCLUDED.sub_series,
                sub_scores = EXCLUDED.sub_scores,
                doc_md = EXCLUDED.doc_md,
                updated_at = NOW()
        """, (
            sid,
            s.get("tg_chat_id", 0),
            s.get("status", "WAITING_CONTENT"),
            s.get("raw_content") or s.get("content"),
            s.get("main_topic"),
            json.dumps(s.get("key_points"), ensure_ascii=False) if s.get("key_points") else None,
            json.dumps(s.get("analysis"), ensure_ascii=False) if s.get("analysis") else None,
            json.dumps(s.get("scores"), ensure_ascii=False) if s.get("scores") else None,
            json.dumps(s.get("sub_series"), ensure_ascii=False) if s.get("sub_series") else None,
            json.dumps(s.get("sub_scores"), ensure_ascii=False) if s.get("sub_scores") else None,
            s.get("doc_md"),
        ))
        conn.commit()
    except Exception as e:
        print(f"DB save error for session {sid}: {e}")
    finally:
        cur.close()
        conn.close()
    return sid


def load_analysis_session(session_id: str) -> dict | None:
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM analysis_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        data = dict(row)
        for json_field in ("key_points", "analysis", "scores", "sub_series", "sub_scores"):
            if data.get(json_field) and isinstance(data[json_field], str):
                try:
                    data[json_field] = json.loads(data[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        data["raw_content"] = data.get("raw_content", "")
        data["content"] = data["raw_content"]
        data["message_count"] = data.get("message_count", 0)
        data["char_count"] = len(data.get("raw_content", ""))
        return data
    except Exception as e:
        print(f"DB load error for session {session_id}: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def find_active_session(session_id: str) -> dict | None:
    result = load_analysis_session(session_id)
    if result and result.get("status") not in (SessionState.COMPLETED, SessionState.CLOSED):
        return result
    return None


def find_active_sessions_by_chat(tg_chat_id: int) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM analysis_sessions
            WHERE tg_chat_id = %s
            AND status NOT IN (%s, %s)
            ORDER BY updated_at DESC
        """, (tg_chat_id, SessionState.COMPLETED, SessionState.CLOSED))
        rows = cur.fetchall()
        results = []
        for row in rows:
            data = dict(row)
            for json_field in ("key_points", "analysis", "scores", "sub_series", "sub_scores"):
                if data.get(json_field) and isinstance(data[json_field], str):
                    try:
                        data[json_field] = json.loads(data[json_field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            results.append(data)
        return results
    except Exception as e:
        print(f"DB find active error for chat {tg_chat_id}: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def mark_session_closed(session_id: str) -> None:
    session = load_analysis_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    if session["status"] != SessionState.COMPLETED:
        raise ValueError(f"只能关闭 COMPLETED 状态的 session，当前: {session['status']}")

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE analysis_sessions SET status = %s, updated_at = NOW() WHERE id = %s
        """, (SessionState.CLOSED, session_id))
        conn.commit()
    except Exception as e:
        print(f"DB close error for session {session_id}: {e}")
    finally:
        cur.close()
        conn.close()


def cleanup_expired_sessions(days: int = 7) -> int:
    from datetime import timezone

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, status, updated_at FROM analysis_sessions
            WHERE status IN (%s, %s)
            AND updated_at < NOW() - (%s * INTERVAL '1 day')
        """, (SessionState.CLOSED, SessionState.COMPLETED, days))

        expired = cur.fetchall()
        ids_to_delete = []
        ids_to_close = []

        for row in expired:
            sid, status, updated_at = row
            if status == SessionState.CLOSED:
                ids_to_delete.append(sid)
            elif status == SessionState.COMPLETED:
                ids_to_close.append(sid)

        count = 0

        for sid in ids_to_close:
            cur.execute("""
                UPDATE analysis_sessions SET status = %s, updated_at = NOW() WHERE id = %s
            """, (SessionState.CLOSED, sid))
            count += cur.rowcount

        for sid in ids_to_delete:
            cur.execute("DELETE FROM analysis_sessions WHERE id = %s", (sid,))
            count += cur.rowcount

        conn.commit()
        return count
    except Exception as e:
        print(f"DB cleanup error: {e}")
        return 0
    finally:
        cur.close()
        conn.close()


# Import at bottom to avoid circular — needed by save_analysis_session et al.
from session_manager import SessionState

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Done. Tables created.")

    print("\nGetting recent hotspots (last 7 days)...")
    hotspots = get_recent_hotspots(7)
    print(json.dumps(hotspots, ensure_ascii=False, indent=2, default=str))

    print("\nGetting trends...")
    trends = get_hotspot_trends(7)
    print(json.dumps(trends, ensure_ascii=False, indent=2, default=str))
