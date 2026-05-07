"""
公众号后台数据回传对接 v1.0
微信公众平台 API — Token管理 / 素材上传 / 草稿发布 / 数据回传

环境变量:
  WECHAT_APPID      — 公众号 AppID
  WECHAT_APPSECRET  — 公众号 AppSecret
  WECHAT_TOKEN      — 服务器配置 Token (消息校验用，可选)

使用:
  from wechat_backend import WeChatClient
  wx = WeChatClient()
  wx.push_draft(title, content, thumb_media_id="...")
"""
import json
import os
import time
import hashlib
import threading
from datetime import datetime
from typing import Optional


WECHAT_APPID = os.environ.get("WECHAT_APPID", "")
WECHAT_APPSECRET = os.environ.get("WECHAT_APPSECRET", "")
WECHAT_TOKEN = os.environ.get("WECHAT_TOKEN", "")

API_BASE = "https://api.weixin.qq.com"


class WeChatClient:
    """微信公众平台 API 客户端"""

    def __init__(self):
        self.appid = WECHAT_APPID
        self.appsecret = WECHAT_APPSECRET
        self.token = WECHAT_TOKEN
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._lock = threading.Lock()
        self._last_result: dict = {}

    @property
    def configured(self) -> bool:
        return bool(self.appid and self.appsecret)

    # ------------------------------
    # Token 管理
    # ------------------------------
    def _fetch_access_token(self) -> Optional[str]:
        """从微信服务器获取 access_token"""
        import requests
        url = f"{API_BASE}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.appsecret,
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if "access_token" in data:
                token = data["access_token"]
                expires_in = data.get("expires_in", 7200)
                self._access_token = token
                self._token_expires_at = time.time() + expires_in - 300
                self._last_result = data
                return token
            else:
                self._last_result = data
                print(f"[WeChat] Token获取失败: {data}")
                return None
        except Exception as e:
            print(f"[WeChat] Token请求异常: {e}")
            return None

    def get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """获取有效 access_token（带缓存）"""
        if not self.configured:
            return None

        with self._lock:
            if not force_refresh and self._access_token and time.time() < self._token_expires_at:
                return self._access_token
            return self._fetch_access_token()

    def status(self) -> dict:
        """返回微信对接状态"""
        if not self.configured:
            return {
                "configured": False,
                "message": "未配置 WECHAT_APPID / WECHAT_APPSECRET",
            }

        has_token = bool(self._access_token) and time.time() < self._token_expires_at
        return {
            "configured": True,
            "has_valid_token": has_token,
            "token_expires_in": max(0, int(self._token_expires_at - time.time())) if has_token else 0,
            "last_result": self._last_result,
        }

    # ------------------------------
    # API 请求基础
    # ------------------------------
    def _api_get(self, path: str, params: dict = None) -> dict:
        import requests
        token = self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "无有效 access_token"}
        url = f"{API_BASE}{path}"
        p = params or {}
        p["access_token"] = token
        try:
            r = requests.get(url, params=p, timeout=15)
            return r.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def _api_post(self, path: str, data: dict, params: dict = None) -> dict:
        import requests
        token = self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "无有效 access_token"}
        url = f"{API_BASE}{path}"
        p = params or {}
        p["access_token"] = token
        try:
            r = requests.post(
                url,
                data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                params=p,
                timeout=30,
            )
            return r.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    # ------------------------------
    # 素材管理
    # ------------------------------
    def upload_news(self, articles: list[dict]) -> dict:
        """
        上传永久图文素材
        articles: [{"title":"..","thumb_media_id":"..","content":"..","content_source_url":"..",
                     "digest":"..","show_cover_pic":1,"need_open_comment":1,...}]
        """
        return self._api_post("/cgi-bin/material/add_news", {"articles": articles})

    def upload_image(self, source) -> dict:
        """
        上传图片永久素材（返回 media_id 和 url）
        source 可以是文件路径 (str) 或图片数据 (bytes)
        """
        import requests
        token = self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "无有效 access_token"}
        url = f"{API_BASE}/cgi-bin/material/add_material"
        try:
            if isinstance(source, bytes):
                from io import BytesIO
                r = requests.post(
                    url,
                    params={"access_token": token, "type": "image"},
                    files={"media": ("cover.jpg", BytesIO(source), "image/jpeg")},
                    timeout=30,
                )
            else:
                with open(source, "rb") as f:
                    r = requests.post(
                        url,
                        params={"access_token": token, "type": "image"},
                        files={"media": f},
                        timeout=30,
                    )
            return r.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    # ------------------------------
    # 草稿管理
    # ------------------------------
    def add_draft(self, articles: list[dict]) -> dict:
        """
        创建草稿
        articles: [{"title":"..","content":"..","content_source_url":"..",
                     "digest":"..","thumb_media_id":"..","need_open_comment":1,...}]
        返回: {"media_id": "xxx"} 或错误
        """
        return self._api_post("/cgi-bin/draft/add", {"articles": articles})

    def get_drafts(self, offset: int = 0, count: int = 20, no_content: int = 1) -> dict:
        return self._api_post("/cgi-bin/draft/batchget", {
            "offset": offset, "count": count, "no_content": no_content
        })

    def delete_draft(self, media_id: str) -> dict:
        return self._api_post("/cgi-bin/draft/delete", {"media_id": media_id})

    # ------------------------------
    # 发布
    # ------------------------------
    def publish(self, media_id: str) -> dict:
        """发布草稿"""
        return self._api_post("/cgi-bin/freepublish/submit", {"media_id": media_id})

    def get_publish_records(self, offset: int = 0, count: int = 20) -> dict:
        return self._api_post("/cgi-bin/freepublish/batchget", {
            "offset": offset, "count": count
        })

    # ------------------------------
    # 数据统计（回传阅读）
    # ------------------------------
    def get_article_summary(self, begin_date: str, end_date: str) -> dict:
        """
        获取图文群发每日数据（阅读量 / 分享 / 收藏等）
        begin_date / end_date: "YYYY-MM-DD" 格式，间隔不超过30天
        """
        return self._api_post("/datacube/getarticlesummary", {
            "begin_date": begin_date, "end_date": end_date
        })

    def get_article_total(self, begin_date: str, end_date: str) -> dict:
        """获取图文群发总数据"""
        return self._api_post("/datacube/getarticletotal", {
            "begin_date": begin_date, "end_date": end_date
        })

    def get_user_read(self, begin_date: str, end_date: str) -> dict:
        """获取图文阅读来源分布"""
        return self._api_post("/datacube/getuserread", {
            "begin_date": begin_date, "end_date": end_date
        })

    def get_user_share(self, begin_date: str, end_date: str) -> dict:
        """获取图文分享转发数据"""
        return self._api_post("/datacube/getusershare", {
            "begin_date": begin_date, "end_date": end_date
        })

    # ------------------------------
    # 便捷方法: 一键推送生成结果
    # ------------------------------
    def _get_or_create_thumb(self) -> str:
        """获取或创建默认封面图 media_id"""
        # Look in same directory as this file (production: /opt/hisclub/.wechat_thumb)
        thumb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wechat_thumb")
        try:
            with open(thumb_path) as f:
                return f.read().strip()
        except:
            pass

        try:
            from PIL import Image, ImageDraw
            import io as io_mod
            img = Image.new('RGB', (900, 500), color=(25, 55, 109))
            draw = ImageDraw.Draw(img)
            draw.text((50, 200), "History Pipeline", fill=(255, 255, 255))
            draw.text((50, 260), "AI Content Workflow", fill=(200, 200, 220))
            buf = io_mod.BytesIO()
            img.save(buf, 'JPEG', quality=85)

            result = self.upload_image(buf.getvalue())
            if result.get("media_id"):
                with open(thumb_path, "w") as f:
                    f.write(result["media_id"])
                return result["media_id"]
        except Exception as e:
            print(f"[WeChat] 封面图生成失败: {e}")

        return ""

    def push_draft(
        self,
        title: str,
        content: str,
        digest: str = "",
        thumb_media_id: str = "",
        content_source_url: str = "",
        need_open_comment: int = 1,
    ) -> dict:
        """
        将生成的公众号文章推送到微信后台草稿箱
        content 应为 HTML 格式的完整文章
        """
        if not thumb_media_id:
            thumb_media_id = self._get_or_create_thumb()
        article = {
            "title": title[:64],
            "content": content,
            "digest": digest[:120] if digest else content[:120],
            "content_source_url": content_source_url,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": need_open_comment,
            "show_cover_pic": 1,
        }
        return self.add_draft([article])

    def push_generation(self, gen_result: dict) -> dict:
        """
        将 /generate 输出的结果转为草稿推送到微信后台
        gen_result: generator.generate() 的返回结果
        """
        article = gen_result.get("article", {})
        title = article.get("recommended_title", gen_result.get("topic", "历史文章"))
        subtitle = article.get("subtitle", "")

        # 将 sections 渲染为 HTML
        html_parts = [f"<h1>{title}</h1>"]
        if subtitle:
            html_parts.append(f"<p><em>{subtitle}</em></p>")

        for sec in article.get("sections", []):
            html_parts.append(f"<h2>{sec.get('heading', '')}</h2>")
            if sec.get("hook"):
                html_parts.append(f"<blockquote>{sec['hook']}</blockquote>")
            html_parts.append(f"<p>{sec.get('body', '')}</p>")

        if article.get("extended_reading"):
            html_parts.append("<h3>延伸阅读</h3><ul>")
            for r in article["extended_reading"]:
                html_parts.append(f"<li>{r}</li>")
            html_parts.append("</ul>")

        if article.get("golden_quotes"):
            for q in article["golden_quotes"]:
                html_parts.append(f"<blockquote>{q}</blockquote>")

        html_content = "\n".join(html_parts)
        digest = article.get("sections", [{}])[0].get("body", "")[:120] if article.get("sections") else ""

        return self.push_draft(title, html_content, digest=digest)

    # ------------------------------
    # 服务器验证（消息校验）
    # ------------------------------
    def verify_server(self, signature: str, timestamp: str, nonce: str, echostr: str = "") -> str:
        """验证微信服务器配置（用于设置服务器URL时）"""
        if not self.token:
            return ""
        tmp_list = sorted([self.token, timestamp, nonce])
        tmp_str = "".join(tmp_list)
        tmp_sha1 = hashlib.sha1(tmp_str.encode("utf-8")).hexdigest()
        if tmp_sha1 == signature:
            return echostr
        return ""


# 全局单例
_client: Optional[WeChatClient] = None


def get_wechat_client() -> WeChatClient:
    global _client
    if _client is None:
        _client = WeChatClient()
    return _client


if __name__ == "__main__":
    wx = get_wechat_client()
    print("=== 微信对接状态 ===")
    print(json.dumps(wx.status(), ensure_ascii=False, indent=2))
