"""
DocExporter v4.0 — MD系列设计文档导出
汇总主主题/评分/子系列/子评分 → 生成标准Markdown文档
"""
from datetime import datetime


def format_md_header(main_topic: str, date_str: str, total_score: float) -> str:
    return (
        f"# 微信公众号系列设计文档\n\n"
        f"## 基本信息\n\n"
        f"- **主主题**: {main_topic}\n"
        f"- **分析时间**: {date_str}\n"
        f"- **综合评分**: {total_score}/10\n\n"
    )


def format_scores_section(scores: dict) -> str:
    if not scores:
        return ""

    h = scores.get("hot_score", {})
    u = scores.get("unique_score", {})
    s = scores.get("spread_score", {})

    lines = [
        "## 多维度评分\n",
        "| 维度 | 评分 | 证据 |",
        "|------|------|------|",
        f"| 互联网热度 | {h.get('value', 'N/A')} | {h.get('evidence', '')} |",
        f"| 角度独特度 | {u.get('value', 'N/A')} | {u.get('evidence', '')} |",
        f"| 预测传播热度 | {s.get('value', 'N/A')} | {s.get('evidence', '')} |",
        f"| **综合评分** | **{scores.get('total_score', 'N/A')}** | |",
        "",
    ]

    return "\n".join(lines)


def format_sub_series_table(sub_series: list[dict]) -> str:
    if not sub_series:
        return ""

    lines = ["## 子系列设计\n"]

    labels = {
        "政治制度": "政", "经济财政": "经",
        "军事战略": "军", "文化社会": "文",
        "关键人物": "人", "技术演进": "技", "地理环境": "地",
    }

    for i, item in enumerate(sub_series, 1):
        dim = item.get("dimension", "")
        label = labels.get(dim, dim[:2])
        name = item.get("name", "")
        viewpoint = item.get("viewpoint", "")
        outline = item.get("outline", [])
        quotes = item.get("quotes", [])
        scores = item.get("scores", {})

        lines.append(f"### {i}. [{label}] {name}\n")
        lines.append(f"- **核心观点**: {viewpoint}\n")

        if outline:
            lines.append("- **内容大纲**:")
            for j, ol in enumerate(outline, 1):
                lines.append(f"  {j}. {ol}")
            lines.append("")

        if quotes:
            lines.append("- **金句**:")
            for q in quotes:
                lines.append(f"  - \"{q}\"")
            lines.append("")

        if scores:
            total = scores.get("total_score", "N/A")
            lines.append(
                f"- **评分**: 热度 {scores.get('hot_score', {}).get('value', 'N/A')}"
                f" | 独特度 {scores.get('unique_score', {}).get('value', 'N/A')}"
                f" | 传播 {scores.get('spread_score', {}).get('value', 'N/A')}"
                f" | **综合 {total}**\n"
            )

    return "\n".join(lines)


def format_sub_score_table(sub_series: list[dict], sub_scores: list[dict] | None) -> str:
    if not sub_series or not sub_scores:
        return ""

    lines = [
        "## 子主题评分总览\n",
        "| # | 维度 | 子主题 | 热度 | 独特度 | 传播 | 综合 |",
        "|---|------|--------|------|--------|------|------|",
    ]

    for sc in sub_scores:
        idx = sc.get("sub_index", 0)
        if idx < len(sub_series):
            item = sub_series[idx]
            dim = item.get("dimension", "")
            name = item.get("name", "")
            labels = {"政治制度": "政", "经济财政": "经", "军事战略": "军", "文化社会": "文", "关键人物": "人", "技术演进": "技", "地理环境": "地"}
            label = labels.get(dim, dim[:2])
        else:
            dim = "?"
            name = "?"
            label = "?"

        lines.append(
            f"| {idx + 1} | {label} | {name} | "
            f"{sc.get('hot_score', 'N/A')} | {sc.get('unique_score', 'N/A')} | "
            f"{sc.get('spread_score', 'N/A')} | {sc.get('total_score', 'N/A')} |"
        )

    lines.append("")
    return "\n".join(lines)


class DocExporter:
    def export(self, session_data: dict) -> str:
        main_topic = session_data.get("main_topic", "未命名主题")
        content = session_data.get("content", "")
        key_points = session_data.get("key_points", [])
        scores = session_data.get("scores", {})
        sub_series = session_data.get("sub_series", [])
        sub_scores = session_data.get("sub_scores", [])

        total_score = scores.get("total_score", 0.0) if scores else 0.0
        date_str = datetime.now().strftime("%Y-%m-%d")

        sections = [
            format_md_header(main_topic, date_str, total_score),
        ]

        if content:
            preview = content[:300].replace("\n", " ")
            sections.append(
                "## 原始输入摘要\n\n"
                f"> {preview}...\n\n"
            )

        if key_points:
            sections.append("## 关键论点\n")
            for i, kp in enumerate(key_points, 1):
                sections.append(f"{i}. {kp}")
            sections.append("")

        if scores:
            sections.append(format_scores_section(scores))

        if sub_series:
            if sub_scores:
                for sc in sub_scores:
                    idx = sc.get("sub_index", 0)
                    sub_scores_dict = {
                        "hot_score": {"value": sc.get("hot_score", 0)},
                        "unique_score": {"value": sc.get("unique_score", 0)},
                        "spread_score": {"value": sc.get("spread_score", 0)},
                        "total_score": sc.get("total_score", 0),
                    }
                    if idx < len(sub_series):
                        sub_series[idx]["scores"] = sub_scores_dict

            sections.append(format_sub_series_table(sub_series))

        if sub_series and sub_scores:
            sections.append(format_sub_score_table(sub_series, sub_scores))

        return "\n".join(sections)

    def generate_filename(self, main_topic: str) -> str:
        safe_name = main_topic.replace(" ", "_").replace("/", "_").replace("\\", "_")[:40]
        date_str = datetime.now().strftime("%Y%m%d")
        return f"{safe_name}_系列设计_{date_str}.md"
