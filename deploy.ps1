$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Server = "124.174.42.6"
$User = "root"
$RemoteDir = "/opt/hisclub"
$LocalSrc = "C:\projects\Ai-hisclub\src"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "部署到生产服务器: $Server" -ForegroundColor Cyan
Write-Host "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ── 文件列表 ──
$Files = @(
    "api.py", "generator.py", "hotspot_scanner.py", "database.py",
    "scheduler.py", "connector.py", "fact_checker.py", "douban.py",
    "mirofish.py", "engines.py", "graph_analyzer.py", "mindspider_bridge.py",
    "analytics.py", "monitor.py", "wechat_backend.py", "env_loader.py"
)

# ── 1. 上传 .env ──
Write-Host "`n[1/4] 上传 .env..." -ForegroundColor Yellow
$envPath = "C:\projects\Ai-hisclub\.env"
if (Test-Path $envPath) {
    scp -o StrictHostKeyChecking=no $envPath ${User}@${Server}:${RemoteDir}/.env
    ssh -o StrictHostKeyChecking=no ${User}@${Server} "chmod 600 ${RemoteDir}/.env"
    Write-Host "  .env -> OK" -ForegroundColor Green
} else {
    Write-Host "  .env 不存在，跳过" -ForegroundColor DarkYellow
}

# ── 2. 上传源文件 ──
Write-Host "`n[2/4] 上传 $($Files.Count) 个源文件..." -ForegroundColor Yellow
$ok = 0; $fail = 0
foreach ($f in $Files) {
    $local = Join-Path $LocalSrc $f
    if (Test-Path $local) {
        scp -o StrictHostKeyChecking=no $local ${User}@${Server}:${RemoteDir}/
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK  $f" -ForegroundColor Green
            $ok++
        } else {
            Write-Host "  FAIL $f" -ForegroundColor Red
            $fail++
        }
    } else {
        Write-Host "  SKIP $f (本地不存在)" -ForegroundColor DarkYellow
    }
}
Write-Host "  结果: $ok 成功, $fail 失败" -ForegroundColor Yellow

# ── 3. 重启 API ──
Write-Host "`n[3/4] 重启 API 服务..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no ${User}@${Server} @"
pkill -f 'python3 api.py' 2>/dev/null
sleep 2
cd ${RemoteDir}
nohup python3 api.py > /tmp/api.log 2>&1 &
echo "  API 重启命令已执行"
"@
Write-Host "  等待 5 秒..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# ── 4. 健康检查 ──
Write-Host "`n[4/4] 健康检查..." -ForegroundColor Yellow
$health = ssh -o StrictHostKeyChecking=no ${User}@${Server} "curl -s http://localhost:5050/health"
if ($health -match '"status":"ok"') {
    Write-Host "  API 健康: $health" -ForegroundColor Green
} else {
    Write-Host "  API 异常: $health" -ForegroundColor Red
    Write-Host "  查看日志: ssh root@$Server 'tail -30 /tmp/api.log'" -ForegroundColor DarkYellow
}

# ── 微信状态 ──
Write-Host "`n微信对接状态:" -ForegroundColor Yellow
$wxStatus = ssh -o StrictHostKeyChecking=no ${User}@${Server} "curl -s http://localhost:5050/wechat/status"
Write-Host "  $wxStatus" -ForegroundColor Cyan

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "部署完成!" -ForegroundColor Green
Write-Host "  API:    http://${Server}:5050"
Write-Host "  看板:   http://${Server}:5050/dashboard"
Write-Host "  健康:   http://${Server}:5050/health"
Write-Host "============================================================" -ForegroundColor Cyan
