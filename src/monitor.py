"""
生产级错误监控告警 v1.0
- Sentry 错误追踪（可选，需 sentry-sdk）
- Telegram / 钉钉 / 企业微信告警通知
- 日志轮转 + 磁盘清理
- 错误统计收集
"""
import json
import os
import sys
import time
import logging
import logging.handlers
import threading
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
REPORT_DIR = os.environ.get("REPORT_DIR", os.path.join(os.path.dirname(__file__), "..", "reports"))
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# ------------------------------
# Sentry (可选集成)
# ------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
_sentry_available = False

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_logging = LoggingIntegration(
            level=logging.WARNING,
            event_level=logging.ERROR,
        )
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=os.environ.get("SENTRY_ENV", "production"),
            integrations=[sentry_logging],
        )
        _sentry_available = True
        print(f"[Monitor] Sentry 已启用: {SENTRY_DSN[:50]}...")
    except ImportError:
        print("[Monitor] sentry-sdk 未安装，Sentry 跳过")
    except Exception as e:
        print(f"[Monitor] Sentry 初始化失败: {e}")


# ------------------------------
# 钉钉 / 企业微信 / Telegram 告警
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")
WECHAT_WORK_WEBHOOK = os.environ.get("WECHAT_WORK_WEBHOOK", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_webhook(url: str, payload: dict, timeout: int = 10) -> bool:
    try:
        import requests
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
        return 200 <= r.status_code < 300
    except:
        return False


def send_dingtalk_alert(title: str, message: str, level: str = "error") -> bool:
    """发送钉钉机器人告警"""
    if not DINGTALK_WEBHOOK:
        return False

    level_emoji = {"error": "🔴", "warning": "🟡", "info": "🔵", "ok": "🟢"}
    emoji = level_emoji.get(level, "📢")

    server = os.environ.get("SERVER_HOST", "unknown")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{emoji} {title[:50]}",
            "text": (
                f"## {emoji} {title}\n\n"
                f"> 服务器: **{server}**\n"
                f"> 时间: {now}\n"
                f"> 级别: {level}\n\n"
                f"**详情**:\n{message[:2000]}"
            ),
        },
    }
    return _send_webhook(DINGTALK_WEBHOOK, payload)


def send_wechat_work_alert(title: str, message: str, level: str = "error") -> bool:
    """发送企业微信机器人告警"""
    if not WECHAT_WORK_WEBHOOK:
        return False

    server = os.environ.get("SERVER_HOST", "unknown")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": (
                f"## [{level.upper()}] {title}\n"
                f"> 服务器: **{server}**\n"
                f"> 时间: {now}\n\n"
                f"{message[:2000]}"
            ),
        },
    }
    return _send_webhook(WECHAT_WORK_WEBHOOK, payload)


def send_telegram_alert(title: str, message: str, level: str = "error") -> bool:
    """发送 Telegram Bot 告警 (HTML 格式)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    level_emoji = {"error": "🔴", "warning": "🟡", "info": "ℹ️", "ok": "✅"}
    emoji = level_emoji.get(level, "ℹ️")

    server = os.environ.get("SERVER_HOST", "unknown")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # HTML-safe: escape < > &
    safe_message = message[:1800].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    text = (
        f"{emoji} <b>{title}</b>\n\n"
        f"<b>Server:</b> <code>{server}</code>\n"
        f"<b>Time:</b> <code>{now}</code>\n"
        f"<b>Level:</b> <code>{level.upper()}</code>\n\n"
        f"{safe_message}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    return _send_webhook(url, payload, timeout=15)


def alert(title: str, message: str = "", level: str = "error", exception: Exception = None):
    """统一告警入口 — 同时推送 Sentry + 钉钉 + 企微"""
    if exception:
        if message:
            message += "\n\n" + traceback.format_exc()
        else:
            message = traceback.format_exc()

    if _sentry_available and level == "error":
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exception) if exception else sentry_sdk.capture_message(title)
        except:
            pass

    send_dingtalk_alert(title, message, level)
    send_wechat_work_alert(title, message, level)
    send_telegram_alert(title, message, level)


# ------------------------------
# 错误统计收集
# ------------------------------
_error_counts = defaultdict(int)
_error_details = []
_error_lock = threading.Lock()
MAX_ERROR_DETAILS = 200


def record_error(source: str, error_msg: str, exception: Exception = None):
    """记录错误到内存统计"""
    with _error_lock:
        _error_counts[source] += 1
        _error_details.append({
            "source": source,
            "time": datetime.now().isoformat(),
            "message": error_msg[:500],
            "traceback": traceback.format_exc()[:2000] if exception else "",
        })
        if len(_error_details) > MAX_ERROR_DETAILS:
            _error_details.pop(0)


def get_error_stats() -> dict:
    """获取错误统计摘要"""
    with _error_lock:
        recent = _error_details[-20:] if _error_details else []
        return {
            "total_errors": sum(_error_counts.values()),
            "by_source": dict(_error_counts),
            "recent_errors": recent,
        }


def reset_error_stats():
    """重置错误统计"""
    global _error_counts, _error_details
    with _error_lock:
        _error_counts = defaultdict(int)
        _error_details = []


# ------------------------------
# 日志轮转配置
# ------------------------------
def setup_rotating_logger(
    name: str,
    log_file: str,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    level: int = logging.INFO,
    to_console: bool = True,
) -> logging.Logger:
    """创建带轮转的文件日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件处理器（轮转）
    log_path = os.path.join(LOG_DIR, log_file)
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    fh.setFormatter(formatter)
    fh.setLevel(level)
    logger.addHandler(fh)

    # 控制台处理器
    if to_console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        ch.setLevel(level)
        logger.addHandler(ch)

    return logger


# 预配置的各模块日志记录器
api_logger = setup_rotating_logger("api", "api.log")
generator_logger = setup_rotating_logger("generator", "generator.log")
scheduler_logger = setup_rotating_logger("scheduler", "scheduler.log")
monitor_logger = setup_rotating_logger("monitor", "monitor.log")
access_logger = setup_rotating_logger("access", "access.log", level=logging.DEBUG, to_console=False)


def log_exception(logger: logging.Logger, source: str, exc: Exception, context: str = ""):
    """统一异常日志记录"""
    msg = f"[{source}] {context}: {exc}" if context else f"[{source}] {exc}"
    logger.error(msg, exc_info=True)
    record_error(source, str(exc), exc)

    # 严重错误告警
    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
        return
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        alert(f"服务异常 [{source}]", str(exc), "warning", exc)
    else:
        alert(f"服务异常 [{source}]", str(exc), "error", exc)


# ------------------------------
# 磁盘清理策略
# ------------------------------
def clean_old_logs(days: int = 30) -> int:
    """清理过期日志文件"""
    cutoff = datetime.now() - timedelta(days=days)
    count = 0
    try:
        for fname in os.listdir(LOG_DIR):
            fpath = os.path.join(LOG_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
                count += 1
                monitor_logger.info(f"清理过期日志: {fname}")
    except Exception as e:
        monitor_logger.error(f"日志清理失败: {e}")
    return count


def clean_old_reports(days: int = 90) -> int:
    """清理过期报告文件"""
    cutoff = datetime.now() - timedelta(days=days)
    count = 0
    try:
        for fname in os.listdir(REPORT_DIR):
            fpath = os.path.join(REPORT_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
                count += 1
                monitor_logger.info(f"清理过期报告: {fname}")
    except Exception as e:
        monitor_logger.error(f"报告清理失败: {e}")
    return count


def get_disk_usage() -> dict:
    """获取日志和报告目录的磁盘占用"""
    result = {}

    for label, directory in [("logs", LOG_DIR), ("reports", REPORT_DIR)]:
        total_size = 0
        file_count = 0
        try:
            for fname in os.listdir(directory):
                fpath = os.path.join(directory, fname)
                if os.path.isfile(fpath):
                    total_size += os.path.getsize(fpath)
                    file_count += 1
        except:
            pass
        result[label] = {
            "path": directory,
            "file_count": file_count,
            "size_mb": round(total_size / (1024 * 1024), 2),
        }

    return result


def run_cleanup():
    """执行一次清理任务"""
    log_count = clean_old_logs(30)
    report_count = clean_old_reports(90)
    monitor_logger.info(f"磁盘清理完成: 删除{log_count}个过期日志, {report_count}个过期报告")


# ------------------------------
# 健康检查与监控指标
# ------------------------------
def collect_health_metrics() -> dict:
    """收集系统健康指标"""
    metrics = {
        "time": datetime.now().isoformat(),
        "sentry_enabled": _sentry_available,
        "dingtalk_enabled": bool(DINGTALK_WEBHOOK),
        "wechat_work_enabled": bool(WECHAT_WORK_WEBHOOK),
        "telegram_enabled": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
    }

    # 磁盘
    metrics["disk"] = get_disk_usage()

    # 错误统计
    metrics["errors"] = get_error_stats()

    # 内存使用
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        mem = proc.memory_info()
        metrics["memory"] = {
            "rss_mb": round(mem.rss / (1024 * 1024), 2),
            "vms_mb": round(mem.vms / (1024 * 1024), 2),
            "cpu_percent": proc.cpu_percent(interval=0.1),
            "threads": proc.num_threads(),
        }
    except ImportError:
        metrics["memory"] = {"note": "psutil 未安装"}
    except:
        metrics["memory"] = {"note": "采集失败"}

    return metrics


def startup_health_report():
    """启动时输出健康报告"""
    metrics = collect_health_metrics()
    monitor_logger.info(f"监控模块启动")
    monitor_logger.info(
        f"Sentry={_sentry_available} "
        f"DingTalk={bool(DINGTALK_WEBHOOK)} "
        f"WeChatWork={bool(WECHAT_WORK_WEBHOOK)} "
        f"Telegram={bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}"
    )

    # 启动时发送一次状态通知
    if DINGTALK_WEBHOOK or WECHAT_WORK_WEBHOOK or TELEGRAM_BOT_TOKEN:
        alert("服务启动", f"History Pipeline v3.0 已启动\n磁盘={json.dumps(metrics.get('disk', {}))}", "info")


if __name__ == "__main__":
    print("=== 监控模块自检 ===")
    metrics = collect_health_metrics()
    print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))

    print("\n=== 记录测试错误 ===")
    record_error("test", "这是一条测试错误")
    print(json.dumps(get_error_stats(), ensure_ascii=False, indent=2))

    print("\n=== 测试钉钉告警 ===")
    if DINGTALK_WEBHOOK:
        ok = send_dingtalk_alert("测试告警", "这是一条来自监控模块的测试消息", "info")
        print(f"  钉钉发送: {'成功' if ok else '失败'}")
    else:
        print("  钉钉未配置 (设置 DINGTALK_WEBHOOK 环境变量)")

    print("\n=== 磁盘清理 ===")
    run_cleanup()
    print(json.dumps(get_disk_usage(), ensure_ascii=False, indent=2))
