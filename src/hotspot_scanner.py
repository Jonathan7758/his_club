"""
历史热点扫描器
从MindSpider的NewsNow API获取全网热点，LLM过滤历史相关话题
"""
import sys, json, requests
from openai import OpenAI
from database import save_hotspot_scan, save_post
from douban import enrich_hotspot_with_douban

client = OpenAI(
    api_key="sk-3ded85b7ccb4438fbe95ec7d45416e44",
    base_url="https://api.deepseek.com/v1"
)

NEWS_API = "https://newsnow.busiyi.world"
SOURCES = ["zhihu", "weibo", "bilibili-hot-search", "toutiao", "douyin", "tieba"]

def fetch_hot_items() -> list[dict]:
    """从NewsNow API获取全网热点（逐个平台拉取）"""
    items = []
    for src in SOURCES:
        try:
            url = f"{NEWS_API}/api/s?id={src}&latest"
            r = requests.get(url, headers={"Referer": NEWS_API, "User-Agent": "Mozilla/5.0"}, timeout=10)
            data = r.json()
            for item in data.get("items", []):
                items.append({
                    "platform": src,
                    "title": item.get("title", "")[:120],
                    "heat": item.get("extra", {}).get("info", "") if isinstance(item.get("extra"), dict) else ""
                })
        except:
            pass
    return items if items else [{"platform": "error", "title": "API无数据", "heat": ""}]

def filter_history_topics(hot_items: list[dict], max_topics: int = 20) -> list[dict]:
    """用LLM从全网热点中筛选历史相关话题"""
    items_text = "\n".join([
        f"[{i['platform']}] {i['title']}"
        for i in hot_items[:300]
    ])
    
    prompt = f"""以下是今日全网热点（来自微博、知乎、B站、头条、抖音等12个平台）。请从中筛选出与"历史"相关的话题。

历史相关话题包括但不限于：
- 历史事件讨论/争议（如"xxx真相""xxx之谜"）
- 考古新发现/文物展出
- 历史人物相关热点
- 历史纪录片/影视剧热议
- 历史纪念日
- 传统文化/非遗传承
- 博物馆展览
- 历史类书籍/文章讨论
- 任何可以用历史学分析方法深度解读的当下话题

请输出最多{max_topics}个话题，按历史相关度和潜在公众号受众吸引力排序。
输出JSON数组：[
  {{"topic": "话题标题", "relevance": "历史关联说明(30字)", "source_platform": "来源平台", "score": 8}}
]

今日热点：
{items_text[:8000]}"""
    
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2000
    )
    text = resp.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "")
    
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        return json.loads(text[start:end])
    except:
        return [{"topic": "解析失败", "relevance": text[:100], "source_platform": "unknown", "score": 0}]

def scan_history_hotspots() -> dict:
    """完整的历史热点扫描"""
    print("获取全网热点...")
    hot_items = fetch_hot_items()
    print(f"  共 {len(hot_items)} 条")

    # 原始热点 → posts 表
    print("  热点落库 posts...")
    post_count = 0
    for item in hot_items:
        if item.get("platform") != "error":
            pid = save_post({
                "platform": item["platform"],
                "title": item["title"],
                "content": item.get("heat", ""),
                "url": "",
                "author": "",
            })
            if pid:
                post_count += 1
    print(f"  已存 {post_count} 条帖子")
    
    print("筛选历史相关话题...")
    history_topics = filter_history_topics(hot_items, max_topics=15)
    
    result = {
        "total_items_scanned": len(hot_items),
        "history_topics": history_topics,
        "top_5": history_topics[:5] if len(history_topics) >= 5 else history_topics,
        "suggested_next": history_topics[0] if history_topics else None
    }

    try:
        n = save_hotspot_scan(result, window_type="daily")
        print(f"  已存入数据库 {n} 条热点")
    except Exception as e:
        print(f"  DB保存失败: {e}")

    try:
        result = enrich_hotspot_with_douban(result)
    except Exception as e:
        print(f"  豆瓣辅证失败: {e}")
    
    return result

if __name__ == "__main__":
    result = scan_history_hotspots()
    print(json.dumps(result, ensure_ascii=False, indent=2))
