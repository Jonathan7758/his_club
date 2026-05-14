"""
SeriesDesigner v4.0 — 主主题→7维子系列拆分
每个子系列: 名称(公众号化) / 核心观点 / 内容大纲 / 金句
"""
from forum_engine import DIMENSIONS, parse_json_response

DIMENSION_LABELS = {
    "政治制度": "政",
    "经济财政": "经",
    "军事战略": "军",
    "文化社会": "文",
    "关键人物": "人",
    "技术演进": "技",
    "地理环境": "地",
}


class SeriesDesigner:
    def __init__(self, llm_fn):
        self.llm_fn = llm_fn

    def design_series(self, main_topic: str, key_points: list[str] | None = None) -> list[dict]:
        if key_points is None:
            key_points = []

        key_text = "\n".join([f"- {p}" for p in key_points]) if key_points else "（无预提取论点）"

        results = []
        for dim in DIMENSIONS:
            label = DIMENSION_LABELS.get(dim, dim[:2])
            prompt = (
                f'你是一位微信公众号历史系列内容策划人。主主题是《{main_topic}》。\n'
                f'关键论点参考：\n{key_text}\n\n'
                f'现在请从「{dim}」维度，设计一个公众号化的子系列。\n\n'
                f'要求：\n'
                f'1. 子主题名称应适合公众号传播，有吸引力（格式："{label} | 吸引人的标题"或直接写标题）\n'
                f'2. 核心观点：1句话提炼该维度的核心分析论点\n'
                f'3. 内容大纲：3-5段的标题目录（每段10-20字）\n'
                f'4. 金句：2-3句适合传播的金句（口语化、有力量、可引用）\n\n'
                f'输出JSON：{{"name":"子主题名称","viewpoint":"1句话核心观点",'
                f'"outline":["段1标题","段2标题","段3标题","段4标题"],'
                f'"quotes":["金句1","金句2","金句3"]}}'
            )

            resp = self.llm_fn(prompt, temperature=0.8, max_tokens=800)
            parsed = parse_json_response(resp)

            if isinstance(parsed, dict):
                name = parsed.get("name", f"{label} | {dim}分析")
                parsed["dimension"] = dim
                parsed["name"] = name
                parsed.setdefault("viewpoint", "")
                parsed.setdefault("outline", [])
                parsed.setdefault("quotes", [])
                results.append(parsed)
            else:
                results.append({
                    "dimension": dim,
                    "name": f"{label} | {dim}分析",
                    "viewpoint": str(parsed)[:100],
                    "outline": [],
                    "quotes": [],
                })

        return results

    def modify_item(self, series: list[dict], index: int, **kwargs) -> list[dict]:
        if index < 0 or index >= len(series):
            raise IndexError(f"索引 {index} 超出范围 0-{len(series) - 1}")

        series = [dict(item) for item in series]
        for key, value in kwargs.items():
            if key in series[index]:
                series[index][key] = value

        return series

    def get_summary(self, series: list[dict]) -> str:
        lines = ["子系列概览："]
        for item in series:
            dim = item.get("dimension", "")
            name = item.get("name", "")
            lines.append(f"- [{dim}] {name}")
        return "\n".join(lines)
