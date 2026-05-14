"""
搜狗搜索工具 v4.0
搜狗微信搜索 + 搜狗网页搜索 — 从 generator.py 提取独立为公共模块
供 engines / analytics / generator 等模块共享使用
"""
import requests
from bs4 import BeautifulSoup


def weixin_search(query: str, max_results: int = 10) -> list[str]:
    """搜狗微信搜索——直接在公众号池子里查竞品（新颖度验证最佳来源）"""
    try:
        url = f"https://weixin.sogou.com/weixin?type=2&query={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for li in soup.select(".news-list li")[:max_results]:
            title_el = li.select_one("h3 a, .tit a")
            desc_el = li.select_one("p, .txt-info")
            if title_el:
                title = title_el.get_text(strip=True)
                desc = desc_el.get_text(strip=True)[:200] if desc_el else ""
                results.append(f"{title} | {desc}")
        return results if results else ["无公众号文章"]
    except Exception:
        return []


def sogou_web_search(query: str, max_results: int = 10) -> list[str]:
    """搜狗网页搜索——查全网中文内容（知乎、豆瓣等平台）"""
    try:
        url = f"https://www.sogou.com/web?query={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".vrwrap, .rb, .result")[:max_results]:
            title_el = item.select_one("h3 a, .vr-title, .vrTitle a")
            desc_el = item.select_one(".star-wiki, .str-text, .space-txt, .vr_summary, p")
            if title_el:
                title = title_el.get_text(strip=True)
                desc = desc_el.get_text(strip=True)[:200] if desc_el else ""
                results.append(f"{title} {desc}")
        return results
    except Exception:
        return []
