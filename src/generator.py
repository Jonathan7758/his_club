"""
生产级历史内容生成器 v3.0
ForumEngine 7Agent辩论 + 搜狗双源验证 + 负面约束突破共识
"""
import json
import os
from openai import OpenAI
from fact_checker import fact_check_article, inject_dispute_markers, generate_verification_footnote
from database import save_generation, save_entity_relations, save_sentiment_labels

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)

MODEL = "deepseek-chat"
DIMENSIONS = ["政治制度", "经济财政", "军事战略", "文化社会", "关键人物", "技术演进", "地理环境"]

def _call_llm(prompt: str, temperature: float = 0.8, max_tokens: int = 2000) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content

from search import weixin_search as _weixin_search, sogou_web_search as _sogou_web_search

def _search_verify(thesis: str, angle_title: str) -> dict:
    """双源验证：搜狗微信(公众号池) + 搜狗网页(全网)，综合计算真实新颖度"""
    try:
        # 提取论点的核心短语做精准搜索
        import re
        words = re.findall(r'[\u4e00-\u9fff]{2,4}', thesis[:30])
        core_phrase = " ".join(words[:3]) if words else angle_title
        query = f"{angle_title} {core_phrase}"
        thesis_keywords = set(words[:4])  # 核心词组用于匹配
        
        # 主验证源：微信公众号池
        wx_results = _weixin_search(query, max_results=10)
        # 辅验证源：全网中文
        web_results = _sogou_web_search(query, max_results=10)
        
        # 过滤空结果
        wx_valid = [r for r in wx_results if r != "无公众号文章"]
        web_valid = [r for r in web_results if r]
        
        # 精准匹配：核心短语需同时命中
        wx_matches = 0
        for r in wx_valid:
            if len(thesis_keywords) >= 2:
                hit_phrases = sum(1 for w in thesis_keywords if w in r)
                if hit_phrases >= 2:
                    wx_matches += 1
            else:
                hits = sum(1 for c in set(angle_title) if c in r)
                if hits >= len(set(angle_title)) * 0.3:
                    wx_matches += 1
        
        web_matches = 0
        for r in web_valid[:5]:
            if len(thesis_keywords) >= 2:
                hit_phrases = sum(1 for w in thesis_keywords if w in r)
                if hit_phrases >= 2:
                    web_matches += 1
            else:
                hits = sum(1 for c in set(angle_title) if c in r)
                if hits >= len(set(angle_title)) * 0.25:
                    web_matches += 1
        
        # 公众号权重70%，全网权重30%
        total_ref = max(len(wx_valid), 1) * 0.7 + max(len(web_valid), 1) * 0.3
        total_matches = wx_matches * 0.7 + web_matches * 0.3
        
        real_novelty = max(0.2, round(1.0 - (total_matches / max(total_ref, 1)), 2))
        
        return {
            "real_novelty": real_novelty,
            "wechat_articles": len(wx_valid),
            "wechat_matches": wx_matches,
            "web_results": len(web_valid),
            "web_matches": web_matches,
            "top_wechat": wx_valid[:2],
            "note": f"公众号{wx_matches}/{len(wx_valid)}篇相似 | 全网{web_matches}/{len(web_valid)}条相似 → 新颖度{real_novelty:.0%}"
        }
    except Exception as e:
        return {"real_novelty": None, "note": f"验证失败: {str(e)[:60]}"}

def _get_hot_score(topic: str) -> dict:
    """双源扫描：公众号+知乎/B站，判断选题热度"""
    try:
        wx = _weixin_search(topic, max_results=15)
        web = _sogou_web_search(f"{topic} 知乎 OR B站 OR 豆瓣", max_results=15)
        
        wx_valid = [r for r in wx if r != "无公众号文章"]
        web_valid = [r for r in web if r]
        
        hot_level = "hot" if len(wx_valid) > 10 else ("warm" if len(wx_valid) > 3 else "cold")
        
        return {
            "hot_level": hot_level,
            "wechat_count": len(wx_valid),
            "web_count": len(web_valid),
            "note": f"公众号{len(wx_valid)}篇 | 网页{len(web_valid)}条 → 热度:{hot_level}"
        }
    except:
        return {"hot_level": "unknown", "note": "热度扫描暂不可用"}

def _forum_debate(topic: str, forbidden: list[str]) -> list[dict]:
    """ForumEngine Lite: 7Agent辩论，每轮碰撞后修正角度，提取真正独特的分析"""
    
    # === Round 1: Each agent independently proposes an angle ===
    round1_prompts = {
        "政治制度": f"你是《{topic}》政治制度分析专家。全网已饱和的观点有：{';'.join(forbidden[:3])}。禁止重复这些观点。请从一个学术界几乎无人触及、极度冷门的政治制度子问题，提出一个对《{topic}》的全新分析角度。角度必须具体到可论证，给出2条独特论据。JSON: {{'angle_title':'...','thesis':'...','evidence':['','']}}",
        "经济财政": f"你是《{topic}》经济史专家。禁止：{';'.join(forbidden[1:4])}。请找到一个被经济史学者长期忽视的财政细节，从这个细节出发提出颠覆性的分析角度。必须给出具体数据或史料支持。JSON同上。",
        "军事战略": f"你是《{topic}》军事战略专家。禁止：{';'.join(forbidden[:3])}。请从一个极其冷门的军事后勤或技术细节切入，提出与众不同的分析。避开所有常见军事论述。JSON同上。",
        "文化社会": f"你是《{topic}》文化社会史专家。禁止：{';'.join(forbidden[2:5])}。请关注被主流叙事忽略的边缘群体或亚文化现象，从中提取独特分析角度。JSON同上。",
        "关键人物": f"你是《{topic}》人物研究专家。禁止：{';'.join(forbidden[1:4])}。请聚焦一个常被忽视的次要人物或幕僚，从这个边缘视角看整体事件。JSON同上。",
        "技术演进": f"你是《{topic}》技术史专家。禁止：{';'.join(forbidden[2:5])}。请从技术演进路径（冶铁/造船/印刷/火药/水利/纺织等）中提取一个被忽视的技术决定论视角。必须说明具体技术细节如何左右了历史走向。JSON同上。",
        "地理环境": f"你是《{topic}》历史地理学专家。禁止：{';'.join(forbidden[2:5])}。请聚焦地理约束（关隘/水系/气候/土壤/交通线/人口密度）中一个被忽视的变量，论证地理因素如何重塑了《{topic}》的进程。给出具体地名和地形数据。JSON同上。",
    }
    
    round1 = {}
    for dim, prompt in round1_prompts.items():
        resp = _call_llm(prompt, temperature=0.95, max_tokens=500)
        # 清理常见格式问题
        clean = resp.strip()
        clean = clean.replace("```json", "").replace("```", "")
        try:
            start = clean.index("{")
            end = clean.rindex("}") + 1
            round1[dim] = json.loads(clean[start:end])
        except:
            round1[dim] = {"angle_title": f"{dim}分析", "thesis": resp[:200], "evidence": []}
    
    # === Round 2: Cross-criticism - each agent reads others' proposals and refines ===
    round2 = {}
    for dim, my_proposal in round1.items():
        other_proposals = {k: v.get("thesis", "") for k, v in round1.items() if k != dim}
        others_text = "; ".join([f"[{k}]: {v}" for k, v in other_proposals.items()])
        
        refine_prompt = f"""你是《{topic}》{dim}专家。你的初步角度是：{my_proposal.get('thesis','')}
其他专家的角度：{others_text}

现在进行第二轮辩论：你的角度是否与其他人有重叠？如果有，请主动偏离。如果没有，请进一步深挖。用其他人的视角来批判你自己的角度，找出弱点，然后在修正后提出一个更加锋利、更具原创性的版本。

输出JSON：{{'angle_title':'修正后的角度','thesis':'更锋利的论点','evidence':['论据1','论据2'],'debate_note':'本轮修正说明'}}"""
        
        resp = _call_llm(refine_prompt, temperature=0.9, max_tokens=500)
        clean = resp.strip().replace("```json", "").replace("```", "")
        try:
            start = clean.index("{")
            end = clean.rindex("}") + 1
            round2[dim] = json.loads(clean[start:end])
        except:
            round2[dim] = my_proposal
    
    # === Round 3: Debate Host synthesizes final unique angles ===
    all_angles_text = ""
    for dim, a in round2.items():
        all_angles_text += f"[{dim}] {a.get('angle_title','')}: {a.get('thesis','')}\n"
    
    host_prompt = f"""你是历史内容主编。以下是7位专家经过两轮辩论后提出的《{topic}》分析角度：

{all_angles_text}

请做以下判断：
1. 哪些角度仍然流于表面或与已知饱和观点相似？直接淘汰。
2. 哪些角度真正具有原创性和深度？选出最优秀的3-4个。
3. 对选中的每个角度，给出1-10的新颖度评分和评分理由。

输出JSON数组：
[{{'dimension':'维度','angle_title':'标题','thesis':'论点','evidence':['','',''],'novelty':8,'controversy':true,'selection_reason':'为什么选中'}}]"""
    
    resp = _call_llm(host_prompt, temperature=0.7, max_tokens=2000)
    clean = resp.strip().replace("```json", "").replace("```", "")
    try:
        start = clean.index("[")
        end = clean.rindex("]") + 1
        final_angles = json.loads(clean[start:end])
    except:
        # Fallback: use round2 results directly
        final_angles = []
        for k, v in round2.items():
            if v.get("thesis") and "无法处理" not in v.get("thesis", ""):
                final_angles.append({
                    "dimension": k,
                    "angle_title": v.get("angle_title", k),
                    "thesis": v.get("thesis", ""),
                    "evidence": v.get("evidence", []),
                    "novelty": 7,
                    "controversy": True
                })
    
    # 过滤掉合规拒绝和空论点
    final_angles = [a for a in final_angles if a.get("thesis") 
                    and "无法处理" not in a.get("thesis", "")
                    and "抱歉" not in a.get("thesis", "")
                    and len(a.get("thesis", "")) > 20]
    
    return final_angles

def generate_angles(topic: str, inject_mirofish: bool = True) -> list[dict]:
    """Stage 1: 扫描饱和角度 → ForumEngine辩论 → 搜索验证 + MiroFish反事实推演"""
    
    # Step 0: 扫描市场，找饱和角度
    scan_queries = [
        f"{topic} 分析 角度 深度",
        f"{topic} 独特 观点 解读",
        f"{topic} 冷门 真相 揭秘",
    ]
    saturated = set()
    for q in scan_queries:
        wx = _weixin_search(q, max_results=5)
        for r in wx:
            if r != "无公众号文章" and len(r) > 20:
                saturated.add(r[:40])
    
    forbidden = list(saturated)[:10] if saturated else []
    
    # Step 1: ForumEngine 7Agent辩论（带负面约束）
    angles = _forum_debate(topic, forbidden)
    
    # Step 2: 搜索验证每个角度
    for a in angles:
        verify = _search_verify(a.get("thesis", ""), a.get("angle_title", ""))
        a["llm_novelty"] = a.get("novelty", 7) / 10
        a["real_novelty"] = verify.get("real_novelty")
        a["search_verification"] = verify
        a["forum_debate"] = True
        a["forbidden_count"] = len(forbidden)
    
    # Step 3: MiroFish 反事实推演角度注入
    if inject_mirofish:
        try:
            from mirofish import quick_prediction, _suggest_what_if
            what_if_predictions = quick_prediction(topic)
            
            if isinstance(what_if_predictions, list):
                for wi in what_if_predictions[:3]:
                    what_if_text = wi.get("what_if", "")
                    direction = wi.get("direction", "")
                    title_sug = wi.get("title_suggestion", "")
                    
                    if not what_if_text:
                        continue
                    
                    # 为每个 MiroFish 角度做搜索验证（反事实命题天然高新颖度）
                    miro_verify = _search_verify(direction or what_if_text, what_if_text[:30])
                    real_novelty = miro_verify.get("real_novelty", 0.9)
                    
                    angles.append({
                        "dimension": "反事实推演",
                        "angle_title": title_sug or what_if_text[:40],
                        "thesis": f"{what_if_text}。{direction}",
                        "evidence": [wi.get("appeal", ""), direction[:150]],
                        "novelty": 9,
                        "llm_novelty": 0.9,
                        "real_novelty": real_novelty,
                        "search_verification": miro_verify,
                        "source": "mirofish",
                        "what_if": what_if_text,
                        "controversy": True,
                    })
        except Exception:
            pass  # MiroFish 注入失败不影响主流程
    
    return angles

def select_best_angles(angles: list[dict], top_n: int = 3) -> list[dict]:
    """用真实新颖度排序"""
    scored = [a for a in angles if a.get("real_novelty") is not None]
    scored.sort(key=lambda x: x["real_novelty"], reverse=True)
    return scored[:top_n]

def generate_article(topic: str, angles: list[dict]) -> dict:
    """Stage 2: 公众号图文（优先使用真实新颖度最高的角度）"""
    best = select_best_angles(angles, 3)
    angles_text = "\n".join([
        f"- [{a['dimension']}] {a['angle_title']}: {a['thesis']} (真实新颖度:{a.get('real_novelty','?')})"
        for a in best
    ])
    
    prompt = f"""你是公众号历史类爆款写手。基于以下经过搜索验证的角度，生成微信公号文章。

选题：{topic}
经搜索验证的高新颖度角度：
{angles_text}

要求：3个候选标题、3-4节正文(每节300-400字)、3金句、延伸阅读。
输出JSON：{{"titles":[...], "recommended_title":"...", "subtitle":"...", "sections":[...], "golden_quotes":[...], "extended_reading":[...]}}"""
    
    resp = _call_llm(prompt, temperature=0.75, max_tokens=4000)
    try:
        start = resp.index("{")
        end = resp.rindex("}") + 1
        return json.loads(resp[start:end])
    except:
        return {"raw": resp}

def generate_video_script(topic: str, angles: list[dict]) -> dict:
    """Stage 3: 视频号脚本"""
    best = select_best_angles(angles, 2)
    angles_text = "、".join([a["angle_title"] for a in best])
    
    prompt = f"""生成历史视频号分镜脚本。选题:{topic}。角度:{angles_text}。
总时长90-120秒。输出JSON：{{"total_duration":120, "segments":[{{"time":"0-15s", "visual":"...", "narration":"..."}}], "memorable_points":["..."]}}"""
    
    resp = _call_llm(prompt, temperature=0.7, max_tokens=2000)
    try:
        start = resp.index("{")
        end = resp.rindex("}") + 1
        return json.loads(resp[start:end])
    except:
        return {"raw": resp}

def _extract_entities_from_article(article: dict, topic: str) -> list[dict]:
    """从生成的文章中提取历史实体关系"""
    sections_text = " ".join([
        sec.get("body") or sec.get("content") or ""
        for sec in article.get("sections", [])
    ])
    if not sections_text:
        return []

    prompt = f"""从以下关于《{topic}》的历史文章中提取实体关系三元组。
每个三元组格式：(人物/制度/事件/地名, 关系, 人物/制度/事件/地名)
关系类型：导致、影响、隶属于、对抗、继承、废除了、建立了、促使了、背叛了、结盟了

文章内容：
{sections_text[:3000]}

输出JSON数组：
[{{"source_entity":"实体A","relation":"关系","target_entity":"实体B","context":"原文中对应的句子(50字)","confidence":0.8}}]

只提取明确有历史依据的关系，最多20条。"""

    resp = _call_llm(prompt, temperature=0.3, max_tokens=2000)
    clean = resp.strip().replace("```json", "").replace("```", "")
    try:
        start = clean.index("[")
        end = clean.rindex("]") + 1
        return json.loads(clean[start:end])
    except:
        return []

def _analyze_article_sentiment(article: dict, topic: str) -> list[dict]:
    """对文章内容运行历史领域情感分析"""
    sections_text = " ".join([
        sec.get("body") or sec.get("content") or ""
        for sec in article.get("sections", [])
    ])
    if not sections_text or len(sections_text) < 30:
        return []

    prompt = f"""分析以下关于《{topic}》的历史文章的读者情感倾向。用5个历史情感维度打分(0-1)：
怀古(对过去的怀念)、争议(观点分歧程度)、猎奇(新鲜感吸引度)、共情(代入感)、反思(批判性思考)

文章内容：
{sections_text[:1500]}

输出JSON数组：
[{{"label":"怀古","score":0.7}},{{"label":"争议","score":0.3}},{{"label":"猎奇","score":0.5}},{{"label":"共情","score":0.6}},{{"label":"反思","score":0.8}}]"""

    resp = _call_llm(prompt, temperature=0.3, max_tokens=400)
    clean = resp.strip().replace("```json", "").replace("```", "")
    try:
        start = clean.index("[")
        end = clean.rindex("]") + 1
        labels = json.loads(clean[start:end])
        target_id = topic[:16]
        for l in labels:
            l["target_type"] = "article"
            l["target_id"] = target_id
        return labels
    except:
        return []

def generate(topic: str, inject_mirofish: bool = True) -> dict:
    """全流程生成 + 搜索验证 + MiroFish反事实推演"""
    result = {"topic": topic}
    
    # 热度扫描
    result["hot_scan"] = _get_hot_score(topic)
    
    # 角度分析（含搜索验证 + MiroFish注入）
    result["angles"] = generate_angles(topic, inject_mirofish=inject_mirofish)
    
    # 图文 + 脚本
    result["article"] = generate_article(topic, result["angles"])
    result["video_script"] = generate_video_script(topic, result["angles"])

    # 事实校验层
    fact_check = fact_check_article(result["article"], topic)
    if fact_check["total_claims"] > 0:
        result["article"] = inject_dispute_markers(result["article"], fact_check)
        result["verification_footnote"] = generate_verification_footnote(fact_check)
    result["fact_check"] = fact_check

    result["meta"] = {
        "generated_by": "deepseek-chat + sogou_verification",
        "angles_count": len(result["angles"]),
        "verified_angles": sum(1 for a in result["angles"] if a.get("real_novelty") is not None),
        "fact_check_score": fact_check.get("overall_score"),
        "format_version": "3.0"
    }

    # 实体关系抽取
    entities = _extract_entities_from_article(result["article"], topic)
    if entities:
        try:
            n = save_entity_relations(entities, extracted_from=f"generation/{topic}")
            result["meta"]["entity_relations"] = n
        except:
            pass

    # 情感分析
    sentiments = _analyze_article_sentiment(result["article"], topic)
    if sentiments:
        try:
            save_sentiment_labels(sentiments)
            result["meta"]["sentiment_labels"] = len(sentiments)
        except:
            pass

    try:
        gen_id = save_generation(topic, result)
        result["meta"]["db_id"] = gen_id
    except Exception as e:
        print(f"  DB save failed: {e}")
    
    return result

if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "安史之乱"
    output = generate(topic)
    print(json.dumps(output, ensure_ascii=False, indent=2))
