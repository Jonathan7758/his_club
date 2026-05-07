"""
完整自动化管道 API v3.0
热点扫描 → 角度生成 → 内容输出
"""
import os, sys, json
sys.path.insert(0, '/opt/hisclub')

# 加载 .env 环境变量（必须在此处，在所有业务模块导入之前）
from env_loader import load_env
load_env()

from hotspot_scanner import scan_history_hotspots
from generator import generate
from database import init_db, get_recent_hotspots, get_topic_history, get_hotspot_trends, _get_conn, get_comments_for_post, get_comments_stats
from scheduler import get_scheduler
from mirofish import mirofish_simulate, quick_prediction, mirofish_generate
from graph_analyzer import get_graph_stats, get_entity_centrality, find_topic_clusters, find_content_gaps
from engines import query_engine_search, media_engine_analyze, insight_engine_query, run_all_engines
from analytics import diagnose_article, batch_analyze, diagnose_from_url, batch_diagnose_from_urls
from monitor import collect_health_metrics, get_error_stats, reset_error_stats, run_cleanup, startup_health_report, record_error
from wechat_backend import get_wechat_client, WeChatClient
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
import uvicorn
import psycopg2.extras

app = FastAPI(title="History Content Pipeline v3.0")
sched = get_scheduler()

@app.on_event("startup")
def startup():
    try:
        init_db()
        print("Database initialized")
    except Exception as e:
        print(f"DB init warning: {e}")
    sched.start()
    print("Scheduler started")
    try:
        startup_health_report()
    except Exception as e:
        print(f"Monitor init warning: {e}")

class TopicRequest(BaseModel):
    topic: str
    include_video: bool = True
    inject_mirofish: bool = True

class ArticleInput(BaseModel):
    title: str = ""
    content: str

class BatchArticleInput(BaseModel):
    articles: list[dict]
    run_benchmark: bool = False

class UrlInput(BaseModel):
    url: str
    run_benchmark: bool = True

class BatchUrlInput(BaseModel):
    urls: list[str]
    run_benchmark: bool = False

class PushToWechatInput(BaseModel):
    topic: str
    include_video: bool = False

class PushResultInput(BaseModel):
    gen_result: dict

class VerifyServerInput(BaseModel):
    signature: str
    timestamp: str
    nonce: str
    echostr: str = ""

@app.post("/generate")
def generate_content(req: TopicRequest):
    result = generate(req.topic, inject_mirofish=req.inject_mirofish)
    if not req.include_video:
        del result["video_script"]
    return result

@app.get("/hotspot")
def get_hotspots():
    """获取今日历史热点"""
    return scan_history_hotspots()

@app.post("/hotspot/generate")
def hotspot_to_content(req: TopicRequest = None):
    """
    一键全流程: 扫描热点 → 选最高分话题 → 生成内容
    如果提供topic参数则直接生成，否则从热点中自动选
    """
    if req and req.topic:
        return generate(req.topic)
    
    # Auto-select from hotspots
    hotspots = scan_history_hotspots()
    if hotspots.get("suggested_next"):
        topic = hotspots["suggested_next"]["topic"]
        result = generate(topic)
        result["selected_from_hotspot"] = True
        result["hotspot_context"] = hotspots["top_5"]
        return result
    
    return {"error": "未找到历史热点"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/trends")
def get_trends(days: int = 30):
    """获取热点趋势 + 平台分布 + 热门生成话题"""
    try:
        return get_hotspot_trends(days)
    except Exception as e:
        return {"error": str(e), "hint": "可能数据库未连接或表未初始化"}

@app.get("/topic/{topic}/history")
def topic_history(topic: str):
    """查询某话题的历史生成记录"""
    try:
        return get_topic_history(topic)
    except Exception as e:
        return {"error": str(e)}

@app.get("/hotspots/recent")
def recent_hotspots(days: int = 7, limit: int = 20):
    """查询近N天存入数据库的热点"""
    try:
        return get_recent_hotspots(days, limit)
    except Exception as e:
        return {"error": str(e)}

@app.post("/webhook/trigger/{window}")
def trigger_window(window: str):
    """手动触发调度任务: daily / weekly / monthly"""
    valid = {"daily", "weekly", "monthly"}
    if window not in valid:
        return {"error": f"无效窗口类型, 可选: {valid}"}
    return sched.trigger_manual(window)

@app.get("/scheduler/status")
def scheduler_status():
    """查看调度器状态"""
    return sched.status()

@app.post("/mirofish/predict")
def mirofish_predict(topic: str, what_if: str = None, rounds: int = 5):
    """
    MiroFish Lite 历史推演
    参数: topic(历史事件), what_if(反事实条件，可选), rounds(推演轮数3-7)
    """
    try:
        return mirofish_simulate(topic, what_if, rounds=max(3, min(7, rounds)))
    except Exception as e:
        return {"error": str(e)}

@app.get("/mirofish/quick/{topic}")
def mirofish_quick(topic: str):
    """快速生成"历史如果"选题建议，用于评估"""
    try:
        return quick_prediction(topic)
    except Exception as e:
        return {"error": str(e)}

@app.post("/mirofish/generate")
def mirofish_full_generate(topic: str, what_if: str = None, rounds: int = 5):
    """
    MiroFish全流程: 推演 → 角度提取 → 文章生成
    一键产出"历史如果"公众号完整内容包
    """
    try:
        result = mirofish_generate(topic, what_if, rounds=max(3, min(7, rounds)))
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/stats")
def dashboard_stats():
    """数据看板 — 全部统计指标JSON"""
    try:
        conn = _get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 总览
        cur.execute("SELECT count(*) FROM hot_topics")
        total_hotspots = cur.fetchone()["count"]
        cur.execute("SELECT count(*) FROM generations")
        total_generations = cur.fetchone()["count"]
        cur.execute("SELECT count(*) FROM posts")
        total_posts = cur.fetchone()["count"]
        cur.execute("SELECT count(*) FROM entity_relations")
        total_entities = cur.fetchone()["count"]
        cur.execute("SELECT count(*) FROM sentiment_labels")
        total_sentiments = cur.fetchone()["count"]

        # 平台分布
        cur.execute("SELECT source_platform, count(*) as cnt FROM hot_topics GROUP BY source_platform ORDER BY cnt DESC LIMIT 10")
        platform_dist = [dict(r) for r in cur.fetchall()]

        # 最近生成
        cur.execute("SELECT topic, created_at, meta FROM generations ORDER BY created_at DESC LIMIT 10")
        recent_gens = []
        for r in cur.fetchall():
            meta = r["meta"] if isinstance(r["meta"], dict) else {}
            recent_gens.append({
                "topic": r["topic"],
                "created_at": str(r["created_at"]),
                "fact_check_score": meta.get("fact_check_score"),
                "angles_count": meta.get("angles_count"),
                "entity_count": meta.get("entity_relations"),
            })

        # 情感分布
        cur.execute("SELECT label, round(avg(score)::numeric,2) as avg_score, count(*) as cnt FROM sentiment_labels GROUP BY label ORDER BY label")
        sentiment_dist = [dict(r) for r in cur.fetchall()]

        # 实体关系Top
        cur.execute("SELECT source_entity, relation, target_entity, confidence FROM entity_relations ORDER BY confidence DESC LIMIT 10")
        top_entities = [dict(r) for r in cur.fetchall()]

        # 最近7天趋势
        cur.execute("SELECT DATE(created_at) as day, count(*) as cnt FROM hot_topics WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY day ORDER BY day")
        recent_daily = [dict(r) for r in cur.fetchall()]

        cur.close()
        conn.close()

        return {
            "overview": {
                "total_hotspots": total_hotspots,
                "total_generations": total_generations,
                "total_posts": total_posts,
                "total_entities": total_entities,
                "total_sentiments": total_sentiments,
            },
            "platform_distribution": platform_dist,
            "recent_generations": recent_gens,
            "sentiment_distribution": sentiment_dist,
            "top_entity_relations": top_entities,
            "recent_7day_trend": recent_daily,
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/graph/stats")
def graph_overview():
    """知识图谱基础统计"""
    try:
        return get_graph_stats()
    except Exception as e:
        return {"error": str(e)}

@app.get("/graph/centrality")
def graph_centrality(top_n: int = 20):
    """实体中心度排名"""
    try:
        return get_entity_centrality(top_n)
    except Exception as e:
        return {"error": str(e)}

@app.get("/graph/clusters")
def graph_clusters(min_cooccur: int = 2):
    """话题聚类发现"""
    try:
        return find_topic_clusters(min_cooccur)
    except Exception as e:
        return {"error": str(e)}

@app.get("/graph/gaps")
def graph_gaps():
    """内容盲区发现"""
    try:
        return find_content_gaps()
    except Exception as e:
        return {"error": str(e)}

@app.get("/analyze/{topic}")
def analyze_topic(topic: str):
    """三引擎并行分析: QueryEngine+MediaEngine+InsightEngine"""
    try:
        return run_all_engines(topic)
    except Exception as e:
        return {"error": str(e)}

@app.post("/analytics/diagnose")
def diagnose_single(article: ArticleInput, run_benchmark: bool = True):
    """
    单篇文章诊断 — 7维评分 + 改进建议
    输入: 标题(可选) + 正文文本
    输出: 诊断报告(含维度分/强弱项/改进计划)
    """
    try:
        return diagnose_article(article.content, article.title, run_benchmark=run_benchmark)
    except Exception as e:
        return {"error": str(e)}

@app.post("/analytics/batch")
def diagnose_batch(req: BatchArticleInput):
    return batch_analyze(req.articles, run_benchmark=req.run_benchmark)

@app.post("/analytics/diagnose/url")
def diagnose_from_url_endpoint(req: UrlInput):
    """
    通过微信公众号文章URL诊断 — 自动抓取正文+标题
    输入: 文章URL (如 https://mp.weixin.qq.com/s/XXXX)
    """
    try:
        return diagnose_from_url(req.url, run_benchmark=req.run_benchmark)
    except Exception as e:
        return {"error": str(e)}

@app.post("/analytics/batch/urls")
def batch_diagnose_from_urls_endpoint(req: BatchUrlInput):
    """
    批量URL诊断 — 传入多个微信文章URL一次性分析
    输入: {"urls": ["https://mp.weixin.qq.com/s/xxx", ...]}
    """
    try:
        return batch_diagnose_from_urls(req.urls, run_benchmark=req.run_benchmark)
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_html():
    """数据看板 HTML 页面"""
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>历史内容Pipeline — 数据看板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:24px}
h1{font-size:24px;margin-bottom:20px;color:#38bdf8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.card h3{font-size:13px;color:#94a3b8;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}
.card .value{font-size:36px;font-weight:700;color:#38bdf8}
.section{margin-bottom:24px}
.section h2{font-size:18px;color:#cbd5e1;margin-bottom:12px;border-bottom:1px solid #334155;padding-bottom:8px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #1e293b}
th{color:#94a3b8;font-weight:600}
td{color:#cbd5e1}
tr:hover{background:#1e293b}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600}
.badge-green{background:#065f46;color:#6ee7b7}
.badge-yellow{background:#78350f;color:#fcd34d}
.badge-red{background:#7f1d1d;color:#fca5a5}
.refresh{text-align:right;color:#64748b;font-size:12px;margin-bottom:16px}
</style>
</head>
<body>
<h1>History Content Pipeline v3.0 — 数据看板</h1>
<div class="refresh">最后更新: <span id="refreshTime"></span> | 自动刷新 30s</div>
<div id="app">加载中...</div>
<script>
async function load(){
  try{
    const r=await fetch('/stats');
    const d=await r.json();
    document.getElementById('refreshTime').textContent=new Date().toLocaleTimeString('zh');
    let o=d.overview||{};
    let html='<div class="grid">'+
      '<div class="card"><h3>热点扫描</h3><div class="value">'+o.total_hotspots+'</div></div>'+
      '<div class="card"><h3>文章生成</h3><div class="value">'+o.total_generations+'</div></div>'+
      '<div class="card"><h3>帖子沉淀</h3><div class="value">'+o.total_posts+'</div></div>'+
      '<div class="card"><h3>实体关系</h3><div class="value">'+o.total_entities+'</div></div>'+
      '<div class="card"><h3>情感标签</h3><div class="value">'+o.total_sentiments+'</div></div>'+
      '</div>';

    html+='<div class="section"><h2>平台分布</h2><table><thead><tr><th>平台</th><th>话题数</th></tr></thead><tbody>';
    (d.platform_distribution||[]).forEach(p=>{html+='<tr><td>'+p.source_platform+'</td><td>'+p.cnt+'</td></tr>'});
    html+='</tbody></table></div>';

    html+='<div class="section"><h2>热点趋势(近7天)</h2><table><thead><tr><th>日期</th><th>话题数</th></tr></thead><tbody>';
    (d.recent_7day_trend||[]).forEach(r=>{html+='<tr><td>'+r.day+'</td><td>'+r.cnt+'</td></tr>'});
    html+='</tbody></table></div>';

    html+='<div class="section"><h2>情感维度</h2><table><thead><tr><th>标签</th><th>均分</th><th>数量</th></tr></thead><tbody>';
    (d.sentiment_distribution||[]).forEach(s=>{html+='<tr><td>'+s.label+'</td><td>'+s.avg_score+'</td><td>'+s.cnt+'</td></tr>'});
    html+='</tbody></table></div>';

    html+='<div class="section"><h2>最近生成</h2><table><thead><tr><th>话题</th><th>时间</th><th>角度数</th><th>事实分</th><th>实体数</th></tr></thead><tbody>';
    (d.recent_generations||[]).forEach(g=>{
      let score=g.fact_check_score||0;
      let badge=score>=0.8?'badge-green':(score>=0.6?'badge-yellow':'badge-red');
      html+='<tr><td>'+g.topic+'</td><td>'+g.created_at+'</td><td>'+g.angles_count+'</td><td><span class="badge '+badge+'">'+score+'</span></td><td>'+g.entity_count+'</td></tr>'
    });
    html+='</tbody></table></div>';

    document.getElementById('app').innerHTML=html;
  }catch(e){document.getElementById('app').innerHTML='加载失败: '+e}
}
load();
setInterval(load,30000);
</script>
</body>
</html>"""


# ================================================================
# 监控告警端点
# ================================================================
@app.get("/monitor/health")
def monitor_health():
    """系统健康指标（含内存、磁盘、错误统计）"""
    try:
        return collect_health_metrics()
    except Exception as e:
        record_error("api.monitor.health", str(e))
        return {"error": str(e)}


@app.get("/monitor/errors")
def monitor_errors():
    """错误统计摘要"""
    try:
        return get_error_stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/monitor/errors/reset")
def monitor_reset_errors():
    """重置错误统计"""
    reset_error_stats()
    return {"status": "ok"}


@app.post("/monitor/cleanup")
def monitor_cleanup():
    """触发磁盘清理（删除过期日志和报告）"""
    try:
        run_cleanup()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


# ================================================================
# 评论数据端点
# ================================================================
@app.get("/comments/{post_id}")
def comments_for_post(post_id: str, limit: int = 50):
    """查询某帖子的评论列表"""
    try:
        return get_comments_for_post(post_id, limit)
    except Exception as e:
        return {"error": str(e)}


@app.get("/comments/stats")
def comments_overview(days: int = 7):
    """评论数据概览统计"""
    try:
        return get_comments_stats(days)
    except Exception as e:
        return {"error": str(e)}


# ================================================================
# 公众号后台数据回传端点
# ================================================================
@app.get("/wechat/status")
def wechat_status():
    """微信公众平台对接状态"""
    try:
        wx = get_wechat_client()
        return wx.status()
    except Exception as e:
        return {"error": str(e)}


@app.get("/wechat/stats")
def wechat_read_stats(begin_date: str = None, end_date: str = None):
    """
    拉取微信后台图文阅读数据
    begin_date / end_date: YYYY-MM-DD 格式
    """
    from datetime import date, timedelta
    if not begin_date:
        begin_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = date.today().strftime("%Y-%m-%d")

    try:
        wx = get_wechat_client()
        if not wx.configured:
            return {"error": "微信未配置"}
        return wx.get_article_summary(begin_date, end_date)
    except Exception as e:
        return {"error": str(e)}


@app.get("/wechat/drafts")
def wechat_drafts(offset: int = 0, count: int = 20):
    """获取微信草稿箱列表"""
    try:
        wx = get_wechat_client()
        if not wx.configured:
            return {"error": "微信未配置"}
        return wx.get_drafts(offset, count)
    except Exception as e:
        return {"error": str(e)}


@app.get("/wechat/verify", response_class=PlainTextResponse)
def wechat_server_verify(signature: str, timestamp: str, nonce: str, echostr: str = ""):
    """
    微信服务器配置验证端点
    在公众号后台 -> 开发 -> 基本配置 -> 服务器配置 中设置此端点
    URL 格式: https://your-domain/wechat/verify
    """
    try:
        wx = get_wechat_client()
        result = wx.verify_server(signature, timestamp, nonce, echostr)
        return result if result else ""
    except Exception as e:
        return ""


# ================================================================
# 预览端点 — 生成 HTML 格式供人工审阅（不推送微信）
# ================================================================
@app.post("/preview")
def preview_content(req: TopicRequest):
    """生成公众号内容并返回 HTML（不推送微信）"""
    try:
        result = generate(req.topic, inject_mirofish=req.inject_mirofish)
        article = result.get("article", {})
        title = article.get("recommended_title", req.topic)
        subtitle = article.get("subtitle", "")
        sections = article.get("sections", [])
        angles = result.get("angles", [])

        html_parts = [f"<h1>{title}</h1>"]
        if subtitle:
            html_parts.append(f"<p><em>{subtitle}</em></p>")
        for sec in sections:
            html_parts.append(f"<h2>{sec.get('heading', '')}</h2>")
            if sec.get("hook"):
                html_parts.append(f"<blockquote>{sec['hook']}</blockquote>")
            html_parts.append(f"<p>{sec.get('body', '')}</p>")

        return {
            "topic": req.topic,
            "title": title,
            "html": "\n".join(html_parts),
            "angles_count": len(angles),
            "fact_check_score": result.get("fact_check", {}).get("overall_score"),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/preview/latest")
def preview_latest():
    """最近一篇生成结果的 HTML 预览"""
    try:
        conn = _get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM generations ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"error": "无生成记录"}
        article = row.get("article") or {}
        if isinstance(article, str):
            article = json.loads(article)
        title = article.get("recommended_title", row.get("topic", ""))
        sections = article.get("sections", [])
        html_parts = [f"<h1>{title}</h1>"]
        for sec in sections:
            html_parts.append(f"<h2>{sec.get('heading', '')}</h2>")
            if sec.get("hook"):
                html_parts.append(f"<blockquote>{sec['hook']}</blockquote>")
            body = sec.get("body") or sec.get("content") or ""
            html_parts.append(f"<p>{body}</p>")
        return {"topic": row.get("topic"), "title": title, "html": "\n".join(html_parts)}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)
