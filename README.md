# History Content AI Pipeline — 历史公众号 AI 内容工作流

> 基于 BettaFish/MiroFish 多 Agent 技术的微信公众平台历史领域内容自动化生产系统

**MVP v3.0** | 28/28 模块完成 | 35 API 端点 | 4,300+ 行代码

---

## 架构概览

```
调度层 ──── 日扫描(06:00) / 周汇总(周一08:00) / 月前瞻(每月1日09:00)
  │
数据层 ──── NewsNow API / 搜狗双源 / 豆瓣爬虫 / MindSpider 桥接 / PostgreSQL
  │
分析层 ──── ForumEngine 7维辩论 / MiroFish 反事实推演 / 3引擎并排分析
  │
验证层 ──── 搜狗网页交叉验证 / 事实断言提取 / 段落级争议标注
  │
生成层 ──── 公众号 HTML / 视频分镜脚本 / 金句提取 / 延伸阅读
  │
输出层 ──── FastAPI :5050 / HTML 预览 / 微信草稿对接 / Telegram 告警
```

## 数据流

```
NewsNow API ─┬─→ hot_topics (LLM 历史过滤)
             └─→ posts (原始热点存底)

豆瓣爬虫 ────→ posts (书评+小组讨论)

MindSpider  ──→ daily_news ─→ mindspider_bridge ─→ posts/comments

generate() ──→ generations (完整 JSON 文章)
          ├─→ entity_relations (LLM命名实体抽取)
          └─→ sentiment_labels (LLM 5维情感标注)

MiroFish  ───→ /mirofish/generate (推演 → 角度 → 文章)
```

## 项目结构

```
src/
├── api.py              — FastAPI HTTP 接口, 35 端点
├── generator.py        — ForumEngine 7维辩论 + 双源验证 + 文章生成
├── hotspot_scanner.py  — NewsNow API + LLM 历史过滤 + 豆瓣辅证
├── database.py         — PostgreSQL 6表持久化 + comments CRUD
├── scheduler.py        — 三级时间窗口调度 (自动后台线程)
├── connector.py        — 管道对接模块 (Python SDK)
├── fact_checker.py     — 事实断言提取 → 交叉验证 → 段落级争议标注
├── douban.py           — 豆瓣图书搜索 + 小组讨论 + 标签热书爬虫
├── mirofish.py         — MiroFish Lite: 7方利益体5轮推演 + 一键生成
├── engines.py          — BettaFish 3引擎桥接 (Query/Media/Insight)
├── graph_analyzer.py   — 知识图谱分析 (中心度/聚类/内容盲区)
├── mindspider_bridge.py — MindSpider 数据同步 v2.0 (content→posts, comment→comments)
├── analytics.py        — 历史文章 7 维对比诊断 + 批量分析 + URL 抓取
├── monitor.py          — Sentry + Telegram 告警 + 日志轮转 + 磁盘清理
├── wechat_backend.py   — 微信公众号 API (Token/素材/草稿/发布/数据)

.env.example            — 环境变量模板
deploy.py / deploy.ps1  — 一键部署脚本
scripts/                — 工具脚本
docs/                   — 9 份设计文档
```

## 核心功能

### 1. 内容生成 (`POST /preview`)

```bash
curl -X POST http://localhost:5050/preview \
  -H "Content-Type: application/json" \
  -d '{"topic":"玄武门之变","inject_mirofish":true}'
```

**生成流程**（耗时 ~5分钟）：

| 阶段 | 耗时 | 说明 |
|------|------|------|
| 热度扫描 | 2s | 搜狗微信/网页双源检测选题新颖度 |
| **ForumEngine 辩论** | 90s | 7 维专家 Agent 3 轮辩论 + 交叉批判 |
| **MiroFish 反事实** | 60s | 7 方利益体 5 轮推演 → "历史如果"角度 |
| 搜索验证 | 10s | 搜狗网页交叉验证每个角度的新颖度 |
| 文章生成 | 30s | LLM 基于高新颖度角度生成 3-4 节正文 |
| **事实校验** | 60s | 提取事实断言 → 网页验证 → 争议标注 |
| 视频脚本 | 15s | 90-120秒分镜脚本 + 核心记忆点 |
| 实体/情感 | 20s | 命名实体关系抽取 + 5 维情感标签 |

### 2. 多维度分析角度

ForumEngine 7 维辩论：
- **政治制度** | **经济财政** | **军事战略** | **文化社会**
- **关键人物** | **技术演进** | **地理环境**

MiroFish 反事实推演（额外注入 3 个"历史如果"角度）

### 3. 事实校验

```
断言提取 → 搜狗网页交叉验证 → 争议标注
         ├─ verified (已证实)
         ├─ disputed (存争议) → 段落级结构化注记
         ├─ likely_true (可能为真)
         └─ unverifiable (无法验证)
```

### 4. 文章诊断 (`POST /analytics/diagnose`)

对已发布文章做 7 维评分：写作质量、传播潜力、角度多样性、事实准确性、情感均衡、竞品重叠、基准差距。

---

## 部署

### 环境要求

- Python 3.12+
- PostgreSQL 16
- DeepSeek API Key

### 一键部署

```bash
# 部署代码 + 环境变量到生产服务器
python deploy.py --env

# 预览模式 (不执行)
python deploy.py --dry-run

# PowerShell
powershell -ExecutionPolicy Bypass -File deploy.ps1
```

### 手动部署

```bash
# SSH 到服务器
ssh root@124.174.42.6

# 重启 API
pkill -f api.py
cd /opt/hisclub && nohup python3 api.py > /tmp/api.log 2>&1 &

# 验证
curl http://localhost:5050/health
```

### 环境变量

复制 `.env.example` 为 `.env`：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 |
| `WECHAT_APPID` | 可选 | 公众号 AppID |
| `WECHAT_APPSECRET` | 可选 | 公众号 AppSecret |
| `TELEGRAM_BOT_TOKEN` | 推荐 | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 推荐 | Telegram 接收者 Chat ID |
| `DB_HOST/PORT/NAME/USER/PASS` | ✅ | PostgreSQL 连接 |

---

## API 端点

### 内容生成
| 端点 | 说明 |
|------|------|
| `POST /generate` | 完整生成（含事实校验、实体、情感） |
| `POST /preview` | 生成并返回 HTML 格式内容（不推送） |
| `GET /preview/latest` | 最近一篇的 HTML 预览 |

### 热点扫描
| 端点 | 说明 |
|------|------|
| `GET /hotspot` | 今日历史热点 |
| `POST /hotspot/generate` | 热点自动选题+生成 |
| `GET /trends?days=30` | 热点趋势统计 |
| `GET /hotspots/recent?days=7` | 近 N 天热点 |

### MiroFish 推演
| 端点 | 说明 |
|------|------|
| `GET /mirofish/quick/{topic}` | 快速"历史如果"选题 |
| `POST /mirofish/predict` | 完整历史推演 (3-7轮) |
| `POST /mirofish/generate` | 推演→文章一键生成 |

### 文章诊断
| 端点 | 说明 |
|------|------|
| `POST /analytics/diagnose` | 单篇 7 维诊断 |
| `POST /analytics/diagnose/url` | 微信 URL → 自动抓取 → 诊断 |

### 知识图谱
| 端点 | 说明 |
|------|------|
| `GET /graph/stats` | 图谱统计 |
| `GET /graph/centrality` | 实体中心度 |
| `GET /graph/clusters` | 话题聚类 |
| `GET /graph/gaps` | 内容盲区 |

### 调度器
| 端点 | 说明 |
|------|------|
| `GET /scheduler/status` | 调度状态 |
| `POST /webhook/trigger/{window}` | 手动触发 (daily/weekly/monthly) |

### 微信对接
| 端点 | 说明 |
|------|------|
| `GET /wechat/status` | 对接状态 |
| `GET /wechat/drafts` | 草稿箱列表 |
| `GET /wechat/stats` | 图文阅读数据 |
| `GET /wechat/verify` | 服务器验证回调 |

### 监控运维
| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /stats` | 数据看板 JSON |
| `GET /dashboard` | 数据看板 HTML |
| `GET /monitor/health` | 系统健康指标 |
| `GET /monitor/errors` | 错误统计 |
| `POST /monitor/cleanup` | 磁盘清理 |

### 数据
| 端点 | 说明 |
|------|------|
| `GET /topic/{topic}/history` | 话题历史生成 |
| `GET /comments/{post_id}` | 帖子评论 |
| `GET /comments/stats` | 评论统计 |

---

## 告警 & 运维

| 通道 | 配置 | 状态 |
|------|------|------|
| **Telegram** | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | ✅ 推荐 |
| 钉钉 | `DINGTALK_WEBHOOK` | 可选 |
| Sentry | `SENTRY_DSN` | 可选 |
| 日志轮转 | 自动: 10MB/5备份 | ✅ |
| 磁盘清理 | 日志 30 天 / 报告 90 天 | ✅ |
