"""
事实校验层 v1.0
提取文章事实断言 → 搜狗网页交叉验证 → 争议标注 → 来源追溯
"""
import json
import re
import hashlib
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)

MODEL = "deepseek-chat"


def _sogou_web_search(query: str, max_results: int = 8) -> list[dict]:
    """搜狗网页搜索"""
    try:
        import requests
        from bs4 import BeautifulSoup
        url = f"https://www.sogou.com/web?query={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".vrwrap, .rb, .result")[:max_results]:
            title_el = item.select_one("h3 a, .vr-title, .vrTitle a")
            desc_el = item.select_one(".star-wiki, .str-text, .space-txt, .vr_summary, p")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": desc_el.get_text(strip=True)[:200] if desc_el else "",
                    "url": title_el.get("href", "")
                })
        return results
    except:
        return []


def _extract_claims_from_article(article: dict) -> list[dict]:
    """从文章各节提取事实性断言"""
    claims = []
    sections = article.get("sections", [])
    for i, sec in enumerate(sections):
        body = sec.get("body") or sec.get("content") or ""
        if not body:
            continue

        prompt = f"""从以下历史文章段落中提取所有可验证的事实断言（人名/地名/年代/数据/制度名/事件因果等）。
对每个断言标注类型（person/event/date/data/institution/causality），给出置信度 0-1。

段落：{body[:1500]}

输出JSON数组：[{{"claim":"断言原文或摘要", "type":"类型", "confidence":0.8, "section_idx":{i}}}]"""

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "")
        try:
            start = text.index("[")
            end = text.rindex("]") + 1
            section_claims = json.loads(text[start:end])
            claims.extend(section_claims)
        except:
            pass

    return claims


def _verify_single_claim(claim: dict, topic: str) -> dict:
    """对单个事实断言做网络交叉验证"""
    claim_text = claim.get("claim", "")[:80]
    if not claim_text:
        return {"status": "unverifiable", "sources": [], "note": "空断言"}

    query = f"{topic} {claim_text}"
    results = _sogou_web_search(query, max_results=5)

    if not results:
        return {"status": "unverifiable", "sources": [], "note": "无网络搜索结果"}

    # LLM 判断搜索结果是否支持该断言
    sources_text = "\n".join([f"[{i+1}] {r['title']}: {r['snippet'][:100]}" for i, r in enumerate(results)])

    judge_prompt = f"""你是一位严谨的历史事实核查员。判断以下历史断言是否有网络资料支持。

断言：{claim_text}
断言类型：{claim.get('type', 'unknown')}

网络搜索结果：
{sources_text[:3000]}

请判断：
- verified: 有明确来源证实
- disputed: 不同来源说法矛盾或有争议
- likely_true: 有间接支持但无直接来源
- likely_false: 与主流说法明显矛盾
- unverifiable: 无法从结果中判断

输出JSON：{{"verdict":"verified|disputed|likely_true|likely_false|unverifiable","supporting_sources":[1,3],"conflicting_sources":[2],"confidence":0.7,"note":"判断理由(30字内)"}}"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": judge_prompt}],
        temperature=0.2,
        max_tokens=500
    )
    text = resp.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "")

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        verdict = json.loads(text[start:end])
    except:
        verdict = {"verdict": "unverifiable", "note": "解析失败"}

    verdict["search_results"] = [{"title": r["title"], "url": r["url"]} for r in results]
    verdict["claim"] = claim_text
    verdict["claim_id"] = hashlib.md5(claim_text.encode()).hexdigest()[:8]

    return verdict


def _detect_controversies(verification_results: list[dict]) -> list[dict]:
    """检测存在学术争议的断言簇"""
    disputed = [v for v in verification_results if v.get("verdict") in ("disputed", "likely_false")]
    if len(disputed) >= 2:
        # 存在多个争议点，可能是学术争议话题
        cluster_prompt = f"""以下断言在网络验证中存在争议或矛盾，请判断是否属于学术争议话题（即学界存在不同观点），还是纯粹的事实错误。

争议断言：
{json.dumps(disputed, ensure_ascii=False, indent=2)[:2000]}

输出JSON：{{
  "is_academic_controversy": true/false,
  "controversy_label": "争议标签(如'李隆基责任论')",
  "majority_view": "主流学界观点(50字)",
  "minority_view": "少数派观点(50字)",
  "recommendation": "建议在文章中如何处理(如:标注存在争议)"
}}"""

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": cluster_prompt}],
            temperature=0.3,
            max_tokens=600
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "")
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            controversy = json.loads(text[start:end])
            controversy["disputed_claims"] = [d.get("claim", "") for d in disputed]
            return [controversy]
        except:
            pass

    return []


def fact_check_article(article: dict, topic: str) -> dict:
    """对生成的文章做完整事实校验"""
    claims = _extract_claims_from_article(article)

    if not claims:
        return {"total_claims": 0, "verified": 0, "disputed": 0, "unverifiable": 0,
                "verifications": [], "controversies": [], "overall_score": 1.0,
                "note": "文章中无可验证的事实断言"}

    verified_count = 0
    disputed_count = 0
    unverifiable_count = 0
    verifications = []

    for claim in claims:
        result = _verify_single_claim(claim, topic)
        verifications.append(result)

        verdict = result.get("verdict", "unverifiable")
        if verdict == "verified":
            verified_count += 1
        elif verdict in ("disputed", "likely_false"):
            disputed_count += 1
        else:
            unverifiable_count += 1

    controversies = _detect_controversies(verifications)

    total = len(claims)
    overall_score = round(
        1.0 - (disputed_count / max(total, 1)) * 0.5 - (unverifiable_count / max(total, 1)) * 0.2,
        2
    )
    overall_score = max(0.1, overall_score)

    return {
        "total_claims": total,
        "verified": verified_count,
        "disputed": disputed_count,
        "unverifiable": unverifiable_count,
        "verifications": verifications,
        "controversies": controversies,
        "overall_score": overall_score,
        "verdict": "reliable" if overall_score >= 0.8 else ("caution" if overall_score >= 0.6 else "unreliable"),
        "note": f"经核实 {verified_count}/{total} 条可证实，{disputed_count} 条存争议。事实可靠度 {overall_score:.0%}"
    }


def inject_dispute_markers(article: dict, fact_check: dict) -> dict:
    """
    将争议标注以段落级注解形式注入文章正文
    
    旧版: simple inline text replacement → ⚠️[学界存在争议]
    新版: 在含有争议断言的段落末尾添加结构化校验注记
      格式: > ⚠️ 事实校验: "assertion" — 学界对此存在分歧。
             主流观点: majority_view
             少数观点: minority_view
             建议: recommendation
    """
    if not fact_check.get("controversies"):
        return article

    # Build lookup: claim_text (first 20 chars) → controversy detail
    claim_map = {}
    for c in fact_check["controversies"]:
        for dc in c.get("disputed_claims", []):
            key = dc[:20].strip()
            if key:
                claim_map[key] = {
                    "label": c.get("controversy_label", ""),
                    "majority": c.get("majority_view", ""),
                    "minority": c.get("minority_view", ""),
                    "recommendation": c.get("recommendation", "建议标注存在争议并说明双方观点"),
                    "full_claim": dc,
                }

    # Also build map from verifications for per-claim annotations
    verified_claims = {}
    for v in fact_check.get("verifications", []):
        claim_text = v.get("claim", "")[:80]
        if v.get("verdict") in ("disputed", "likely_false"):
            verified_claims[claim_text[:20].strip()] = v

    marked_sections = []
    for i, sec in enumerate(article.get("sections", [])):
        body = sec.get("body", "")
        if not body:
            marked_sections.append(sec)
            continue

        annotations = []

        for key, detail in claim_map.items():
            if key in body:
                # Only mark if the claim is meaningful (>10 chars)
                full_claim = detail.get("full_claim", key)
                if len(full_claim) > 10:
                    # Add paragraph-level footnote
                    annotation_line = (
                        f"> [事实校验] 关于'{full_claim[:60]}'的论断学界存在争议。\n"
                        f"> 主流观点: {detail['majority']}\n"
                        f"> 少数观点: {detail['minority']}\n"
                        f"> 建议: {detail['recommendation']}"
                    )
                    annotations.append(annotation_line)

        if annotations:
            body = body.rstrip()
            # Append annotations after the body text
            body += "\n\n" + "\n\n".join(annotations)
        
        sec["body"] = body
        marked_sections.append(sec)

    article["sections"] = marked_sections
    article["_dispute_markers_added"] = len(claim_map) > 0
    article["_annotated_claims"] = len(claim_map)

    return article


def generate_verification_footnote(fact_check: dict) -> str:
    """生成文章末尾的结构化事实校验注记（段落级）"""
    lines = ["---\n### 📋 事实校验报告\n"]
    
    verdict_emoji = {"reliable": "✅", "caution": "⚠️", "unreliable": "❌"}
    emoji = verdict_emoji.get(fact_check.get("verdict", ""), "")
    
    total = fact_check.get("total_claims", 0)
    verified = fact_check.get("verified", 0)
    disputed = fact_check.get("disputed", 0)
    unverifiable = fact_check.get("unverifiable", 0)
    
    lines.append(
        f"**{emoji} 综合评估**: {fact_check.get('overall_score', 0):.0%} — "
        f"{verified}/{total}条可证实, {disputed}条存争议, {unverifiable}条未验证"
    )
    lines.append("")
    
    # 逐条列出争议断言详情
    for c in fact_check.get("controversies", []):
        label = c.get("controversy_label", "未标注")
        lines.append(f"#### 🔍 争议话题: {label}")
        lines.append(f"- 主流观点: {c.get('majority_view', '未知')}")
        lines.append(f"- 少数观点: {c.get('minority_view', '未知')}")
        lines.append(f"- 处理建议: {c.get('recommendation', '建议标注')}")
        
        disputed_claims = c.get("disputed_claims", [])
        if disputed_claims:
            lines.append("- 涉及断言:")
            for dc in disputed_claims[:5]:
                lines.append(f"  - \"{dc[:100]}\"")
        lines.append("")
    
    # 已验证断言的最高置信度来源
    verifications = fact_check.get("verifications", [])
    verified_items = [v for v in verifications if v.get("verdict") == "verified"][:3]
    if verified_items:
        lines.append("#### ✅ 已验证断言 (示例)")
        for v in verified_items:
            claim = v.get("claim", "")[:60]
            sources = v.get("supporting_sources", [])
            lines.append(f"- \"{claim}\" — {len(sources)}个来源支持")
        lines.append("")
    
    # 校验说明
    lines.append("*注: 以上校验通过搜狗网页交叉验证完成，可能存在时效性偏差。建议读者兼听多方观点。*")
    
    return "\n".join(lines)


if __name__ == "__main__":
    test_article = {
        "sections": [
            {"body": "安史之乱爆发于755年，由安禄山发动。唐朝因此由盛转衰，人口从5200万骤降至1600万。"},
            {"body": "均田制在安史之乱前就已崩溃，府兵制也随之瓦解，募兵制取而代之。"},
        ]
    }
    result = fact_check_article(test_article, "安史之乱")
    print(json.dumps(result, ensure_ascii=False, indent=2))
