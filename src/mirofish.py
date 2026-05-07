"""
MiroFish Lite v1.0 — "历史如果"推演引擎
7方利益Agent博弈 + 5轮推演 → 多条历史分岔叙事
用于: 公众号差异化选题 + 深度内容原料
"""
import json
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)
MODEL = "deepseek-chat"

STAKEHOLDERS = {
    "皇室/统治层": "你代表皇帝和皇族利益。关注权力稳定、继承合法性、中央控制力。决策逻辑：优先维系统治，即使牺牲其他阶层。",
    "官僚/士大夫": "你代表文官集团和科举精英。关注制度合法性、俸禄保障、政治理想。决策逻辑：在效忠皇权和维护政体理性之间摇摆。",
    "军事将领": "你代表军队和边将。关注军饷、后勤、战功晋升。决策逻辑：忠诚取决于利益保障，边缘化则易倒戈。",
    "财政/商人": "你代表商业势力（盐商/票号/海商）。关注税收负担、贸易路线、货币稳定。决策逻辑：逐利驱动，但混乱期倾向自保。",
    "基层/农民": "你代表底层劳动人口。关注赋税、徭役、天灾救济。决策逻辑：生存优先，压迫超过阈值则爆发。",
    "周边势力": "你代表邻国/游牧/朝贡国。关注边境稳定、朝贡利益、军力对比。决策逻辑：中央衰弱则趁机蚕食，中央强大则归附。",
    "知识/文化圈": "你代表士人、史官、文人。关注思想潮流、历史评价、文化正统。决策逻辑：记录评判，影响后世叙事，间接塑造舆论。",
}


def _call_llm(prompt: str, temperature: float = 0.8, max_tokens: int = 1500) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content


def _parse_json(text: str) -> dict | list:
    """安全解析JSON"""
    text = text.strip().replace("```json", "").replace("```", "")
    try:
        if text.strip().startswith("["):
            start = text.index("[")
            end = text.rindex("]") + 1
            return json.loads(text[start:end])
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except:
        return {"raw": text[:500]}


def _init_counterfactual(topic: str, what_if: str) -> dict:
    """生成初始反事实场景设定"""
    prompt = f"""请在历史事件《{topic}》的语境下，构建一个关键反事实场景。

反事实条件：{what_if}

请输出：
1. 具体的历史分岔点（哪一年、哪个决策、谁做了什么不同的事）
2. 分岔点后的初始状态（哪些力量被削弱、哪些被增强、出现了什么新变量）
3. 这个变化对7方利益体的第一轮冲击分别是什么

输出JSON：
{{
  "divergence_point": "公元xxx年，xxx做了/没有做xxx",
  "initial_state": "分岔后的初始局面描述(100字)",
  "primary_shock": "对整个系统的第一波冲击描述(50字)",
  "stakeholder_impacts": {{
    "皇室/统治层": "冲击描述(30字)",
    "官僚/士大夫": "冲击描述(30字)",
    "军事将领": "冲击描述(30字)",
    "财政/商人": "冲击描述(30字)",
    "基层/农民": "冲击描述(30字)",
    "周边势力": "冲击描述(30字)",
    "知识/文化圈": "冲击描述(30字)"
  }}
}}"""

    resp = _call_llm(prompt, temperature=0.8, max_tokens=1500)
    return _parse_json(resp)


def _round_action(stakeholder: str, persona: str, scenario: dict, prev_actions: list[str], round_num: int) -> str:
    """单个利益体在当前轮次的决策"""
    prev_text = "\n".join(prev_actions[-6:]) if prev_actions else "（初始局面）"
    state_desc = json.dumps(scenario, ensure_ascii=False)[:1500]

    prompt = f"""你是{stakeholder}的利益代表。

身份设定：{persona}

当前历史推演场景：
{state_desc[:1200]}

此前各方行动：
{prev_text}

现在是第{round_num}轮推演。根据你的身份和此前的变化，请做出本轮决策。决策需要：
1. 符合你的阶层立场和利益逻辑
2. 对前几轮的变化做出反应
3. 不要做违反你阶层根本利益的事

输出JSON：
{{"stakeholder":"{stakeholder}","round":{round_num},"action":"本轮的决策或反应(50字)","reasoning":"决策逻辑(30字)","alliance":"本轮与谁结盟或对抗(15字)","red_line":"你的底线是什么(20字)"}}"""

    resp = _call_llm(prompt, temperature=0.85, max_tokens=400)
    return resp


def _round_summary(round_num: int, actions: list[str], scenario: dict, topic: str, what_if: str) -> dict:
    """推演主持人：总结本轮变化，更新全局状态"""
    actions_text = "\n".join(actions[-7:])

    prompt = f"""你是历史推演主持人。《{topic}》的反事实条件下({what_if})，第{round_num}轮各方已完成行动。

各方行动：
{actions_text}

请做以下分析：
1. 本轮出现了哪些关键博弈结果？
2. 谁得益、谁受损？
3. 是否出现了不可逆的转折点？
4. 系统整体稳定性如何变化（0-100分）？
5. 综合各方立场，本轮最可能的历史走向是什么？

输出JSON：
{{
  "round": {round_num},
  "key_outcomes": ["本轮关键结果1(30字)","结果2","结果3"],
  "winners": ["得益方1"],
  "losers": ["受损方1"],
  "tipping_point": "是否出现不可逆转折(有则描述，无则:无)",
  "stability": 65,
  "narrative_direction": "推演走向描述(80字)",
  "updated_state": "新一轮系统状态(80字)"
}}"""

    resp = _call_llm(prompt, temperature=0.7, max_tokens=1000)
    return _parse_json(resp)


def _synthesize_narratives(rounds: list[dict], topic: str, what_if: str, initial: dict) -> dict:
    """最终合成：对推演结果生成多条可能叙事+公众号选题"""
    rounds_text = json.dumps(rounds, ensure_ascii=False, indent=2)[:4000]
    initial_text = json.dumps(initial, ensure_ascii=False)

    prompt = f"""你是历史叙事专家。以下是对《{topic}》的反事实推演({what_if})的完整过程。

初始设定：
{initial_text[:1500]}

推演过程（{len(rounds)}轮）：
{rounds_text[:4000]}

请完成以下任务：
1. 识别推演中共出现过几个关键分岔点（每个分岔点可能导致不同结局）
2. 为每个主要可能性生成一条完整的"历史如果"叙事（类似《万历十五年》风格）
3. 分析：为什么现实中历史走了另一条路？（对比分析）
4. 从这个推演中提炼出3个公众号选题（带角度建议）

输出JSON：
{{
  "topic": "{topic}",
  "counterfactual": "{what_if}",
  "simulation_rounds": {len(rounds)},
  "divergence_paths": [
    {{
      "path_name": "叙事A的标题",
      "probability_estimate": 0.35,
      "narrative": "完整的'历史如果'叙事(300-500字，文学化叙述)《万历十五年》风格",
      "key_moments": ["关键节点1(30字)","关键节点2"],
      "final_state": "推演终点描述(50字)"
    }}
  ],
  "comparison_with_reality": {{
    "why_different": "为什么现实历史走了另一条路(150字)",
    "critical_decision": "现实中是谁做的什么决策改变了走向",
    "lesson": "这段推演给我们的启示(80字)"
  }},
  "wechat_topics": [
    {{
      "title": "选题标题1",
      "angle": "独特分析角度(50字)",
      "hooking_question": "钩子问题(30字)",
      "appeal": "受众吸引力理由(30字)"
    }}
  ]
}}"""

    resp = _call_llm(prompt, temperature=0.75, max_tokens=4000)
    return _parse_json(resp)


def mirofish_simulate(topic: str, what_if: str = None, rounds: int = 5) -> dict:
    """
    MiroFish Lite 历史推演引擎

    Args:
        topic: 历史事件 e.g. "安史之乱"
        what_if: 反事实条件 e.g. "如果哥舒翰没有在潼关贸然出击"
        rounds: 推演轮数 (3-7)
    """
    if what_if is None:
        what_if = _suggest_what_if(topic)

    rounds = max(3, min(7, rounds))

    print(f"[MiroFish] 推演: {topic}")
    print(f"[MiroFish] 反事实: {what_if}")
    print(f"[MiroFish] 轮数: {rounds}")

    # Phase 1: 初始化反事实场景
    print("  Phase 1: 初始化反事实场景...")
    initial = _init_counterfactual(topic, what_if)
    scenario = initial

    # Phase 2: 多轮Agent博弈
    all_rounds = []
    agent_actions = []

    for r in range(1, rounds + 1):
        print(f"  Phase 2: 第{r}轮推演...")
        round_actions = []

        for stake, persona in STAKEHOLDERS.items():
            action_raw = _round_action(stake, persona, scenario, agent_actions, r)
            try:
                action_json = _parse_json(action_raw)
                action_text = json.dumps(action_json, ensure_ascii=False)
            except:
                action_text = action_raw[:300]
            round_actions.append(action_text)
            agent_actions.append(action_text)

        summary = _round_summary(r, round_actions, scenario, topic, what_if)
        all_rounds.append(summary)
        scenario = summary  # 更新场景状态

    # Phase 3: 叙事合成
    print("  Phase 3: 合成推演叙事...")
    synthesis = _synthesize_narratives(all_rounds, topic, what_if, initial)

    result = {
        "topic": topic,
        "counterfactual": what_if,
        "simulation_rounds": rounds,
        "initial_scenario": initial,
        "round_details": all_rounds,
        "synthesis": synthesis,
        "meta": {
            "engine": "MiroFish Lite v1.0",
            "stakeholders": len(STAKEHOLDERS),
            "model": "deepseek-chat"
        }
    }

    print(f"[MiroFish] 推演完成")
    return result


def _suggest_what_if(topic: str) -> str:
    """自动生成一个有价值的反事实命题"""
    prompt = f"""你是历史反事实推演专家。针对《{topic}》，请提出一个最具思辨价值的 "如果..." 命题。

要求：
- 必须是历史学界曾讨论过的反事实假设
- 这个假设的变化应该足够微小（一个人的决策、一场小战斗的胜负），但后果足够深远
- 可以用一句话表达
- 这个命题适合作为公众号的钩子标题

请直接输出"如果..."格式的一句话，不要解释。"""

    resp = _call_llm(prompt, temperature=0.9, max_tokens=200)
    resp = resp.strip().strip("\"'")
    if not resp.startswith("如果"):
        resp = f"如果{resp}"
    return resp[:100]


def quick_prediction(topic: str) -> dict:
    """轻量预测: 单次调用LLM直接生成"历史如果"思路，用于快速选题评估"""
    prompt = f"""你是历史反事实推演专家。针对《{topic}》，快速生成3个"历史如果"选题。

每个选题格式：
- 反事实命题（"如果...") 
- 可能的推演方向（50字）
- 公众号选题建议（角度+标题建议）

输出JSON数组：
[
  {{"what_if":"如果...","direction":"推演方向","title_suggestion":"公众号标题建议","appeal":"受众吸引力(20字)"}}
]"""

    resp = _call_llm(prompt, temperature=0.85, max_tokens=1500)
    result = _parse_json(resp)
    if isinstance(result, dict):
        return {"raw": resp}
    return result


def mirofish_to_angles(synthesis: dict, topic: str) -> list[dict]:
    """将 MiroFish 推演合成结果转为 ForumEngine 兼容的角度列表"""
    angles = []
    paths = synthesis.get("divergence_paths", [])

    for i, path in enumerate(paths):
        narrative = path.get("narrative", "")
        key_moments = path.get("key_moments", [])
        final_state = path.get("final_state", "")

        # 从叙事和关键节点中提取分析角度
        prompt = f"""从以下"历史如果"推演叙事中，提取1个可论证的历史分析角度。

推演路径：{path.get('path_name', '')}
全文叙事：{narrative[:800]}
关键节点：{'; '.join(key_moments[:2])}
终局状态：{final_state}

请输出一个可用于公众号深度分析的角度，需包含：论点、2条具体论据，基于推演中揭示的历史规律。
JSON：{{"angle_title":"角度标题","thesis":"论点(80字)","evidence":["论据1","论据2"]}}"""

        resp = _call_llm(prompt, temperature=0.7, max_tokens=600)
        angle = _parse_json(resp)
        if isinstance(angle, dict) and angle.get("thesis"):
            angle["dimension"] = f"历史如果·路径{i+1}"
            angle["source"] = "mirofish"
            angle["divergence_path"] = path.get("path_name", "")
            angle["novelty"] = 9  # MiroFish 推演角度天然高新颖度
            angles.append(angle)

    # 补充对比现实的角度
    comparison = synthesis.get("comparison_with_reality", {})
    why_diff = comparison.get("why_different", "")
    lesson = comparison.get("lesson", "")
    critical = comparison.get("critical_decision", "")

    if why_diff:
        angles.append({
            "dimension": "历史如果·现实对比",
            "angle_title": "为什么现实走了另一条路",
            "thesis": f"推演揭示：{critical_decision}是关键分岔点。{lesson}",
            "evidence": [why_diff[:150], lesson[:150]],
            "source": "mirofish",
            "novelty": 8,
            "controversy": True
        })

    return angles


def mirofish_generate(topic: str, what_if: str = None, rounds: int = 5) -> dict:
    """
    MiroFish 全流程: 推演 → 角度提取 → 文章生成
    一键产出"历史如果"公众号内容
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Phase 1: MiroFish 推演
    mirofish_result = mirofish_simulate(topic, what_if, rounds=rounds)
    synthesis = mirofish_result.get("synthesis", {})

    # Phase 2: 推演叙事 → 分析角度
    print("[MiroFish] 提取推演角度...")
    angles = mirofish_to_angles(synthesis, topic)

    # Phase 3: 角度 → 文章生成
    print("[MiroFish] 生成公众号内容...")
    try:
        from generator import generate_article, generate_video_script, select_best_angles

        article = generate_article(f"{topic}（历史如果推演）", angles)
        video = generate_video_script(f"{topic}（历史如果推演）", angles)

        return {
            "topic": topic,
            "counterfactual": synthesis.get("counterfactual", what_if or ""),
            "mirofish": {
                "divergence_paths": synthesis.get("divergence_paths", []),
                "comparison": synthesis.get("comparison_with_reality", {}),
                "wechat_topics": synthesis.get("wechat_topics", []),
            },
            "angles": angles,
            "article": article,
            "video_script": video,
            "meta": {
                "pipeline": "mirofish→generator",
                "angles_count": len(angles),
                "simulation_rounds": rounds,
                "format_version": "3.0+mirofish"
            }
        }
    except Exception as e:
        return {
            "topic": topic,
            "mirofish": mirofish_result,
            "angles": angles,
            "error": f"文章生成失败: {e}"
        }


if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "安史之乱"
    what_if = sys.argv[2] if len(sys.argv) > 2 else None

    print("=== MiroFish Lite 快速预测 ===")
    predictions = quick_prediction(topic)
    print(json.dumps(predictions, ensure_ascii=False, indent=2))

    print("\n=== MiroFish Lite 完整推演 (3轮) ===")
    result = mirofish_simulate(topic, what_if, rounds=3)
    # 只打印合成结果
    print(json.dumps(result.get("synthesis", {}), ensure_ascii=False, indent=2))
