"""
历史文章诊断模块 v1.0
输入已发布文章 → 7维对比诊断 → 输出"好/差/改进"报告
"""
import json
import os
import sys
import hashlib
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)
MODEL = "deepseek-chat"
DIMENSIONS = ["政治制度", "经济财政", "军事战略", "文化社会", "关键人物", "技术演进", "地理环境"]
SENTIMENT_LABELS = ["怀古", "争议", "猎奇", "共情", "反思"]


def _call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 2000) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content


def _parse_json(raw: str):
    text = raw.strip().replace("```json", "").replace("```", "")
    try:
        brace_pos = text.find("{")
        bracket_pos = text.find("[")
        if bracket_pos != -1 and (brace_pos == -1 or bracket_pos < brace_pos):
            start = bracket_pos
            end = text.rindex("]") + 1
        elif brace_pos != -1:
            start = brace_pos
            end = text.rindex("}") + 1
        else:
            return None
        return json.loads(text[start:end])
    except:
        return None


def extract_article_structure(article_text: str, title: str = "") -> dict:
    prompt = f"""分析以下已发布历史文章，提取结构化信息。

文章标题：{title or '未提供'}
文章正文：
{article_text[:4000]}

dimensions_covered 只能从以下7个中选（只列文章实际覆盖的）：
政治制度、经济财政、军事战略、文化社会、关键人物、技术演进、地理环境

输出JSON：
{{
    "detected_topic": "文章主要讨论的历史事件/时代/人物(20字以内)",
    "sub_topics": ["子话题1", "子话题2"],
    "dimensions_covered": ["经济财政", "军事战略"],
    "thesis": "核心论点(80字)",
    "key_evidence": ["论据1", "论据2", "论据3"],
    "entities": ["实体1", "实体2"],
    "writing_tone": "叙述风格(学术/通俗/煽情/客观/娱乐)",
    "target_audience": "目标读者画像(30字)",
    "estimated_length": 文章大致字数
}}"""

    resp = _call_llm(prompt, temperature=0.2, max_tokens=1000)
    return _parse_json(resp) or {"detected_topic": title or "未知", "dimensions_covered": []}


def analyze_sentiment(article_text: str) -> list[dict]:
    prompt = f"""分析以下历史文章的读者情感倾向，用5个历史情感维度打分(0-1)：
怀古(对过去的怀念)、争议(观点分歧程度)、猎奇(新鲜感吸引度)、共情(代入感)、反思(批判性思考)

文章内容：
{article_text[:2000]}

输出JSON数组：
[{{"label":"怀古","score":0.7}},{{"label":"争议","score":0.3}},{{"label":"猎奇","score":0.5}},{{"label":"共情","score":0.6}},{{"label":"反思","score":0.8}}]"""

    resp = _call_llm(prompt, temperature=0.3, max_tokens=400)
    return _parse_json(resp) or []


def evaluate_sentiment_balance(sentiments: list[dict]) -> dict:
    if not sentiments:
        return {"score": 50, "issue": "无法分析情感", "suggestion": "文章内容需足够长以便分析"}
    scores = {s["label"]: s["score"] for s in sentiments}
    high_scores = [k for k, v in scores.items() if v > 0.7]
    low_scores = [k for k, v in scores.items() if v < 0.3]
    balanced = len(high_scores) <= 2 and len(low_scores) <= 2
    score = 100 - (len(high_scores) * 10) - (len(low_scores) * 5)
    return {
        "score": max(40, score),
        "labels": scores,
        "over_represented": high_scores,
        "under_represented": low_scores,
        "balanced": balanced,
        "suggestion": "情感分布均衡" if balanced else f"过度倾向{high_scores}，可增加{low_scores or ['争议','猎奇']}维度"
    }


def analyze_dimension_diversity(structure: dict) -> dict:
    covered = structure.get("dimensions_covered", [])
    missed = [d for d in DIMENSIONS if d not in covered]
    score = min(100, len(covered) * 15)
    return {
        "score": score,
        "covered": covered,
        "covered_count": len(covered),
        "missed": missed,
        "missed_count": len(missed),
        "benchmark_total": len(DIMENSIONS),
        "suggestion": f"覆盖了{len(covered)}/7维度" if len(covered) >= 4
        else f"仅覆盖{len(covered)}/7维度，建议补充{', '.join(missed[:3])}等视角"
    }


def run_fact_check_on_text(article_text: str, topic: str) -> dict:
    from fact_checker import _extract_claims_from_article, _verify_single_claim
    wrapper = {"sections": [{"body": article_text}]}
    claims = _extract_claims_from_article(wrapper)
    if not claims:
        return {"total_claims": 0, "verdicts": {}, "score": 50, "suggestion": "未提取到可验证的事实断言"}

    verdicts = {"verified": 0, "likely_true": 0, "disputed": 0, "likely_false": 0, "unverifiable": 0}
    verified_claims = []
    for c in claims[:15]:
        v = _verify_single_claim(c, topic)
        verdict = v.get("verdict", "unverifiable")
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        verified_claims.append(v)

    accurate = verdicts["verified"] + verdicts["likely_true"]
    total = sum(verdicts.values()) or 1
    score = int(40 + (accurate / total) * 60)

    suggestion = ""
    if verdicts["disputed"] + verdicts["likely_false"] > 0:
        suggestion = f"发现{verdicts['disputed']}处争议 + {verdicts['likely_false']}处可能错误，需核实"
    elif verdicts["unverifiable"] > total * 0.3:
        suggestion = "较多断言无法验证，建议增加可查证的史料引用"
    else:
        suggestion = "事实准确性良好"

    return {
        "total_claims": len(claims),
        "verdicts": verdicts,
        "verified_claims": verified_claims[:5],
        "score": int(min(100, score)),
        "suggestion": suggestion
    }


def compare_to_benchmark(topic: str, structure: dict, article_text: str) -> dict:
    try:
        from generator import generate
        benchmark = generate(topic)
    except Exception as e:
        return {"error": str(e), "score": 50, "suggestion": "基准生成失败，无法对比"}

    bench_angles = benchmark.get("angles", [])
    bench_dimensions = set(a.get("dimension", "") for a in bench_angles)
    actual_dimensions = set(structure.get("dimensions_covered", []))

    dim_overlap = actual_dimensions & bench_dimensions
    novelty_scores = [a.get("real_novelty", 0.5) for a in bench_angles]
    avg_bench_novelty = sum(novelty_scores) / len(novelty_scores) if novelty_scores else 0.5

    fact_score = benchmark.get("fact_check", {}).get("overall_score", 0.7)
    bench_entity_count = benchmark.get("meta", {}).get("entity_relations", 0)

    evidence_count = len(structure.get("key_evidence", []))
    bench_evidence_count = sum(len(a.get("evidence", [])) for a in bench_angles)

    suggestion = ""
    if len(dim_overlap) < 2:
        suggestion = f"你只覆盖了{len(actual_dimensions)}个维度，工具可生成{len(bench_dimensions)}个维度，建议拓宽视角"
    elif evidence_count < bench_evidence_count:
        suggestion = f"论据偏少({evidence_count}条 vs 基准{bench_evidence_count}条)，建议增加史料支撑"
    else:
        suggestion = "维度覆盖接近基准水平"

    return {
        "score": int(min(100, len(dim_overlap) * 12 + 40)),
        "benchmark_angles": len(bench_angles),
        "benchmark_dimensions": list(bench_dimensions),
        "actual_dimensions": list(actual_dimensions),
        "dimension_overlap": list(dim_overlap),
        "benchmark_avg_novelty": round(avg_bench_novelty, 2),
        "benchmark_fact_score": round(fact_score, 2) if fact_score else None,
        "benchmark_entity_count": bench_entity_count,
        "actual_evidence_count": evidence_count,
        "benchmark_evidence_count": bench_evidence_count,
        "suggestion": suggestion
    }


def check_wechat_overlap(detected_topic: str, thesis: str) -> dict:
    from search import weixin_search
    results = weixin_search(detected_topic, max_results=10)
    valid = [r for r in results if r != "无公众号文章"]
    overlap = min(len(valid), 10)
    score = max(10, 100 - overlap * 8)
    return {
        "score": score,
        "similar_articles": len(valid),
        "top_competitors": valid[:3],
        "suggestion": f"有{len(valid)}篇公众号同类文章" if len(valid) >= 5
        else f"公众号同类文章不多({len(valid)}篇)，选题相对独特" if len(valid) <= 3
        else f"公众号市场{len(valid)}篇同类，需差异化切入"
    }


def evaluate_writing_quality(article_text: str, title: str) -> dict:
    if len(article_text) < 100:
        return {"score": 30, "issue": "文章太短", "suggestion": "正文需足够长度才能评估写作质量"}

    head = article_text[:300]
    prompt = f"""你是公众号写作专家。评估这篇历史文章的质量，从4个维度打分(0-100)：

文章标题：{title}
文章开头(前300字)：{head}
全文长度：约{len(article_text)}字

评分维度：
- title_clickbait: 标题吸引力，能否让读者想点开
- opening_hook: 开头300字能否迅速抓住注意力、制造悬念或共鸣
- narrative_clarity: 叙事是否清晰、层次分明、有逻辑主线
- reader_fatigue: 是否有信息过载、段落过长、堆砌感（高分=不疲劳）

同时给出1-50字的整体评价和建议。
输出JSON：{{"title_clickbait":70,"opening_hook":65,"narrative_clarity":60,"reader_fatigue":75,"comment":"整体评价","suggestion":"改进建议"}}"""

    resp = _call_llm(prompt, temperature=0.4, max_tokens=500)
    parsed = _parse_json(resp)
    if not parsed:
        return {"score": 50, "issue": "写作评估解析失败", "suggestion": "重试"}

    scores = [parsed.get("title_clickbait", 50), parsed.get("opening_hook", 50),
              parsed.get("narrative_clarity", 50), parsed.get("reader_fatigue", 50)]
    avg_score = int(sum(scores) / len(scores))

    return {
        "score": avg_score,
        "title_clickbait": parsed.get("title_clickbait", 50),
        "opening_hook": parsed.get("opening_hook", 50),
        "narrative_clarity": parsed.get("narrative_clarity", 50),
        "reader_fatigue": parsed.get("reader_fatigue", 50),
        "comment": parsed.get("comment", ""),
        "suggestion": parsed.get("suggestion", "")
    }


def evaluate_viral_potential(article_text: str, structure: dict, topic: str) -> dict:
    if len(article_text) < 100:
        return {"score": 30, "issue": "文章太短", "suggestion": "正文不足无法评估传播性"}

    prompt = f"""你是有10万+爆文经验的公众号运营。分析以下历史文章的传播潜力。

话题：{topic}
标题：{structure.get('detected_topic', '')[:40]}
论点核心：{structure.get('thesis', '')[:150]}
正文前400字：{article_text[:400]}

从以下4个维度打分(0-100)：
- controversy_spark: 是否抛出有争议性或反直觉的观点，能引发评论区讨论
- share_worthiness: 读者是否愿意转发给朋友（社交货币）
- emotional_punch: 是否有情绪爆点（震惊/感动/愤怒/共鸣），击中读者情感
- uniqueness: 观点是否独特，避免千篇一律的历史科普

输出JSON：{{"controversy_spark":45,"share_worthiness":60,"emotional_punch":55,"uniqueness":40,"comment":"整体评价(30字)","suggestion":"提升传播力的建议(40字)"}}"""

    resp = _call_llm(prompt, temperature=0.4, max_tokens=500)
    parsed = _parse_json(resp)
    if not parsed:
        return {"score": 40, "issue": "传播评估解析失败", "suggestion": "重试"}

    scores = [parsed.get("controversy_spark", 40), parsed.get("share_worthiness", 40),
              parsed.get("emotional_punch", 40), parsed.get("uniqueness", 40)]
    avg_score = int(sum(scores) / len(scores))

    return {
        "score": avg_score,
        "controversy_spark": parsed.get("controversy_spark", 40),
        "share_worthiness": parsed.get("share_worthiness", 40),
        "emotional_punch": parsed.get("emotional_punch", 40),
        "uniqueness": parsed.get("uniqueness", 40),
        "comment": parsed.get("comment", ""),
        "suggestion": parsed.get("suggestion", "")
    }


def generate_improvement_plan(dim_scores: dict, structure: dict, topic: str) -> list[dict]:
    weaknesses = sorted(
        [(k, v) for k, v in dim_scores.items() if v["score"] < 60],
        key=lambda x: x[1]["score"]
    )
    if not weaknesses:
        return [{"priority": "低", "area": "整体表现", "action": "文章质量良好，继续保持多维度深度分析风格"}]

    prompt = f"""针对历史文章《{topic}》的以下弱项，生成3条具体可操作的改进建议：

弱项：{json.dumps([{'area': k, 'score': v['score'], 'issue': v.get('suggestion','')} for k, v in weaknesses[:3]], ensure_ascii=False)}

每条建议格式：{{"priority":"高|中|低","area":"问题领域","action":"具体行动(50字内)","expected_impact":"预期效果(30字内)"}}
输出JSON数组"""

    resp = _call_llm(prompt, temperature=0.5, max_tokens=800)
    return _parse_json(resp) or [
        {"priority": "中", "area": w[0], "action": w[1].get("suggestion", "根据诊断优化"), "expected_impact": "预期提升内容质量"}
        for w in weaknesses[:3]
    ]


def diagnose_article(article_text: str, article_title: str = "", run_benchmark: bool = True) -> dict:
    structure = extract_article_structure(article_text, article_title)
    topic = structure.get("detected_topic", article_title or "未知话题")

    sentiments = analyze_sentiment(article_text)
    sentiment_result = evaluate_sentiment_balance(sentiments)

    dimension_result = analyze_dimension_diversity(structure)

    fact_result = run_fact_check_on_text(article_text, topic)

    overlap_result = check_wechat_overlap(topic, structure.get("thesis", ""))

    writing_result = evaluate_writing_quality(article_text, article_title)
    viral_result = evaluate_viral_potential(article_text, structure, topic)

    benchmark_result = {}
    if run_benchmark:
        benchmark_result = compare_to_benchmark(topic, structure, article_text)

    dim_scores = {
        "writing_quality": writing_result,
        "viral_potential": viral_result,
        "angle_diversity": dimension_result,
        "fact_accuracy": fact_result,
        "sentiment_balance": {**sentiment_result, "id": "sentiment"},
        "competition_overlap": {**overlap_result, "id": "competition"},
    }
    if benchmark_result:
        dim_scores["benchmark_gap"] = benchmark_result

    all_scores = [v["score"] for v in dim_scores.values() if "score" in v and "id" not in v]
    overall = int(sum(all_scores) / len(all_scores)) if all_scores else 50

    strengths = [k for k, v in dim_scores.items() if v["score"] >= 70]
    weaknesses = [k for k, v in dim_scores.items() if v["score"] < 60]

    improvement_plan = generate_improvement_plan(dim_scores, structure, topic)

    return {
        "article_title": article_title,
        "detected_topic": topic,
        "article_structure": structure,
        "overall_score": overall,
        "grade": "A" if overall >= 85 else ("B" if overall >= 70 else ("C" if overall >= 55 else "D")),
        "strengths": [dim_scores[s]["suggestion"][:60] if dim_scores[s].get("suggestion") else s for s in strengths],
        "weaknesses": [{"area": w, "detail": dim_scores[w].get("suggestion", "")} for w in weaknesses],
        "dimension_scores": dim_scores,
        "improvement_plan": improvement_plan,
        "summary": f"总体评分{overall}/100（{len(strengths)}优 {len(weaknesses)}弱）。"
                   f"写作{writing_result['score']}分 传播{('有潜力' if viral_result['score']>=60 else '不足')}，"
                   f"覆盖{structure.get('dimensions_covered',[])}维度，"
                   f"情感{('平衡' if sentiment_result.get('balanced') else '偏向')}。"
    }


def batch_analyze(articles: list[dict], run_benchmark: bool = False) -> dict:
    results = []
    topics_seen = []
    for i, art in enumerate(articles):
        text = art.get("content") or art.get("text") or ""
        title = art.get("title") or art.get("article_title") or f"文章{i+1}"
        if not text or len(text) < 100:
            continue
        result = diagnose_article(text, title, run_benchmark=run_benchmark)
        results.append(result)
        topics_seen.append(result["detected_topic"])

    if not results:
        return {"error": "无有效文章"}

    scores = [r["overall_score"] for r in results]
    avg_score = sum(scores) / len(scores)
    grades = {"A": sum(1 for r in results if r["grade"] == "A"),
              "B": sum(1 for r in results if r["grade"] == "B"),
              "C": sum(1 for r in results if r["grade"] == "C"),
              "D": sum(1 for r in results if r["grade"] == "D")}

    all_covered_dims = []
    for r in results:
        all_covered_dims.extend(r.get("article_structure", {}).get("dimensions_covered", []))
    from collections import Counter
    dim_counter = Counter(all_covered_dims)
    dim_coverage = {d: dim_counter.get(d, 0) for d in DIMENSIONS}

    common_weaknesses = []
    for r in results:
        for w in r.get("weaknesses", []):
            common_weaknesses.append(w["area"])
    weakness_counter = Counter(common_weaknesses)

    high_articles = sorted(results, key=lambda r: r["overall_score"], reverse=True)[:3]
    low_articles = sorted(results, key=lambda r: r["overall_score"])[:3]

    batch_prompt = f"""你是公众号历史内容运营顾问。基于{len(results)}篇文章的诊断数据，给出整体运营建议。

平均分：{avg_score:.0f}
最好3篇：{', '.join([r['detected_topic'] for r in high_articles])}
最差3篇：{', '.join([r['detected_topic'] for r in low_articles])}
维度覆盖不足：{json.dumps({k: v for k, v in dim_coverage.items() if v < max(dim_coverage.values(), default=1) * 0.5}, ensure_ascii=False)}
常见弱项：{weakness_counter.most_common(3)}

输出JSON数组3条战略建议：
[{{"area":"战略方向","finding":"发现的问题","strategy":"改进策略(60字内)","expected_impact":"预期效果"}}]"""

    resp = _call_llm(batch_prompt, temperature=0.6, max_tokens=1000)
    batch_suggestions = _parse_json(resp) or []

    return {
        "total_articles": len(results),
        "average_score": round(avg_score, 1),
        "grade_distribution": grades,
        "dimension_coverage": dim_coverage,
        "top_weaknesses": [{"area": k, "occurrence": v} for k, v in weakness_counter.most_common(5)],
        "top_articles": [{"title": r["article_title"], "topic": r["detected_topic"], "score": r["overall_score"], "grade": r["grade"]}
                         for r in high_articles],
        "weakest_articles": [{"title": r["article_title"], "topic": r["detected_topic"], "score": r["overall_score"], "grade": r["grade"]}
                             for r in low_articles],
        "per_article": results,
        "strategic_suggestions": batch_suggestions,
        "summary": f"分析{len(results)}篇文章：均分{avg_score:.0f}/100，A级{grades['A']}篇 B级{grades['B']}篇 C级{grades['C']}篇 D级{grades['D']}篇。"
                   f"最缺维度：{', '.join([d for d, c in dim_coverage.items() if c < max(dim_coverage.values(), default=1)])}。"
                   f"最弱项：{weakness_counter.most_common(1)[0][0] if weakness_counter else '无'}。"
    }


def fetch_wechat_article(url: str) -> dict:
    """从微信公众号文章URL抓取标题+正文"""
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        title_el = soup.select_one("#activity-name, .rich_media_title")
        title = title_el.get_text(strip=True) if title_el else ""

        content_el = soup.select_one("#js_content, .rich_media_content")
        if content_el:
            for tag in content_el.select("img, svg, video, style, script"):
                tag.decompose()
            content = content_el.get_text(separator="\n", strip=True)
        else:
            content = ""

        if not content and not title:
            return {"error": "未能提取文章内容，可能页面结构变化或需登录"}

        return {"title": title, "content": content, "url": url}
    except Exception as e:
        return {"error": str(e)}


def diagnose_from_url(url: str, run_benchmark: bool = True) -> dict:
    article = fetch_wechat_article(url)
    if article.get("error"):
        return article
    result = diagnose_article(article["content"], article["title"], run_benchmark=run_benchmark)
    result["source_url"] = url
    return result


def batch_diagnose_from_urls(urls: list[str], run_benchmark: bool = False) -> dict:
    articles = []
    for url in urls:
        article = fetch_wechat_article(url)
        if article.get("error"):
            articles.append({"title": article.get("error", ""), "content": "", "url": url, "fetch_error": article["error"]})
        else:
            articles.append({"title": article["title"], "content": article["content"], "url": url})
    return batch_analyze(articles, run_benchmark=run_benchmark)


if __name__ == "__main__":
    sample = "秦始皇统一六国后推行郡县制，废除分封制，这是中国历史上的一大进步。然而，秦朝过度使用民力修建长城和阿房宫，导致民怨沸腾。公元前209年，陈胜吴广在蕲县大泽乡揭竿而起，喊出'王侯将相宁有种乎'的口号，拉开了秦末农民起义的序幕。"
    print("=== 单篇诊断测试 ===")
    print(json.dumps(diagnose_article(sample, "秦朝灭亡的教训", run_benchmark=False), ensure_ascii=False, indent=2))
