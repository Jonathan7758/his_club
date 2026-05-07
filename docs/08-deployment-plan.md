# 08 — 部署方案

## 1. 环境要求

| 组件 | 版本要求 |
|------|---------|
| Docker | ≥ 24.x |
| Docker Compose | ≥ 2.x |
| Python | 3.11-3.12 |
| Node.js（MiroFish前端） | ≥ 18 |
| PostgreSQL | 15+ |
| 操作系统 | Ubuntu 22.04 LTS（推荐） |

---

## 2. 部署架构（两套方案）

> **推荐方案 B（火山云单区）**：历史公众号数据源几乎全是国内平台，单区方案更简洁、成本更低、延迟更优。

### 方案 A：HK+MY 双区

#### A.1 香港节点（计算层）

```
hk-node (4C8G, Ubuntu 22.04)
├── Flask Web UI (port 5000)
├── ForumEngine (7历史Agent)
├── ReportEngine
├── QueryEngine / MediaEngine / InsightEngine
├── MiroFish Lite backend (port 5001)
├── MiroFish Lite frontend (port 3000, 可选)
├── APScheduler (日/周/月定时任务)
└── Nginx 反向代理
```

#### A.2 马来节点（数据层）

```
my-node (4C8G, Ubuntu 22.04)
├── PostgreSQL 15 (port 5432)
├── MindSpider 爬虫集群
│   ├── 知乎爬虫
│   ├── B站爬虫
│   ├── 微博爬虫
│   ├── 豆瓣爬虫
│   └── 微信搜索
├── Playwright (Chromium)
├── 代理IP池管理
└── Redis (缓存+任务队列)
```

#### A.3 网络拓扑

```
公网
 │
 ├── HK Node (公网IP)
 │   ├── 开放: 80/443 (Nginx)
 │   ├── 内部: 5000 (Flask), 5001 (MiroFish)
 │   └── VPN/SSH隧道 ────────────┐
 │                                │
 ├── MY Node (公网IP, 或仅HK可访问) │
 │   ├── 开放: 仅SSH              │
 │   ├── PostgreSQL: 仅内网 ◄─────┘
 │   └── Playwright爬虫: 通过代理IP出站
 │
 └── LLM API: dashscope.aliyuncs.com (千问)
              api.deepseek.com (DeepSeek)
```

---

---

### 方案 B：火山云单区 ★ 推荐

#### B.1 资源清单（已有）

| 资源 | 规格 | 用途 | 月费 |
|------|------|------|------|
| ECS-生产 | 4C8G, 火山引擎北京 | 全服务（PG+应用+爬虫+定时任务） | 已有 |
| ECS-开发 | 4C4G, 火山引擎北京 | 开发/测试环境 | 已有 |
| Arkclaw | 2C4G | V1.0后MiroFish推演专用(可选) | ¥50 |

#### B.2 单机 docker-compose.yml

```yaml
# 火山引擎北京 4C8G 单机全服务
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: bettafish
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: bettafish
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  bettafish:
    image: bettafish:latest
    ports:
      - "5000:5000"
    env_file:
      - .env
    environment:
      DB_HOST: postgres
      REDIS_HOST: redis
    volumes:
      - ./final_reports:/app/final_reports
      - ./logs:/app/logs
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  mirofish-backend:  # V1.0启用: docker compose --profile v1 up
    image: mirofish-backend:latest
    ports:
      - "5001:5001"
    env_file:
      - .env
    profiles:
      - v1

  mindspider:
    build: ./mindspider
    env_file:
      - .env
    environment:
      DB_HOST: postgres
    depends_on:
      - postgres
    restart: unless-stopped

  scheduler:
    build: ./scheduler
    env_file:
      - .env
    depends_on:
      - bettafish
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - bettafish
    restart: unless-stopped

volumes:
  pgdata:
```

#### B.3 ICP 备案流程

火山云要求域名必须完成ICP备案才能解析。流程：

1. 购买域名（如已有则跳过）
2. 在火山云控制台提交备案申请（需企业/个人实名认证）
3. 火山云初审（1-3个工作日）
4. 管局审核（约1-3周，各省不同）
5. 备案通过后域名可正常解析

> **备案期间**：可用 ECS 公网 IP 直接访问，不影响开发和调试。
> 如使用微信公众号/视频号发布，本身已有备案域名，无需额外备案。

---

## 3. Docker Compose 部署详情

### 3.1 香港节点 docker-compose.yml（方案A）

```yaml
version: '3.8'
services:
  bettafish:
    image: bettafish:latest  # 基于666ghj/BettaFish Dockerfile构建
    ports:
      - "5000:5000"
    env_file:
      - .env
    volumes:
      - ./final_reports:/app/final_reports
      - ./logs:/app/logs
    restart: unless-stopped

  mirofish-backend:
    image: mirofish-backend:latest  # 基于666ghj/MiroFish backend构建
    ports:
      - "5001:5001"
    env_file:
      - .env
    depends_on:
      - bettafish
    restart: unless-stopped

  scheduler:
    build: ./scheduler
    env_file:
      - .env
    depends_on:
      - bettafish
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - bettafish
    restart: unless-stopped
```

### 3.2 马来节点 docker-compose.yml

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: bettafish
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: bettafish
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  mindspider:
    build: ./mindspider
    env_file:
      - .env
    environment:
      DB_HOST: postgres
    depends_on:
      - postgres
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

volumes:
  pgdata:
```

---

## 4. 环境变量配置 (.env)

```bash
# ============ 数据库 ============
DB_HOST=my-node-internal-ip   # 马来节点内网IP
DB_PORT=5432
DB_USER=bettafish
DB_PASSWORD=<your-password>
DB_NAME=bettafish
DB_DIALECT=postgresql

# ============ LLM配置 ============
# 通义千问（主力）
QWEN_API_KEY=<your-key>
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_NAME=qwen-plus

# DeepSeek（辅助，长文本/报告生成）
DEEPSEEK_API_KEY=<your-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL_NAME=deepseek-chat

# ============ BettaFish Agent LLM ============
# 各Agent默认使用千问，ReportEngine使用DeepSeek
INSIGHT_ENGINE_API_KEY=${QWEN_API_KEY}
INSIGHT_ENGINE_BASE_URL=${QWEN_BASE_URL}
INSIGHT_ENGINE_MODEL_NAME=${QWEN_MODEL_NAME}

MEDIA_ENGINE_API_KEY=${QWEN_API_KEY}
MEDIA_ENGINE_BASE_URL=${QWEN_BASE_URL}
MEDIA_ENGINE_MODEL_NAME=${QWEN_MODEL_NAME}

QUERY_ENGINE_API_KEY=${QWEN_API_KEY}
QUERY_ENGINE_BASE_URL=${QWEN_BASE_URL}
QUERY_ENGINE_MODEL_NAME=${QWEN_MODEL_NAME}

REPORT_ENGINE_API_KEY=${DEEPSEEK_API_KEY}
REPORT_ENGINE_BASE_URL=${DEEPSEEK_BASE_URL}
REPORT_ENGINE_MODEL_NAME=${DEEPSEEK_MODEL_NAME}

# ============ MiroFish ============
LLM_API_KEY=${QWEN_API_KEY}
LLM_BASE_URL=${QWEN_BASE_URL}
LLM_MODEL_NAME=qwen-plus
ZEP_API_KEY=<your-zep-key>

# ============ 搜索API ============
ANSPIRE_API_KEY=<your-anspire-key>

# ============ 安全 ============
# 马来节点postgres仅允许HK节点IP访问
# 可通过 iptables 或 pg_hba.conf 配置
```

---

## 5. 部署步骤

### Step 1: 服务器初始化（双节点）

```bash
# 两台服务器均执行
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose git curl
sudo systemctl enable docker
```

### Step 2: 马来节点 — 数据库+爬虫

```bash
cd /opt/hisclub-my
git clone <your-repo> .
cp .env.example .env
# 编辑 .env 填入配置
docker compose up -d postgres redis
# 初始化数据库
docker compose run mindspider python main.py --setup
# 启动爬虫
docker compose up -d
```

### Step 3: 香港节点 — 分析+生成

```bash
cd /opt/hisclub-hk
git clone <your-repo> .
cp .env.example .env
# 编辑 .env, DB_HOST 指向马来节点内网IP
docker compose up -d
```

### Step 4: 配置VPN隧道（如需要）

```bash
# 在马来节点（如果只有内网）
ssh -R 5432:localhost:5432 hk-node
# 或在香港节点配置WireGuard
```

### Step 5: 验证

```bash
# 香港节点
curl http://localhost:5000/health
# 应返回 {"status": "ok"}
curl http://localhost:5001/health

# 马来节点
docker compose exec postgres psql -U bettafish -c "SELECT 1"
docker compose logs mindspider | grep "ready"
```

---

## 6. CI/CD 建议

```yaml
# .github/workflows/deploy.yml 示例
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy-hk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to HK
        run: |
          ssh hk-node "cd /opt/hisclub-hk && git pull && docker compose up -d --build"
  deploy-my:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to MY
        run: |
          ssh my-node "cd /opt/hisclub-my && git pull && docker compose up -d --build"
```

---

## 7. 监控与告警

### 关键指标

| 指标 | 工具 | 告警阈值 |
|------|------|---------|
| 服务器CPU/内存 | Prometheus + Grafana | CPU > 80%持续10min |
| LLM API延迟 | 应用内日志 | P95 > 15s |
| 爬虫成功率 | 应用内计数 | 连续1小时 < 60% |
| 日报生成成功率 | 应用内计数 | 任意一天失败 |
| 数据库连接数 | pg_stat_activity | 活跃连接 > 50 |
| 磁盘使用率 | node_exporter | > 80% |

### 简化方案（MVP阶段）

- Docker日志 → Loki → 邮件告警
- 健康检查脚本 + cron + 企业微信通知
