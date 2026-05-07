$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$DevServer   = "115.190.167.220"
$ProdServer  = "124.174.42.6"
$User        = "root"
$LocalSrc    = "C:\projects\Ai-hisclub\src"
$RemoteDir   = "/opt/hisclub"
$DevTemp     = "/tmp/hisclub_deploy"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "双跳部署: 本地 -> 开发($DevServer) -> 生产($ProdServer)" -ForegroundColor Cyan
Write-Host "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$Files = @(
    "api.py", "generator.py", "hotspot_scanner.py", "database.py",
    "scheduler.py", "connector.py", "fact_checker.py", "douban.py",
    "mirofish.py", "engines.py", "graph_analyzer.py", "mindspider_bridge.py",
    "analytics.py", "monitor.py", "wechat_backend.py", "env_loader.py"
)

# ═══════════════════════════════════════════════════════════
# Phase 1: 本地 → 开发服务器
# ═══════════════════════════════════════════════════════════
Write-Host "`n[Phase 1] 上传到开发服务器 $DevServer ..." -ForegroundColor Yellow

# 清理 + 创建临时目录
ssh -o StrictHostKeyChecking=no ${User}@${DevServer} "rm -rf ${DevTemp}; mkdir -p ${DevTemp}; echo [dev] ready"

# .env
$envPath = "C:\projects\Ai-hisclub\.env"
if (Test-Path $envPath) {
    Write-Host "  上传 .env -> dev" -ForegroundColor DarkGray
    scp -o StrictHostKeyChecking=no $envPath ${User}@${DevServer}:${DevTemp}/.env
}

# 源文件
$ok = 0
foreach ($f in $Files) {
    $local = Join-Path $LocalSrc $f
    if (Test-Path $local) {
        Write-Host "  上传 $f" -ForegroundColor DarkGray
        scp -o StrictHostKeyChecking=no -q $local ${User}@${DevServer}:${DevTemp}/
        $ok++
    }
}
Write-Host "  Phase 1 完成: $ok 个文件 -> dev" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════
# Phase 2: 开发服务器 → 生产服务器 (同DC高速)
# ═══════════════════════════════════════════════════════════
Write-Host "`n[Phase 2] 开发 -> 生产 $ProdServer (同数据中心) ..." -ForegroundColor Yellow

$result = ssh -o StrictHostKeyChecking=no ${User}@${DevServer} @"
# 从 dev 推文件到 prod
scp -o StrictHostKeyChecking=no ${DevTemp}/.env ${RemoteDir}/.env 2>/dev/null
chmod 600 ${RemoteDir}/.env 2>/dev/null || true

ok=0; fail=0
for f in ${DevTemp}/*.py; do
    if scp -o StrictHostKeyChecking=no -q "\$f" ${ProdServer}:${RemoteDir}/ 2>/dev/null; then
        ok=\$((ok+1))
    else
        fail=\$((fail+1))
        echo "  FAIL: \$(basename \$f)"
    fi
done
echo "PHASE2_DONE ok=\$ok fail=\$fail"
"@

Write-Host "  $result" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════
# Phase 3: 重启生产 API
# ═══════════════════════════════════════════════════════════
Write-Host "`n[Phase 3] 重启生产 API..." -ForegroundColor Yellow

ssh -o StrictHostKeyChecking=no ${User}@${DevServer} @"
ssh -o StrictHostKeyChecking=no ${ProdServer} "
    pkill -f 'python3 api.py' 2>/dev/null
    sleep 2
    cd ${RemoteDir}
    nohup python3 api.py > /tmp/api.log 2>&1 &
    echo '[prod] API 重启命令已执行'
"
"@

Write-Host "  等待 8 秒..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

# ═══════════════════════════════════════════════════════════
# Phase 4: 健康检查 + 微信状态
# ═══════════════════════════════════════════════════════════
Write-Host "`n[Phase 4] 健康检查..." -ForegroundColor Yellow

$health = ssh -o StrictHostKeyChecking=no ${User}@${DevServer} "ssh -o StrictHostKeyChecking=no ${ProdServer} 'curl -s http://localhost:5050/health'"

if ($health -match '"status":"ok"') {
    Write-Host "  API 健康: $health" -ForegroundColor Green
} else {
    Write-Host "  API 异常: $health" -ForegroundColor Red
}

$wx = ssh -o StrictHostKeyChecking=no ${User}@${DevServer} "ssh -o StrictHostKeyChecking=no ${ProdServer} 'curl -s http://localhost:5050/wechat/status'"
Write-Host " 微信状态: $wx" -ForegroundColor Cyan

# 清理
ssh -o StrictHostKeyChecking=no ${User}@${DevServer} "rm -rf ${DevTemp}" 2>$null

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "部署完成!  API: http://${ProdServer}:5050/health" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
