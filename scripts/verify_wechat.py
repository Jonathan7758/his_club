"""微信公众号 API 对接验证脚本"""
import os
import sys
import json
import requests

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
env_path = os.path.normpath(env_path)
if os.path.isfile(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key] = val

APPID = os.environ.get("WECHAT_APPID", "")
APPSECRET = os.environ.get("WECHAT_APPSECRET", "")

print("=" * 60)
print("微信公众号 API 对接验证")
print(f"AppID: {APPID}")
print(f"AppSecret: {'*' * 10}{APPSECRET[-4:] if len(APPSECRET) > 4 else 'N/A'}")
print("=" * 60)

if not APPID or not APPSECRET:
    print("\n[FAIL] WECHAT_APPID 或 WECHAT_APPSECRET 未设置")
    sys.exit(1)

# Step 1: Get access token
print("\n[1] 获取 access_token...")
try:
    r = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": APPID,
            "secret": APPSECRET,
        },
        timeout=15,
    )
    data = r.json()
    print(f"  HTTP {r.status_code}: {json.dumps(data, ensure_ascii=False)}")

    if "access_token" in data:
        token = data["access_token"]
        expires = data.get("expires_in", "?")
        print(f"  [OK] Token 获取成功, 有效期 {expires}s")
        print(f"  Token: {token[:20]}...{token[-10:]}")
    else:
        errcode = data.get("errcode", "?")
        errmsg = data.get("errmsg", "未知错误")
        print(f"  [FAIL] errcode={errcode} errmsg={errmsg}")
        
        # Common error explanations
        explanations = {
            -1: "系统繁忙",
            40001: "AppSecret 错误或 access_token 无效",
            40013: "无效的 AppID",
            40125: "AppSecret 错误",
            40164: "IP 不在白名单中 — 需在公众号后台添加本机 IP",
            41001: "access_token 缺失",
            41002: "AppID 缺失",
        }
        if errcode in explanations:
            print(f"  说明: {explanations[errcode]}")
        print("\n[FAIL] 微信对接失败，请检查配置")
        sys.exit(1)

except Exception as e:
    print(f"  [FAIL] 网络异常: {e}")
    sys.exit(1)

# Step 2: Get draft list (verify permissions)
print("\n[2] 获取草稿箱列表...")
try:
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={token}",
        json={"offset": 0, "count": 5, "no_content": 1},
        timeout=15,
    )
    draft_data = r.json()
    if draft_data.get("errcode") == 0:
        total = draft_data.get("total_count", 0)
        items = draft_data.get("item", [])
        print(f"  [OK] 草稿箱共 {total} 篇")
        for item in items[:3]:
            media_id = item.get("media_id", "")[:20]
            update_time = item.get("update_time", "")
            content_item = item.get("content", {}).get("news_item", [{}])[0] if item.get("content") else {}
            title = content_item.get("title", "无标题")
            print(f"    - {title} (media_id={media_id})")
    else:
        errcode = draft_data.get("errcode", "?")
        errmsg = draft_data.get("errmsg", "")
        if errcode == 48001:
            print(f"  [WARN] 该公众号未授权草稿/发布权限 (errcode=48001)")
        else:
            print(f"  [WARN] errcode={errcode} errmsg={errmsg}")
except Exception as e:
    print(f"  [WARN] 草稿查询异常: {e}")

# Step 3: Test article stats
print("\n[3] 获取图文阅读数据 (近7天)...")
from datetime import date, timedelta
end_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
begin_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
try:
    r = requests.post(
        f"https://api.weixin.qq.com/datacube/getarticlesummary?access_token={token}",
        json={"begin_date": begin_date, "end_date": end_date},
        timeout=15,
    )
    stats = r.json()
    if stats.get("errcode") == 0:
        items = stats.get("list", [])
        if items:
            total_read = sum(d.get("int_page_read_user", 0) for d in items)
            total_share = sum(d.get("share_user", 0) for d in items)
            print(f"  [OK] {len(items)} 天数据: 总阅读 {total_read:,}, 总分享 {total_share:,}")
        else:
            print(f"  [OK] 近7天无群发数据 (或数据尚未生成)")
    else:
        errcode = stats.get("errcode", "?")
        if errcode == 61501:
            print(f"  [WARN] 日期范围无效 (可能无群发记录)")
        else:
            print(f"  [WARN] errcode={errcode} errmsg={stats.get('errmsg','')}")
except Exception as e:
    print(f"  [WARN] 统计数据异常: {e}")

print("\n" + "=" * 60)
print("[OK] 微信公众号 API 对接验证完成")
print("   Token 获取: 成功")
print("   后续操作:")
print(f"   1. python deploy.py 部署到服务器")
print(f"   2. POST /wechat/push {{\"topic\":\"安史之乱\"}} 测试草稿推送")
print(f"   3. GET /wechat/stats 查看阅读数据")
print("=" * 60)
