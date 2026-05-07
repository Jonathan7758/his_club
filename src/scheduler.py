"""
时间窗口调度器 v1.0
三级时间窗口: 日扫描(1周窗口) / 周汇总(1月窗口) / 月前瞻(1年窗口)
纯Python实现，无外部依赖，作为后台线程运行
"""
import threading
import time
import json
from datetime import datetime, timedelta
from openai import OpenAI
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-3ded85b7ccb4438fbe95ec7d45416e44"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)
MODEL = "deepseek-chat"


class TimeWindowScheduler:
    """三级时间窗口调度器"""

    def __init__(self):
        self.running = False
        self.thread = None
        self.last_daily = None
        self.last_weekly = None
        self.last_monthly = None
        self.job_log = []

    def _daily_scan(self):
        """日扫描: 1周窗口 — 每日6:00抓取最新热点"""
        try:
            from hotspot_scanner import scan_history_hotspots
            from database import save_hotspot_scan
            from mindspider_bridge import sync_mindspider_to_posts

            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 日扫描启动...")
            result = scan_history_hotspots()
            n = save_hotspot_scan(result, window_type="daily")
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 日扫描完成: 发现{len(result.get('history_topics',[]))}条, 入库{n}条")

            print(f"[{datetime.now():%Y-%m-%d %H:%M}] MindSpider同步...")
            try:
                ms_stats = sync_mindspider_to_posts()
                print(f"  同步完成: {ms_stats}")
            except Exception as e:
                print(f"  MindSpider同步跳过: {e}")

            self.last_daily = datetime.now()
            self.job_log.append({"type": "daily", "time": str(datetime.now()), "topics": len(result.get("history_topics", [])), "top": result.get("suggested_next", {}).get("topic", "")[:40]})

            self._auto_generate_top_topic(result)

        except Exception as e:
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 日扫描失败: {e}")

    def _auto_generate_top_topic(self, scan_result: dict):
        """自动为热度最高的热点生成内容"""
        try:
            from generator import generate
            from database import save_generation

            suggested = scan_result.get("suggested_next")
            if not suggested or not suggested.get("topic"):
                return

            top_topic = suggested["topic"]
            score = suggested.get("score", 0)
            if score < 6:
                print(f"  Top topic '{top_topic}' score {score} < 6, skipping auto-generate")
                return

            print(f"  自动生成: {top_topic} (score={score})")
            result = generate(top_topic)
            gen_id = save_generation(top_topic, result)
            print(f"  自动生成完成: {gen_id}")
            self.job_log.append({"type": "auto_generate", "time": str(datetime.now()), "topic": top_topic[:40], "db_id": gen_id})

        except Exception as e:
            print(f"  自动生成失败: {e}")

    def _weekly_summary(self):
        """周汇总: 1月窗口 — 每周一8:00趋势分析 + 选题推荐"""
        try:
            from database import get_recent_hotspots, get_hotspot_trends

            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 周汇总启动...")
            trends = get_hotspot_trends(days=30)
            hotspots = get_recent_hotspots(days=7, limit=30)

            report = self._generate_weekly_report(hotspots, trends)
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 周汇总完成")

            # 保存周报告到文件
            report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, f"weekly_{datetime.now():%Y%m%d}.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            self.last_weekly = datetime.now()
            self.job_log.append({"type": "weekly", "time": str(datetime.now()), "report": report_path})

        except Exception as e:
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 周汇总失败: {e}")

    def _generate_weekly_report(self, hotspots: list[dict], trends: dict) -> dict:
        """LLM生成周趋势报告"""
        topics_text = "\n".join([f"- [{h.get('source_platform','')}] {h.get('topic','')} (热度{h.get('heat_score',0)})" for h in hotspots[:20]])
        trends_text = json.dumps(trends.get("daily_stats", []), ensure_ascii=False, default=str)[:2000]

        prompt = f"""你是历史内容运营主编。请根据本周的历史热点数据做趋势分析：

本周历史热点Top 20:
{topics_text[:3000]}

近30天热搜日统计:
{trends_text[:2000]}

请输出JSON：
{{
  "period": "本周({datetime.now():%m.%d}-{(datetime.now()+timedelta(days=7)):%m.%d})",
  "trend_summary": "本周历史内容热度趋势概述(80字)",
  "rising_topics": ["上升话题1(30字说明)","上升话题2"],
  "declining_topics": ["降温话题1"],
  "recommended_next_week": [
    {{"topic":"推荐选题1","reason":"推荐理由(40字)","window":"daily|weekly|monthly","estimated_novelty":0.8}}
  ],
  "content_calendar": [
    {{"date":"周一","topic_type":"热点快评|深度分析|历史如果","suggested_topic":"选题建议"}}
  ]
}}"""

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=2000
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "")
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except:
            return {"trend_summary": text[:200], "raw": text}

    def _monthly_calendar(self):
        """月前瞻: 1年窗口 — 每月1日生成选题日历"""
        try:
            from database import get_recent_hotspots, get_hotspot_trends

            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 月前瞻启动...")
            trends = get_hotspot_trends(days=365)

            calendar = self._generate_topic_calendar(trends)
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 月前瞻完成")

            report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, f"monthly_{datetime.now():%Y%m}.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(calendar, f, ensure_ascii=False, indent=2)

            self.last_monthly = datetime.now()
            self.job_log.append({"type": "monthly", "time": str(datetime.now()), "report": report_path})

        except Exception as e:
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] 月前瞻失败: {e}")

    def _generate_topic_calendar(self, trends: dict) -> dict:
        """LLM生成未来3个月选题日历"""
        stats_text = json.dumps(trends.get("daily_stats", []), ensure_ascii=False, default=str)[:3000]
        platforms = json.dumps(trends.get("platform_distribution", []), ensure_ascii=False, default=str)
        top_generated = json.dumps(trends.get("top_generated_topics", []), ensure_ascii=False, default=str)

        next_month = datetime.now().replace(day=1) + timedelta(days=32)
        next_month = next_month.replace(day=1)

        prompt = f"""你是历史内容运营主编。请分析历史热点趋势数据，为未来3个月生成选题日历。考虑历史纪念日、热门讨论趋势、季节性因素。

过去365天热点统计:
{stats_text[:3000]}

平台分布:
{platforms}

最热门生成话题:
{top_generated}

请输出JSON（按月分组，每月6-8个选题）：
{{
  "calendar": [
    {{
      "month": "{next_month:%Y年%m月}",
      "monthly_theme": "本月核心主题(30字)",
      "topics": [
        {{"week": 1, "topic": "选题", "angle": "切入点(30字)", "date_context": "XX纪念日/XX大展等"}},
        {{"week": 1, "topic": "选题2", "angle": "切入点", "date_context": ""}}
      ]
    }},
    {{"month": "{(next_month + timedelta(days=32)).strftime('%Y年%m月')}", ...}},
    {{"month": "{(next_month + timedelta(days=64)).strftime('%Y年%m月')}", ...}}
  ],
  "strategy_note": "运营策略建议(100字)"
}}"""

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=3000
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "")
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except:
            return {"raw": text}

    def _should_run_daily(self) -> bool:
        now = datetime.now()
        if self.last_daily and (now - self.last_daily).seconds < 3600:
            return False
        return now.hour == 6 and now.minute < 1

    def _should_run_weekly(self) -> bool:
        now = datetime.now()
        if self.last_weekly and (now - self.last_weekly).days < 6:
            return False
        return now.weekday() == 0 and now.hour == 8 and now.minute < 1

    def _should_run_monthly(self) -> bool:
        now = datetime.now()
        if self.last_monthly and (now - self.last_monthly).days < 28:
            return False
        return now.day == 1 and now.hour == 9 and now.minute < 1

    def _loop(self):
        """主循环，每分钟检查一次"""
        print("Scheduler started. Waiting for triggers...")
        # 启动时立即执行一次日扫描
        self._daily_scan()

        while self.running:
            try:
                if self._should_run_daily():
                    self._daily_scan()
                elif self._should_run_weekly():
                    self._weekly_summary()
                elif self._should_run_monthly():
                    self._monthly_calendar()

                time.sleep(60)
            except Exception as e:
                print(f"Scheduler loop error: {e}")
                time.sleep(60)

    def start(self):
        """启动调度器后台线程"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="TimeWindowScheduler")
        self.thread.start()

    def stop(self):
        """停止调度器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def trigger_manual(self, window: str) -> dict:
        """手动触发指定窗口"""
        if window == "daily":
            self._daily_scan()
            return {"status": "ok", "type": "daily", "last_run": str(self.last_daily)}
        elif window == "weekly":
            self._weekly_summary()
            return {"status": "ok", "type": "weekly", "last_run": str(self.last_weekly)}
        elif window == "monthly":
            self._monthly_calendar()
            return {"status": "ok", "type": "monthly", "last_run": str(self.last_monthly)}
        else:
            return {"status": "error", "message": f"Unknown window: {window}"}

    def status(self) -> dict:
        return {
            "running": self.running,
            "last_daily": str(self.last_daily) if self.last_daily else None,
            "last_weekly": str(self.last_weekly) if self.last_weekly else None,
            "last_monthly": str(self.last_monthly) if self.last_monthly else None,
            "job_log": self.job_log[-10:]
        }


_scheduler_instance = None


def get_scheduler() -> TimeWindowScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TimeWindowScheduler()
    return _scheduler_instance


if __name__ == "__main__":
    sched = get_scheduler()
    sched.start()

    print("Scheduler running. Press Ctrl+C to stop.")
    print("  daily  at 06:00")
    print("  weekly at 08:00 Monday")
    print("  monthly at 09:00 1st")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        sched.stop()
        print("Stopped.")
