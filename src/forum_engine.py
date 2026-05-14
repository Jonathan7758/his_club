"""
ForumEngine v4.0 — 7维历史辩论引擎
从 generator.py 拆分，独立为分析层核心模块
3轮辩论: R1独立提案 → R2交叉批评 → R3主编遴选
"""
import json
import re

DIMENSIONS = ["政治制度", "经济财政", "军事战略", "文化社会", "关键人物", "技术演进", "地理环境"]

ROUND1_TEMPLATES = {
    "政治制度": lambda topic, fb: (
        f'你是《{topic}》政治制度分析专家。禁止：{";".join(fb[:3])}。'
        f'请从一个学术界几乎无人触及、极度冷门的政治制度子问题，提出对《{topic}》的全新分析角度。'
        f'角度必须具体到可论证，给出2条独特论据。'
        f'JSON: {{"angle_title":"...","thesis":"...","evidence":["",""]}}'
    ),
    "经济财政": lambda topic, fb: (
        f'你是《{topic}》经济史专家。禁止：{";".join(fb[1:4])}。'
        f'请找到一个被经济史学者长期忽视的财政细节，提出颠覆性的分析角度。'
        f'必须给出具体数据或史料支持。JSON同上。'
    ),
    "军事战略": lambda topic, fb: (
        f'你是《{topic}》军事战略专家。禁止：{";".join(fb[:3])}。'
        f'请从一个极其冷门的军事后勤或技术细节切入，提出与众不同的分析。避开常见军事论述。JSON同上。'
    ),
    "文化社会": lambda topic, fb: (
        f'你是《{topic}》文化社会史专家。禁止：{";".join(fb[2:5])}。'
        f'请关注被主流叙事忽略的边缘群体或亚文化现象，从中提取独特分析角度。JSON同上。'
    ),
    "关键人物": lambda topic, fb: (
        f'你是《{topic}》人物研究专家。禁止：{";".join(fb[1:4])}。'
        f'请聚焦一个常被忽视的次要人物或幕僚，从这个边缘视角看整体事件。JSON同上。'
    ),
    "技术演进": lambda topic, fb: (
        f'你是《{topic}》技术史专家。禁止：{";".join(fb[2:5])}。'
        f'请从技术演进路径中提取一个被忽视的技术决定论视角。必须说明具体技术如何左右了历史走向。JSON同上。'
    ),
    "地理环境": lambda topic, fb: (
        f'你是《{topic}》历史地理学专家。禁止：{";".join(fb[2:5])}。'
        f'请聚焦地理约束中一个被忽视的变量，论证地理因素如何重塑了《{topic}》的进程。给出具体地名和地形数据。JSON同上。'
    ),
}


def build_round1_prompts(topic: str, forbidden: list[str]) -> dict[str, str]:
    if not forbidden:
        forbidden = [""]
    return {dim: fn(topic, forbidden) for dim, fn in ROUND1_TEMPLATES.items()}


def build_round2_prompt(topic: str, dim: str, my_proposal: dict, other_proposals: dict[str, str]) -> str:
    my_thesis = my_proposal.get("thesis", "")
    others_text = "; ".join([f"[{k}]: {v}" for k, v in other_proposals.items()])

    return (
        f'你是《{topic}》{dim}专家。你的初步角度是：{my_thesis}\n'
        f'其他专家的角度：{others_text}\n\n'
        f'现在进行第二轮辩论：你的角度是否与其他人有重叠？如果有，请主动偏离。'
        f'如果没有，请进一步深挖。用其他人的视角批判你自己的角度，找出弱点，'
        f'然后在修正后提出一个更加锋利、更具原创性的版本。\n\n'
        f'输出JSON：{{"angle_title":"修正后的角度","thesis":"更锋利的论点",'
        f'"evidence":["论据1","论据2"],"debate_note":"本轮修正说明"}}'
    )


def build_round3_prompt(topic: str, round2_angles: dict[str, dict]) -> str:
    all_text = ""
    for dim, a in round2_angles.items():
        all_text += f"[{dim}] {a.get('angle_title', '')}: {a.get('thesis', '')}\n"

    return (
        f'你是历史内容主编。以下是7位专家经两轮辩论后提出的《{topic}》分析角度：\n\n'
        f'{all_text}\n'
        f'请做以下判断：\n'
        f'1. 哪些角度仍流于表面或与已知饱和观点相似？直接淘汰。\n'
        f'2. 哪些角度真正具有原创性和深度？选出最优秀的3-4个。\n'
        f'3. 对选中的每个角度，给出1-10的新颖度评分和理由。\n\n'
        f'输出JSON数组：\n'
        f'[{{"dimension":"维度","angle_title":"标题","thesis":"论点","evidence":["","",""],'
        f'"novelty":8,"controversy":true,"selection_reason":"选中原因"}}]'
    )


def parse_json_response(raw: str) -> dict | list:
    text = raw.strip().replace("```json", "").replace("```", "")
    try:
        brace_pos = text.find("{")
        bracket_pos = text.find("[")
        if bracket_pos != -1 and (brace_pos == -1 or bracket_pos < brace_pos):
            start = bracket_pos
            end = text.rindex("]") + 1
            return json.loads(text[start:end])
        elif brace_pos != -1:
            start = brace_pos
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        return {"raw": text[:500]}
    except (json.JSONDecodeError, ValueError):
        return {"raw": text[:500]}


def filter_valid_angles(angles: list[dict]) -> list[dict]:
    blocked = ["无法处理", "抱歉", "我不能", "I cannot", "unable"]
    result = []
    for a in angles:
        thesis = a.get("thesis", "")
        if not thesis or len(thesis) <= 20:
            continue
        blocked_match = False
        for kw in blocked:
            if kw.lower() in thesis.lower():
                blocked_match = True
                break
        if blocked_match:
            continue
        result.append(a)
    return result


def extract_main_topic(content: str, llm_fn=None) -> str:
    if llm_fn:
        prompt = (
            f'从以下内容中提取核心主主题。只返回主题名称，不超过50字。\n'
            f'不要加任何解释或格式标记。\n\n'
            f'{content[:3000]}'
        )
        try:
            raw = llm_fn(prompt, temperature=0.3, max_tokens=100)
            return raw.strip().replace('"', '').replace("'", "")[:80]
        except Exception:
            pass

    sentences = re.split(r'[。！？\n]', content)
    for s in sentences:
        s = s.strip()
        if len(s) >= 6:
            return s[:80]
    return content.strip()[:80]


def extract_key_points(content: str, llm_fn=None) -> list[str]:
    if llm_fn:
        prompt = (
            f'从以下内容中提取3-5个关键论点。每行一个，不要编号，不要加任何解释。\n\n'
            f'{content[:3000]}'
        )
        try:
            raw = llm_fn(prompt, temperature=0.3, max_tokens=500)
            lines = [l.strip().lstrip("1234567890.、- ").strip() for l in raw.strip().split("\n")]
            return [l for l in lines if len(l) >= 4][:5]
        except Exception:
            pass

    points = []
    for marker in ["第一", "第二", "第三", "第四", "第五", "1.", "2.", "3."]:
        for line in content.split("\n"):
            if line.strip().startswith(marker):
                pt = line.strip().lstrip("1234567890.、- ").strip()
                if len(pt) >= 4:
                    points.append(pt)
    if not points:
        points = [content.strip()[:200]]
    return points[:5]


class ForumEngine:
    def __init__(self, llm_fn):
        self.llm_fn = llm_fn

    def run_debate(self, topic: str, forbidden: list[str] | None = None) -> list[dict]:
        if forbidden is None:
            forbidden = [""]

        round1 = {}
        round1_prompts = build_round1_prompts(topic, forbidden)
        for dim, prompt in round1_prompts.items():
            resp = self.llm_fn(prompt, temperature=0.95, max_tokens=500)
            parsed = parse_json_response(resp)
            round1[dim] = parsed if isinstance(parsed, dict) else {"thesis": resp[:200]}

        round2 = {}
        for dim, my_proposal in round1.items():
            other_proposals = {}
            for k, v in round1.items():
                if k != dim:
                    other_proposals[k] = v.get("thesis", "") if isinstance(v, dict) else str(v)[:100]
            prompt = build_round2_prompt(topic, dim, my_proposal if isinstance(my_proposal, dict) else {}, other_proposals)
            resp = self.llm_fn(prompt, temperature=0.9, max_tokens=500)
            parsed = parse_json_response(resp)
            round2[dim] = parsed if isinstance(parsed, dict) else my_proposal if isinstance(my_proposal, dict) else {"thesis": resp[:200]}

        prompt = build_round3_prompt(topic, round2)
        resp = self.llm_fn(prompt, temperature=0.7, max_tokens=2000)
        final_parsed = parse_json_response(resp)

        if isinstance(final_parsed, list):
            final_angles = final_parsed
        else:
            final_angles = []
            for k, v in round2.items():
                thesis = v.get("thesis", "") if isinstance(v, dict) else str(v)
                if thesis and len(thesis) > 10:
                    final_angles.append({
                        "dimension": k,
                        "angle_title": v.get("angle_title", k) if isinstance(v, dict) else k,
                        "thesis": thesis,
                        "evidence": v.get("evidence", []) if isinstance(v, dict) else [],
                        "novelty": 7,
                        "controversy": True,
                    })

        return filter_valid_angles(final_angles)
