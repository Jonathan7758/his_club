"""
BettaFish 三引擎桥接 v1.0
将现有能力封装为 QueryEngine / MediaEngine / InsightEngine 接口
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def query_engine_search(topic: str, sources: int = 3) -> dict:
    """
    QueryEngine: 全网搜索整合
    多源并行搜索，返回聚合结果
    """
    results = {"topic": topic, "sources": {}}

    # 源1: 搜狗微信搜索
    try:
        from generator import _weixin_search
        wx = _weixin_search(topic, max_results=10)
        results["sources"]["wechat"] = [r for r in wx if r != "无公众号文章"][:5]
    except:
        results["sources"]["wechat"] = []

    # 源2: 搜狗网页搜索
    try:
        from generator import _sogou_web_search
        web = _sogou_web_search(topic, max_results=10)
        results["sources"]["web"] = web[:5]
    except:
        results["sources"]["web"] = []

    # 源3: 豆瓣书评搜索
    try:
        from douban import search_history_books
        books = search_history_books(topic, max_results=5)
        results["sources"]["douban_books"] = books
    except:
        results["sources"]["douban_books"] = []

    # 汇总
    total_hits = sum(len(v) for v in results["sources"].values())
    results["summary"] = {
        "total_results": total_hits,
        "wechat_count": len(results["sources"].get("wechat", [])),
        "web_count": len(results["sources"].get("web", [])),
        "douban_count": len(results["sources"].get("douban_books", [])),
    }

    return results


def media_engine_analyze(topic: str) -> dict:
    """
    MediaEngine: 多模态分析（轻量版）
    分析话题在视频平台的覆盖情况
    """
    from openai import OpenAI
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )

    prompt = f"""请分析历史话题《{topic}》在各媒体平台的覆盖情况：

1. B站：有多少UP主做过此话题？主流视角是什么？有无冷门视角？
2. 抖音/快手：短视频如何呈现此话题？爆款视频的共性是什么？
3. 影视剧：有哪些相关的纪录片/电影/电视剧？
4. 播客/音频：哪些历史类播客讨论过此话题？

基于你对中文媒体生态的了解做分析。输出JSON：
{{
  "bilibili": {{"coverage": "高｜中｜低", "mainstream_perspective": "主流视角(40字)", "gap_opportunity": "冷门机会(40字)"}},
  "short_video": {{"coverage": "高｜中｜低", "viral_pattern": "爆款共性(40字)"}},
  "film_tv": {{"related_works": ["作品1","作品2"], "narrative_style": "叙事倾向(40字)"}},
  "audio": {{"podcast_coverage": "高｜中｜低", "key_platforms": "主要平台(20字)"}},
  "cross_platform_insight": "跨平台综合洞察(80字)"
}}"""

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1000
    )
    text = resp.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "")
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except:
        return {"raw": text, "topic": topic}


def insight_engine_query(topic: str) -> dict:
    """
    InsightEngine: 数据库挖掘
    从已积累的数据中提取与话题相关的洞察
    """
    from database import _get_conn
    import psycopg2.extras

    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    result = {"topic": topic}

    # 1. 相关热点历史
    cur.execute("""
        SELECT topic, heat_score, created_at
        FROM hot_topics
        WHERE topic ILIKE %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (f"%{topic}%",))
    result["related_hotspots"] = [dict(r) for r in cur.fetchall()]

    # 2. 已有生成记录
    cur.execute("""
        SELECT id, meta, created_at
        FROM generations
        WHERE topic ILIKE %s
        ORDER BY created_at DESC
        LIMIT 3
    """, (f"%{topic}%",))
    result["previous_generations"] = []
    for r in cur.fetchall():
        meta = r["meta"] if isinstance(r["meta"], dict) else {}
        result["previous_generations"].append({
            "id": r["id"],
            "meta": meta,
            "created_at": str(r["created_at"])
        })

    # 3. 关联实体
    cur.execute("""
        SELECT source_entity, relation, target_entity, confidence
        FROM entity_relations
        WHERE source_entity ILIKE %s OR target_entity ILIKE %s
        ORDER BY confidence DESC
        LIMIT 10
    """, (f"%{topic}%", f"%{topic}%"))
    result["related_entities"] = [dict(r) for r in cur.fetchall()]

    # 4. 情感倾向
    cur.execute("""
        SELECT label, round(avg(score)::numeric, 2) as avg_score, count(*) as cnt
        FROM sentiment_labels
        WHERE target_type = 'article' AND target_id ILIKE %s
        GROUP BY label
    """, (f"%{topic[:8]}%",))
    result["sentiment"] = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return result


def run_all_engines(topic: str) -> dict:
    """并行运行三大引擎，返回聚合分析结果"""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_query = executor.submit(query_engine_search, topic)
        future_media = executor.submit(media_engine_analyze, topic)
        future_insight = executor.submit(insight_engine_query, topic)

        return {
            "topic": topic,
            "query_engine": future_query.result(),
            "media_engine": future_media.result(),
            "insight_engine": future_insight.result(),
            "meta": {"engines": 3, "parallel": True}
        }


if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "安史之乱"

    print("=== QueryEngine ===")
    print(json.dumps(query_engine_search(topic), ensure_ascii=False, indent=2))

    print("\n=== MediaEngine ===")
    print(json.dumps(media_engine_analyze(topic), ensure_ascii=False, indent=2))

    print("\n=== InsightEngine ===")
    print(json.dumps(insight_engine_query(topic), ensure_ascii=False, indent=2))
