"""
管道对接模块
在你的Python工作流中使用:
    from connector import get_content
    data = get_content("安史之乱")
    # data["article"]["sections"][0]["body"] → 直接放入公众号编辑器
    # data["video_script"]["segments"] → 直接给剪辑师
"""
import json, requests

API_URL = "http://124.174.42.6:5050"

def get_content(topic: str, include_video: bool = True) -> dict:
    """获取完整内容包（角度+图文+脚本）"""
    resp = requests.post(
        f"{API_URL}/generate",
        json={"topic": topic, "include_video": include_video},
        timeout=300
    )
    resp.raise_for_status()
    return resp.json()

def get_article_markdown(topic: str) -> str:
    """获取公众号Markdown格式图文（可直接粘贴）"""
    data = get_content(topic, include_video=False)
    art = data["article"]
    md = f"# {art['recommended_title']}\n\n"
    md += f"*{art['subtitle']}*\n\n"
    for sec in art["sections"]:
        md += f"## {sec['heading']}\n\n"
        md += f"> {sec['hook']}\n\n"
        md += f"{sec['body']}\n\n"
        if sec.get("interaction"):
            md += f"💬 {sec['interaction']}\n\n"
    md += "---\n"
    md += "### 📚 延伸阅读\n"
    for r in art.get("extended_reading", []):
        md += f"- {r}\n"
    md += "\n"
    for q in art.get("golden_quotes", []):
        md += f"> {q}\n\n"
    return md

def get_video_brief(topic: str) -> str:
    """获取视频号制作简报（给剪辑师的）"""
    data = get_content(topic, include_video=True)
    vs = data["video_script"]
    lines = [f"# {topic} — 视频分镜脚本 ({vs['total_duration']}s)\n"]
    for seg in vs["segments"]:
        lines.append(f"**{seg['time']}**")
        lines.append(f"- 画面: {seg['visual']}")
        lines.append(f"- 旁白: {seg['narration']}")
        lines.append("")
    lines.append("## 核心记忆点")
    for mp in vs.get("memorable_points", []):
        lines.append(f"- {mp}")
    return "\n".join(lines)

# CLI
if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "安史之乱"
    print(get_article_markdown(topic))
