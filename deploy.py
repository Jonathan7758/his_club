"""
一键部署脚本 v1.0
将本地 src/ 目录同步到生产/开发服务器并重启服务

用法:
    python deploy.py                     # 部署到生产服务器 (124.174.42.6)
    python deploy.py --dev               # 部署到开发服务器 (115.190.167.220)
    python deploy.py --dry-run           # 仅显示将执行的操作，不实际执行
    python deploy.py --restart-only      # 仅重启远程服务
    python deploy.py --files-only        # 仅同步文件，不重启

依赖: ssh / scp (Windows 10+ 自带 OpenSSH 客户端)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime


# ---------------------------------------------------------------------------
# 服务器配置
# ---------------------------------------------------------------------------
SERVERS = {
    "production": {
        "host": "124.174.42.6",
        "user": "root",
        "port": 22,
        "remote_dir": "/opt/hisclub",
        "label": "生产",
    },
    "development": {
        "host": "115.190.167.220",
        "user": "root",
        "port": 22,
        "remote_dir": "/opt/hisclub",
        "label": "开发",
    },
}

# 需要同步的文件（相对于项目根目录）
DEPLOY_FILES = [
    "src/api.py",
    "src/generator.py",
    "src/hotspot_scanner.py",
    "src/database.py",
    "src/scheduler.py",
    "src/connector.py",
    "src/fact_checker.py",
    "src/douban.py",
    "src/mirofish.py",
    "src/engines.py",
    "src/graph_analyzer.py",
    "src/mindspider_bridge.py",
    "src/analytics.py",
    "src/monitor.py",
    "src/wechat_backend.py",
    "src/env_loader.py",
]

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(LOCAL_DIR)


def _run_cmd(cmd: list[str], timeout: int = 60, dry_run: bool = False) -> tuple[bool, str]:
    """执行命令"""
    if dry_run:
        print(f"  [DRY-RUN] {' '.join(cmd)}")
        return True, ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok = r.returncode == 0
        output = r.stdout.strip() or r.stderr.strip()
        return ok, output
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except FileNotFoundError:
        return False, f"找不到命令: {cmd[0]}"
    except Exception as e:
        return False, str(e)


def _ssh(cfg: dict, remote_cmd: str, dry_run: bool = False) -> tuple[bool, str]:
    """SSH 执行远程命令"""
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-p", str(cfg["port"]),
        f"{cfg['user']}@{cfg['host']}",
        remote_cmd,
    ]
    return _run_cmd(cmd, timeout=30, dry_run=dry_run)


def _scp(local_path: str, cfg: dict, remote_filename: str = None, dry_run: bool = False) -> tuple[bool, str]:
    """SCP 拷贝文件到远程"""
    if remote_filename is None:
        remote_filename = os.path.basename(local_path)
    remote_path = f"{cfg['user']}@{cfg['host']}:{cfg['remote_dir']}/{remote_filename}"
    cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-P", str(cfg["port"]),
        local_path,
        remote_path,
    ]
    return _run_cmd(cmd, timeout=30, dry_run=dry_run)


def check_connection(cfg: dict, dry_run: bool = False) -> bool:
    """检测 SSH 连接"""
    print(f"[{cfg['label']}] 检测连接 {cfg['host']}...")
    ok, out = _ssh(cfg, "echo OK", dry_run=dry_run)
    if ok and "OK" in out:
        print(f"  ✅ 连接成功")
        return True
    else:
        print(f"  ❌ 连接失败: {out}")
        return False


def sync_files(cfg: dict, dry_run: bool = False) -> dict:
    """同步所有源文件到远程"""
    stats = {"total": 0, "ok": 0, "failed": []}
    print(f"\n[{cfg['label']}] 同步{len(DEPLOY_FILES)}个文件...")

    for rel_path in DEPLOY_FILES:
        local_path = os.path.join(LOCAL_DIR, rel_path)
        remote_rel = os.path.basename(rel_path)  # 服务器上所有文件在同一个目录
        if not os.path.isfile(local_path):
            print(f"  ⚠️ 跳过 (本地不存在): {rel_path}")
            continue

        stats["total"] += 1
        ok, err = _scp(local_path, cfg, remote_filename=remote_rel, dry_run=dry_run)
        if ok:
            stats["ok"] += 1
            if not dry_run:
                print(f"  ✅ {rel_path}")
        else:
            stats["failed"].append(rel_path)
            print(f"  ❌ {rel_path}: {err}")

    return stats


def sync_env_file(cfg: dict, dry_run: bool = False) -> bool:
    """同步 .env 文件到远程"""
    local_env = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.isfile(local_env):
        print(f"\n[{cfg['label']}] ⚠️ 本地 .env 不存在，跳过同步")
        return False

    print(f"\n[{cfg['label']}] 同步 .env → {cfg['remote_dir']}/.env ...")
    ok, err = _scp(local_env, cfg, dry_run=dry_run)
    if ok:
        print(f"  ✅ .env")
        if not dry_run:
            # 设置权限 600
            _ssh(cfg, f"chmod 600 {cfg['remote_dir']}/.env", dry_run=dry_run)
    else:
        print(f"  ❌ .env: {err}")
    return ok


def restart_service(cfg: dict, dry_run: bool = False) -> bool:
    """重启远程 API 服务"""
    print(f"\n[{cfg['label']}] 重启 API 服务...")
    remote_cmd = (
        f"pkill -f 'python3 api.py' 2>/dev/null; "
        f"sleep 2; "
        f"cd {cfg['remote_dir']} && "
        f"nohup python3 api.py > /tmp/api.log 2>&1 &"
    )
    ok, out = _ssh(cfg, remote_cmd, dry_run=dry_run)
    if ok:
        print(f"  ✅ 服务重启命令已执行")
        time.sleep(3)
    else:
        print(f"  ❌ 重启失败: {out}")
    return ok


def health_check(cfg: dict, dry_run: bool = False) -> bool:
    """健康检查"""
    print(f"\n[{cfg['label']}] 健康检查...")
    ok, out = _ssh(cfg, "curl -s http://localhost:5050/health", dry_run=dry_run)
    if ok and '"status":"ok"' in out:
        print(f"  ✅ API 健康: {out}")
        return True
    elif ok:
        print(f"  ⚠️ API 响应异常: {out[:200]}")
        return False
    else:
        print(f"  ❌ 无法访问 API: {out}")
        return False


def verify_module(cfg: dict, module: str, dry_run: bool = False) -> bool:
    """验证单个模块是否正确部署"""
    ok, out = _ssh(
        cfg,
        f"cd {cfg['remote_dir']} && python3 -c 'import ast; ast.parse(open(\"{module}\").read()); print(\"OK\")' 2>&1",
        dry_run=dry_run,
    )
    return ok and "OK" in out


def deploy(env: str = "production", dry_run: bool = False, files_only: bool = False, restart_only: bool = False, sync_env: bool = False):
    """主部署流程"""
    if env not in SERVERS:
        print(f"❌ 未知环境: {env}. 可选: {list(SERVERS.keys())}")
        return False

    cfg = SERVERS[env]
    print(f"{'='*60}")
    print(f"部署到 {cfg['label']}服务器: {cfg['host']}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if dry_run:
        print("模式: DRY-RUN (不执行实际操作)")
    print(f"{'='*60}")

    if not restart_only:
        # 1. 连接检测
        if not check_connection(cfg, dry_run):
            print("\n❌ 无法连接到服务器，部署中止")
            print("   请确保:")
            print(f"   - SSHD 服务运行在 {cfg['host']}")
            print(f"   - 本地可通过 ssh {cfg['user']}@{cfg['host']} 连接")
            return False

        # 2. 同步 .env（如果指定）
        if sync_env:
            sync_env_file(cfg, dry_run)

        # 3. 同步文件
        stats = sync_files(cfg, dry_run)
        print(f"\n  文件同步: {stats['ok']}/{stats['total']} 成功")

        if stats["failed"]:
            print(f"  失败文件: {stats['failed']}")
    else:
        stats = {"total": 0, "ok": 0, "failed": []}

    if not files_only:
        # 3. 重启服务
        restart_service(cfg, dry_run)

        # 4. 健康检查
        health_ok = health_check(cfg, dry_run)

        # 5. 验证关键模块
        if not dry_run:
            print(f"\n[{cfg['label']}] 模块验证...")
            key_modules = ["database.py", "monitor.py", "wechat_backend.py"]
            for m in key_modules:
                vok = verify_module(cfg, m, dry_run)
                print(f"  {'✅' if vok else '❌'} {m}")

        if health_ok:
            print(f"\n✅ 部署完成! API: http://{cfg['host']}:5050")
            print(f"   看板: http://{cfg['host']}:5050/dashboard")
            print(f"   健康: http://{cfg['host']}:5050/health")
            return True
        else:
            print(f"\n⚠️ 文件已部署但 API 健康检查失败")
            print(f"   查看日志: ssh {cfg['user']}@{cfg['host']} 'tail -50 /tmp/api.log'")
            return False
    else:
        print(f"\n✅ 文件同步完成 (未重启服务)")
        return True


def check_ssh_available() -> bool:
    """检测本地是否有 SSH/SCP 命令"""
    try:
        r = subprocess.run(["ssh", "-V"], capture_output=True, text=True, timeout=5)
        return r.returncode in (0, 255)  # ssh -V returns 255 on some versions
    except:
        return False


def manual_deploy_instructions(env: str = "production"):
    """输出手动部署命令（当 SSH 不可用时）"""
    cfg = SERVERS[env]
    src_dir = LOCAL_DIR
    remote_dir = cfg["remote_dir"]

    print(f"\n{'='*60}")
    print("手动部署命令")
    print(f"{'='*60}")
    print(f"\n# 1. 从本地拷贝文件到 {cfg['label']}服务器:")
    for f in DEPLOY_FILES:
        local = os.path.join(src_dir, f)
        if os.path.isfile(local):
            print(f"scp {local} {cfg['user']}@{cfg['host']}:{remote_dir}/")

    print(f"\n# 2. SSH 到服务器:")
    print(f"ssh {cfg['user']}@{cfg['host']}")

    print(f"\n# 3. 在服务器上重启 API:")
    print(f"pkill -f 'python3 api.py'")
    print(f"cd {remote_dir}")
    print(f"nohup python3 api.py > /tmp/api.log 2>&1 &")

    print(f"\n# 4. 验证:")
    print(f"curl http://localhost:5050/health")


def main():
    parser = argparse.ArgumentParser(description="History Pipeline 一键部署")
    parser.add_argument("--dev", action="store_true", help="部署到开发服务器")
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    parser.add_argument("--files-only", action="store_true", help="仅同步文件")
    parser.add_argument("--restart-only", action="store_true", help="仅重启服务")
    parser.add_argument("--env", action="store_true", help="同步 .env 文件到服务器")
    parser.add_argument("--manual", action="store_true", help="输出手动部署命令")
    args = parser.parse_args()

    env = "development" if args.dev else "production"

    if args.manual:
        manual_deploy_instructions(env)
        return

    if not check_ssh_available():
        print("⚠️ 未检测到 ssh 命令。显示手动部署指引...")
        manual_deploy_instructions(env)
        return

    success = deploy(
        env=env,
        dry_run=args.dry_run,
        files_only=args.files_only,
        restart_only=args.restart_only,
        sync_env=args.env,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
