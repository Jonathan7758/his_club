"""
Scorer v4.0 — 3维评分子系统
互联网热度 (30%) / 角度独特度 (40%) / 预测传播热度 (30%)
每项评分附带证据，综合评分 = hot*0.3 + unique*0.4 + spread*0.3
"""
import math

SCORE_DIMENSIONS = ["互联网热度", "角度独特度", "预测传播热度"]

WEIGHTS = {
    "互联网热度": 0.30,
    "角度独特度": 0.40,
    "预测传播热度": 0.30,
}


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, round(value, 1)))


def score_hot(external: dict | None) -> dict[str, float | str]:
    if not external:
        return {"value": 0.0, "evidence": "无外部数据"}

    wechat_count = external.get("wechat_count", 0)
    web_count = external.get("web_count", 0)
    newsnow_mentions = external.get("newsnow_mentions", 0)
    hot_level = external.get("hot_level", "cold")

    wechat_log = math.log2(max(wechat_count, 1))
    web_log = math.log2(max(web_count, 1)) * 0.5

    raw = wechat_log + web_log + newsnow_mentions * 0.5

    if hot_level == "hot":
        raw *= 1.2
    elif hot_level == "warm":
        raw *= 1.0
    else:
        raw *= 0.7

    value = _clamp(raw)
    evidence = generate_evidence_hot(wechat_count, web_count, newsnow_mentions, hot_level)

    return {"value": value, "evidence": evidence}


def score_unique(external: dict | None = None, forum: list | None = None, graph: dict | None = None) -> dict:
    if not external and not forum and not graph:
        return {"value": 0.0, "evidence": "无分析数据"}

    total_articles = max(external.get("wechat_articles", 1) if external else 1, 1)
    matches = external.get("wechat_matches", 0) if external else 0
    competition_ratio = 1.0 - (matches / total_articles)

    avg_novelty = 5.0
    if forum and len(forum) > 0:
        novelties = [a.get("novelty", 5) for a in forum if isinstance(a, dict)]
        if novelties:
            avg_novelty = sum(novelties) / len(novelties)

    gaps = graph.get("gaps_count", 0) if graph else 0
    gaps_bonus = min(gaps * 0.5, 3.0)

    raw = competition_ratio * 5.0 + (avg_novelty / 10.0) * 4.0 + gaps_bonus
    value = _clamp(raw)
    evidence = generate_evidence_unique(matches, total_articles, avg_novelty, gaps)

    return {"value": value, "evidence": evidence}


def score_spread(mirofish: dict | None = None, forum: list | None = None, sentiments: dict | None = None) -> dict:
    if not mirofish and not forum and not sentiments:
        return {"value": 0.0, "evidence": "无预测数据"}

    conflict = mirofish.get("conflict_intensity", 5.0) if mirofish else 5.0

    controversy_count = 0
    if forum:
        controversy_count = sum(1 for a in forum if isinstance(a, dict) and a.get("controversy"))

    sentiment_score = 0
    sentiment_summary = ""
    if sentiments:
        sentiment_score = sentiments.get("争议", 0) * 0.5 + sentiments.get("猎奇", 0) * 0.3 + sentiments.get("共情", 0) * 0.2
        max_sent = max(sentiments.values()) if sentiments else 1
        sentiment_score = min(sentiment_score / max(max_sent, 1) * 5.0, 5.0)
        top_labels = sorted(sentiments.items(), key=lambda x: x[1], reverse=True)[:2]
        sentiment_summary = "+".join([l for l, _ in top_labels])

    raw = (conflict / 10.0) * 4.0 + min(controversy_count * 1.5, 3.0) + sentiment_score * 0.6
    value = _clamp(raw)
    evidence = generate_evidence_spread(conflict, controversy_count, sentiment_summary)

    return {"value": value, "evidence": evidence}


def generate_evidence_hot(wechat_count: int, web_count: int, newsnow_mentions: int, hot_level: str) -> str:
    parts = [
        f"搜狗微信{wechat_count}篇" if wechat_count > 0 else "微信无数据",
        f"网页{web_count}条" if web_count > 0 else "",
        f"NewsNow提及{newsnow_mentions}次" if newsnow_mentions > 0 else "",
        f"热度等级:{hot_level}",
    ]
    return " | ".join([p for p in parts if p])


def generate_evidence_unique(wechat_matches: int, wechat_articles: int, avg_novelty: float, gaps: int) -> str:
    coverage_pct = round((1.0 - wechat_matches / max(wechat_articles, 1)) * 100)
    parts = [
        f"竞品覆盖{coverage_pct}%未重叠" if wechat_articles > 0 else "",
        f"平均新颖度{avg_novelty:.1f}/10",
        f"知识图谱盲区{gaps}个" if gaps > 0 else "",
    ]
    return " | ".join([p for p in parts if p])


def generate_evidence_spread(conflict: float, controversy_count: int, sentiment_summary: str) -> str:
    parts = [
        f"博弈冲突度{conflict:.1f}",
        f"争议论点{controversy_count}个" if controversy_count > 0 else "",
        f"情感标签:{sentiment_summary}" if sentiment_summary else "",
    ]
    return " | ".join([p for p in parts if p])


def compute_total(hot: dict, unique: dict, spread: dict) -> dict:
    total = (
        hot["value"] * WEIGHTS["互联网热度"]
        + unique["value"] * WEIGHTS["角度独特度"]
        + spread["value"] * WEIGHTS["预测传播热度"]
    )
    return {
        "hot_score": hot,
        "unique_score": unique,
        "spread_score": spread,
        "total_score": round(total, 2),
    }


class Scorer:
    def score(self, analysis_data: dict) -> dict:
        external = analysis_data.get("external", {})
        forum = analysis_data.get("forum", [])
        mirofish = analysis_data.get("mirofish", {})
        graph = analysis_data.get("graph", {})
        sentiments = analysis_data.get("sentiments", {})

        hot = score_hot(external if external else None)
        unique = score_unique(external if external else None, forum, graph)
        spread = score_spread(mirofish if mirofish else None, forum, sentiments)

        return compute_total(hot, unique, spread)

    def format_score_table(self, scores: dict) -> str:
        h = scores["hot_score"]
        u = scores["unique_score"]
        s = scores["spread_score"]

        lines = [
            "┌──────────────┬───────┬────────────────────────────────────┐",
            f"│ 互联网热度    │ {h['value']:4.1f} │ {h['evidence'][:34]:<34} │",
            f"│ 角度独特度    │ {u['value']:4.1f} │ {u['evidence'][:34]:<34} │",
            f"│ 预测传播热度  │ {s['value']:4.1f} │ {s['evidence'][:34]:<34} │",
            "├──────────────┼───────┼────────────────────────────────────┤",
            f"│ **综合评分**  │**{scores['total_score']:4.1f}**│                                    │",
            "└──────────────┴───────┴────────────────────────────────────┘",
        ]
        return "\n".join(lines)
