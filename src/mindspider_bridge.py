"""
MindSpider 桥接模块 v2.0
同步 BettaFish/MindSpider 爬取数据到本系统 posts/comments 表
支持多平台: 知乎/B站/微博/小红书/抖音/快手/贴吧

v2.0: 评论正确路由到 comments 表，建立 post_id 外键映射
"""
import json
import os
import sys
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import save_post, save_comment, _hash_id, _get_conn
import psycopg2.extras

# MindSpider 源表 → (平台名, 内容字段, 输出列)
SOURCE_TABLES = {
    "daily_news": ("news", "description", ["title", "description", "url", "source_platform"]),
    "zhihu_content": ("zhihu", "content_text", ["title", "content_text", "url", "author_name"]),
    "zhihu_comment": ("zhihu_comment", "content", ["content", "author_name"]),
    "weibo_note": ("weibo", "content", ["title", "content", "url", "author"]),
    "weibo_note_comment": ("weibo_comment", "content", ["content", "author"]),
    "bilibili_video": ("bilibili", "description", ["title", "description", "url"]),
    "bilibili_video_comment": ("bilibili_comment", "content", ["content", "author"]),
    "xhs_note": ("xiaohongshu", "content", ["title", "content", "url"]),
    "xhs_note_comment": ("xiaohongshu_comment", "content", ["content", "author"]),
    "douyin_aweme": ("douyin", "desc", ["desc", "url"]),
    "douyin_aweme_comment": ("douyin_comment", "content", ["content", "author"]),
    "kuaishou_video": ("kuaishou", "caption", ["caption", "url"]),
    "kuaishou_video_comment": ("kuaishou_comment", "content", ["content", "author"]),
    "tieba_note": ("tieba", "title", ["title", "content", "url"]),
    "tieba_comment": ("tieba_comment", "content", ["content", "author"]),
}

COMMENT_TABLES = {k for k in SOURCE_TABLES if k.endswith("_comment")}
CONTENT_TABLES = {k for k in SOURCE_TABLES if k not in COMMENT_TABLES}

# 评论表 → 对应的内容表（用于 post_id 关联）
COMMENT_TO_CONTENT = {
    "zhihu_comment": "zhihu_content",
    "weibo_note_comment": "weibo_note",
    "bilibili_video_comment": "bilibili_video",
    "xhs_note_comment": "xhs_note",
    "douyin_aweme_comment": "douyin_aweme",
    "kuaishou_video_comment": "kuaishou_video",
    "tieba_comment": "tieba_note",
}

# 评论表中可能的父级 ID 列名（按优先级）
_PARENT_ID_CANDIDATES = [
    "note_id", "content_id", "video_id", "aweme_id",
    "answer_id", "article_id", "post_id", "parent_id",
    "thread_id", "topic_id"
]

HISTORY_KEYWORDS = [
    "历史", "古代", "朝代", "皇帝", "战争", "制度", "考古", "文物",
    "三国", "唐朝", "宋朝", "明朝", "清朝", "秦汉", "罗马", "革命",
    "变法", "改革", "起义", "帝国", "统一", "分裂", "理学", "儒家",
    "道家", "法家", "佛教", "道教", "丝路", "航海", "科举", "军事",
    "人物传", "大事记", "博物馆", "遗址", "古墓", "青铜", "瓷器",
]


def _is_history_related(text: str) -> bool:
    """简单关键词匹配判断是否历史相关"""
    if not text:
        return False
    text_lower = text.lower()
    for kw in HISTORY_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def _detect_parent_id(row: dict) -> str:
    """从评论行中检测父级内容 ID"""
    for col in _PARENT_ID_CANDIDATES:
        val = row.get(col)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _build_post_id(content_table: str, source_row_id) -> str:
    """构建与 save_post 一致的 post_id"""
    raw = f"mindspider-{content_table}-{source_row_id}"
    return _hash_id(raw)


def _serialize_row(row: dict) -> dict:
    """将数据库行中的 date/datetime/Decimal 转为 JSON 兼容类型"""
    from datetime import date, datetime
    from decimal import Decimal
    result = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            result[k] = str(v)
        elif isinstance(v, Decimal):
            result[k] = float(v)
        else:
            result[k] = v
    return result


def _parse_content_row(row: dict, table_name: str) -> dict:
    """将内容表行解析为 post 数据"""
    platform, content_field, fields = SOURCE_TABLES[table_name]
    content = row.get(content_field, "") or ""
    title = row.get(fields[0], "") if len(fields) > 0 else ""

    if not content and not title:
        return None
    if not _is_history_related(title or content):
        return None

    return {
        "platform": platform,
        "title": (title or "")[:500],
        "content": (content or "")[:5000],
        "url": row.get("url", "") or f"mindspider://{table_name}/{row.get('id','')}",
        "author": row.get(fields[-1], "") if len(fields) > 1 and "author" in fields[-1].lower() else "",
        "raw_data": _serialize_row(row),
    }


def _parse_comment_row(row: dict, table_name: str, post_id: str) -> dict:
    """将评论表行解析为 comment 数据"""
    platform, content_field, fields = SOURCE_TABLES[table_name]
    content = row.get(content_field, "") or ""

    if not content:
        return None
    if not _is_history_related(content):
        return None

    # 读取可能的 likes 值
    likes = 0
    for col in ["like_count", "likes", "digg_count", "upvote_count"]:
        v = row.get(col)
        if v is not None:
            try:
                likes = int(v)
                break
            except (ValueError, TypeError):
                pass

    # 读取可能的发布时间
    published_at = None
    for col in ["created_at", "create_time", "pub_time", "ctime"]:
        v = row.get(col)
        if v is not None:
            try:
                if isinstance(v, datetime):
                    published_at = v
                else:
                    published_at = str(v)
                break
            except:
                pass

    return {
        "post_id": post_id or None,
        "platform": platform,
        "author": (row.get(fields[-1], "") or "")[:100] if len(fields) > 1 else "",
        "content": (content or "")[:5000],
        "likes": likes,
        "parent_id": _detect_parent_id(row) or None,
        "sentiment": {},
        "published_at": published_at,
    }


def sync_mindspider_to_posts(batch_size: int = 100) -> dict:
    """
    两阶段同步:
      1. 内容表 → posts（建立 source_id → post_id 映射）
      2. 评论表 → comments（通过映射关联 post_id）
    """
    conn = _get_conn()
    stats = {
        "scanned_content_tables": 0,
        "scanned_comment_tables": 0,
        "posts_added": 0,
        "comments_added": 0,
        "history_rows": 0,
    }

    # Phase 1: sync content tables → posts, build post_id mapping
    post_id_map = {}  # (table_name, source_row_id) → our_post_id

    for table_name in CONTENT_TABLES:
        platform, _, _ = SOURCE_TABLES[table_name]
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {batch_size}")
            rows = cur.fetchall()
            cur.close()

            if not rows:
                continue

            stats["scanned_content_tables"] += 1

            for row in rows:
                try:
                    post_data = _parse_content_row(row, table_name)
                    if not post_data:
                        continue

                    # 使用与 save_post 相同的 ID 生成逻辑
                    source_row_id = row.get("id", "")
                    computed_id = _build_post_id(table_name, source_row_id)
                    post_data["_computed_id"] = computed_id

                    pid = save_post(post_data)
                    if pid:
                        stats["posts_added"] += 1
                        post_id_map[(table_name, str(source_row_id))] = computed_id
                        stats["history_rows"] += 1
                except:
                    pass

        except Exception as e:
            pass

    # Phase 2: sync comment tables → comments with post_id lookup
    for table_name in COMMENT_TABLES:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {batch_size}")
            rows = cur.fetchall()
            cur.close()

            if not rows:
                continue

            stats["scanned_comment_tables"] += 1

            content_table = COMMENT_TO_CONTENT.get(table_name, "")
            for row in rows:
                try:
                    parent_id = _detect_parent_id(row)
                    post_id = None

                    if content_table and parent_id:
                        post_id = post_id_map.get((content_table, parent_id))
                        if not post_id:
                            post_id = _build_post_id(content_table, parent_id)

                    comment_data = _parse_comment_row(row, table_name, post_id)
                    if not comment_data:
                        continue

                    cid = save_comment(comment_data)
                    if cid:
                        stats["comments_added"] += 1
                        stats["history_rows"] += 1
                except:
                    pass

        except Exception as e:
            pass

    conn.close()
    return stats


def trigger_mindspider_crawl(
    max_notes: int = 20,
    platforms: str = "zhihu,bilibili,weibo,xiaohongshu,douyin,kuaishou,tieba",
) -> bool:
    """触发 MindSpider 运行一次爬虫（如果可用）"""
    mindspider_dir = "/opt/hisclub/bettafish/MindSpider"
    if not os.path.isdir(mindspider_dir):
        print("[MindSpider] 目录不存在，跳过")
        return False

    import subprocess

    try:
        result = subprocess.run(
            [
                "python3", "main.py", "--broad-topic",
                "--max-notes", str(max_notes),
                "--platforms", *platforms.split(","),
            ],
            cwd=mindspider_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        print(f"[MindSpider] stdout: {result.stdout[-500:]}")
        if result.stderr:
            print(f"[MindSpider] stderr: {result.stderr[-200:]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("[MindSpider] 爬虫超时")
        return False
    except FileNotFoundError:
        print("[MindSpider] Python3 或 main.py 不可用")
        return False
    except Exception as e:
        print(f"[MindSpider] 错误: {e}")
        return False


def trigger_mindspider_deep(complete: bool = False) -> bool:
    """触发 MindSpider 大规模/完整爬取"""
    mindspider_dir = "/opt/hisclub/bettafish/MindSpider"
    if not os.path.isdir(mindspider_dir):
        print("[MindSpider] 目录不存在，跳过")
        return False

    import subprocess

    cmd = ["python3", "main.py", "--broad-topic"]
    if complete:
        cmd.append("--complete")
    else:
        cmd.extend(["--max-notes", "100"])

    try:
        result = subprocess.run(
            cmd,
            cwd=mindspider_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )
        print(f"[MindSpider Deep] stdout: {result.stdout[-500:]}")
        if result.stderr:
            print(f"[MindSpider Deep] stderr: {result.stderr[-200:]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("[MindSpider Deep] 爬虫超时")
        return False
    except Exception as e:
        print(f"[MindSpider Deep] 错误: {e}")
        return False


if __name__ == "__main__":
    print("=== MindSpider 桥接同步 v2.0 ===")
    stats = sync_mindspider_to_posts()
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n=== 触发 MindSpider 爬虫 (轻量) ===")
    success = trigger_mindspider_crawl()
    print(f"  爬虫启动: {'成功' if success else '失败'}")
