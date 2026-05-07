"""
豆瓣数据爬虫 v1.0
历史书评 + 文化小组讨论 — 补全文化圈数据源
用于: 热点辅证 + 选题发现 + 读者情绪信号
"""
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import save_post

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://book.douban.com/"
}


def search_history_books(topic: str, max_results: int = 10) -> list[dict]:
    """在豆瓣图书中搜索历史相关书籍"""
    try:
        url = f"https://book.douban.com/subject_search?search_text={requests.utils.quote(topic)}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for item in soup.select("li.subject-item")[:max_results]:
            title_el = item.select_one("h2 a, .info h2 a")
            rating_el = item.select_one(".rating_nums, .rating_nums")
            rating_count_el = item.select_one(".pl")
            pub_info = item.select_one(".pub, .pub")
            desc = item.select_one("p, .info p")

            title = title_el.get_text(strip=True) if title_el else ""
            rating = float(rating_el.get_text(strip=True)) if rating_el else 0
            count_text = rating_count_el.get_text(strip=True) if rating_count_el else ""
            count_match = re.search(r"(\d+)", count_text.replace(",", ""))
            rating_count = int(count_match.group(1)) if count_match else 0
            pub_text = pub_info.get_text(strip=True) if pub_info else ""
            description = desc.get_text(strip=True)[:200] if desc else ""

            if title:
                results.append({
                    "title": title,
                    "rating": rating,
                    "rating_count": rating_count,
                    "publisher": pub_text,
                    "description": description
                })

        return results
    except Exception as e:
        print(f"  豆瓣图书搜索失败: {e}")
        return []


def get_history_group_discussions(topic: str, max_results: int = 8) -> list[dict]:
    """在豆瓣小组中搜索历史讨论"""
    try:
        url = f"https://www.douban.com/search?q={requests.utils.quote(topic)}&cat=1013"
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for item in soup.select(".result")[:max_results]:
            title_el = item.select_one(".title a, h3 a")
            content_el = item.select_one(".content p, .content, .search-result .content")
            meta_el = item.select_one(".meta, .search-meta")

            title = title_el.get_text(strip=True) if title_el else ""
            content = content_el.get_text(strip=True)[:200] if content_el else ""
            meta = meta_el.get_text(strip=True) if meta_el else ""

            # Parse reply count from meta text like "15回应"
            reply_count = 0
            reply_match = re.search(r"(\d+)\s*[回评]", meta)
            if reply_match:
                reply_count = int(reply_match.group(1))

            if title:
                results.append({
                    "title": title,
                    "content": content,
                    "reply_count": reply_count,
                    "meta": meta
                })

        return results
    except Exception as e:
        print(f"  豆瓣小组搜索失败: {e}")
        return []


def get_history_tags_books(tag: str = "历史", max_results: int = 15) -> list[dict]:
    """按标签获取豆瓣历史类热门书籍"""
    try:
        url = f"https://book.douban.com/tag/{requests.utils.quote(tag)}?type=S"
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for item in soup.select("li.subject-item")[:max_results]:
            title_el = item.select_one("h2 a, .info h2 a")
            rating_el = item.select_one(".rating_nums")
            count_el = item.select_one(".pl")

            title = title_el.get_text(strip=True) if title_el else ""
            rating = float(rating_el.get_text(strip=True)) if rating_el else 0
            count_text = count_el.get_text(strip=True) if count_el else ""
            count_match = re.search(r"(\d+)", count_text.replace(",", ""))
            rating_count = int(count_match.group(1)) if count_match else 0

            if title and rating_count > 0:
                results.append({
                    "title": title,
                    "rating": rating,
                    "rating_count": rating_count,
                    "tag": tag
                })

        return sorted(results, key=lambda x: x["rating_count"], reverse=True)
    except Exception as e:
        print(f"  豆瓣标签搜索失败: {e}")
        return []


def scan_douban_hotspots(topics: list[str] = None) -> list[dict]:
    """扫描豆瓣历史文化圈当前活跃度，作为热点辅证"""
    if topics is None:
        topics = ["历史", "中国古代史", "考古", "唐宋", "明朝那些事儿", "三国", "罗马"]

    hotspots = []
    for topic in topics:
        try:
            books = search_history_books(topic, max_results=3)
            groups = get_history_group_discussions(topic, max_results=3)

            # 豆瓣结果 → posts 表
            for b in books:
                save_post({
                    "platform": "douban_book",
                    "title": b.get("title", ""),
                    "content": f"评分: {b.get('rating', 0)}, 评价数: {b.get('rating_count', 0)}, {b.get('description', '')}",
                    "url": "",
                    "author": b.get("publisher", ""),
                })
            for g in groups:
                save_post({
                    "platform": "douban_group",
                    "title": g.get("title", ""),
                    "content": g.get("content", ""),
                    "url": "",
                    "author": g.get("meta", ""),
                })

            if books:
                hot_score = 0
                for b in books:
                    score = b.get("rating", 0) * min(b.get("rating_count", 0) / 100, 10)
                    hot_score += score

                hotspots.append({
                    "topic": topic,
                    "platform": "douban_books",
                    "book_count": len(books),
                    "top_book": books[0]["title"] if books else "",
                    "top_rating": books[0]["rating"] if books else 0,
                    "heat_score": round(hot_score, 1),
                    "data": books
                })
        except:
            pass

    hotspots.sort(key=lambda x: x["heat_score"], reverse=True)
    return hotspots


def enrich_hotspot_with_douban(hotspot_result: dict) -> dict:
    """用豆瓣数据增强热点扫描结果"""
    topics = [h.get("topic", "") for h in hotspot_result.get("history_topics", [])[:5]]
    if not topics:
        return hotspot_result

    print("  豆瓣辅证扫描...")
    douban_data = scan_douban_hotspots(topics)

    # 匹配热点与豆瓣数据
    for h in hotspot_result.get("history_topics", []):
        h_topic = h.get("topic", "")
        for db in douban_data:
            if h_topic in db.get("topic", "") or any(w in db.get("topic", "") for w in h_topic):
                h["douban_books"] = db.get("data", [])[:3]
                h["douban_heat"] = db.get("heat_score", 0)
                break

    hotspot_result["douban_data"] = douban_data
    return hotspot_result


if __name__ == "__main__":
    print("=== 豆瓣历史书搜索 ===")
    books = search_history_books("安史之乱")
    print(json.dumps(books, ensure_ascii=False, indent=2))

    print("\n=== 豆瓣历史标签热门 ===")
    tags = get_history_tags_books("中国古代史", 5)
    print(json.dumps(tags, ensure_ascii=False, indent=2))

    print("\n=== 豆瓣小组讨论 ===")
    groups = get_history_group_discussions("安史之乱", 5)
    print(json.dumps(groups, ensure_ascii=False, indent=2))

    print("\n=== 豆瓣热度扫描 ===")
    scan = scan_douban_hotspots()
    print(json.dumps(scan, ensure_ascii=False, indent=2))
