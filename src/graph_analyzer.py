"""
轻量知识图谱分析 v1.0
基于 entity_relations 表做图分析：中心度/聚类/话题盲区发现
无需 Neo4j，纯 PostgreSQL + Python 实现
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import _get_conn
import psycopg2.extras


def get_graph_stats() -> dict:
    """图基础统计"""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM entity_relations")
    total_relations = cur.fetchone()[0]

    cur.execute("SELECT count(DISTINCT source_entity) + count(DISTINCT target_entity) - count(DISTINCT source_entity) AS unique_nodes FROM (SELECT source_entity, target_entity FROM entity_relations) t")
    unique_nodes = cur.fetchone()[0]

    cur.execute("SELECT relation, count(*) as cnt FROM entity_relations GROUP BY relation ORDER BY cnt DESC LIMIT 10")
    top_relations = [{"relation": r[0], "count": r[1]} for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {"total_relations": total_relations, "unique_entities": unique_nodes, "top_relations": top_relations}


def get_entity_centrality(top_n: int = 20) -> list[dict]:
    """实体中心度分析 — 找出连接最多的核心实体"""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT entity, sum(cnt) as total_links
        FROM (
            SELECT source_entity as entity, count(*) as cnt FROM entity_relations GROUP BY source_entity
            UNION ALL
            SELECT target_entity as entity, count(*) as cnt FROM entity_relations GROUP BY target_entity
        ) t
        GROUP BY entity
        ORDER BY total_links DESC
        LIMIT %s
    """, (top_n,))

    results = [{"entity": r[0], "total_links": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return results


def find_topic_clusters(min_cooccur: int = 2) -> list[dict]:
    """发现话题聚类 — 共现关系形成的实体群组"""
    conn = _get_conn()
    cur = conn.cursor()

    # 找出所有实体对及其共现关系
    cur.execute("""
        SELECT
            LEAST(source_entity, target_entity) as e1,
            GREATEST(source_entity, target_entity) as e2,
            count(*) as cooccur_count,
            string_agg(DISTINCT relation, ', ') as relations
        FROM entity_relations
        GROUP BY LEAST(source_entity, target_entity), GREATEST(source_entity, target_entity)
        HAVING count(*) >= %s
        ORDER BY cooccur_count DESC
        LIMIT 30
    """, (min_cooccur,))

    clusters = []
    for r in cur.fetchall():
        clusters.append({
            "entity_a": r[0],
            "entity_b": r[1],
            "cooccur_count": r[2],
            "relations": r[3]
        })

    cur.close()
    conn.close()
    return clusters


def find_content_gaps() -> dict:
    """发现内容盲区 — 哪些历史维度/实体被讨论得不够"""
    conn = _get_conn()
    cur = conn.cursor()

    # 从 generations 中获取所有已生成的话题
    cur.execute("SELECT topic FROM generations")
    generated_topics = [r[0] for r in cur.fetchall()]

    # 从 hot_topics 中获取过但未生成的话题
    cur.execute("""
        SELECT ht.topic, ht.source_platform, ht.heat_score, ht.relevance
        FROM hot_topics ht
        WHERE NOT EXISTS (
            SELECT 1 FROM generations g WHERE g.topic ILIKE '%' || ht.topic || '%'
        )
        AND ht.created_at >= NOW() - INTERVAL '7 days'
        ORDER BY ht.heat_score DESC
        LIMIT 10
    """)
    missed_opportunities = [dict(r) for r in cur.fetchall()]

    # 情感维度覆盖分析
    cur.execute("""
        SELECT label, count(*) as cnt
        FROM sentiment_labels
        GROUP BY label
        ORDER BY cnt
    """)
    sentiment_coverage = [dict(r) for r in cur.fetchall()]

    # 关系类型覆盖
    cur.execute("""
        SELECT relation, count(*) as cnt
        FROM entity_relations
        GROUP BY relation
        ORDER BY cnt
        LIMIT 10
    """)
    relation_coverage = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    # LLM 生成盲区建议
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        )

        topics_str = ", ".join(generated_topics[-20:])
        gaps_str = ", ".join([m["topic"] for m in missed_opportunities[:5]])

        prompt = f"""你是历史内容运营策略师。请分析以下数据，提出内容盲区建议。

已生成的话题：{topics_str[:1000]}
错过的高热度话题：{gaps_str[:500]}
情感覆盖：{json.dumps(sentiment_coverage, ensure_ascii=False)}
关系覆盖：{json.dumps(relation_coverage, ensure_ascii=False)}

请提出3个被忽视的历史话题方向（朝代/事件/维度），每个给出：
- 话题建议
- 为什么被忽视了
- 公众号受众潜力（高/中/低）

输出JSON数组：[{{"gap_topic":"建议话题","neglect_reason":"被忽视原因(40字)","potential":"高｜中｜低","angle_suggestion":"切入角度建议(50字)"}}]"""

        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=1500
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "")
        try:
            start = text.index("[")
            end = text.rindex("]") + 1
            gap_suggestions = json.loads(text[start:end])
        except:
            gap_suggestions = [{"gap_topic": "解析失败", "neglect_reason": text[:100]}]
    except:
        gap_suggestions = []

    return {
        "missed_opportunities": missed_opportunities,
        "sentiment_coverage": sentiment_coverage,
        "relation_coverage": relation_coverage,
        "gap_suggestions": gap_suggestions,
    }


if __name__ == "__main__":
    print("=== 知识图谱基础统计 ===")
    print(json.dumps(get_graph_stats(), ensure_ascii=False, indent=2))

    print("\n=== 实体中心度 Top 10 ===")
    print(json.dumps(get_entity_centrality(10), ensure_ascii=False, indent=2))

    print("\n=== 话题聚类 ===")
    print(json.dumps(find_topic_clusters(), ensure_ascii=False, indent=2))

    print("\n=== 内容盲区 ===")
    print(json.dumps(find_content_gaps(), ensure_ascii=False, indent=2, default=str))
