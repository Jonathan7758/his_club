# AGENTS.md — 项目工作指引

## 当前状态

历史公众号AI内容工作流 — **MVP v3.0 完成**
项目文档: `docs/01-08` 共8份设计文档
开发纲领: `CLAUDE.md`（完整技术细节）
架构实现度: **~98%** (28/28 模块完成)

## 服务器

| 用途 | IP | SSH |
|------|-----|-----|
| 生产 | 124.174.42.6 | root/1Qxcjyb!@ |
| 开发(备) | 115.190.167.220 | root/1Qxcjyb!@ |

## 核心代码 (15 模块)

```
src/
├── api.py              — FastAPI :5050, 35个端点
├── generator.py        — ForumEngine 7维辩论 + 双源验证 + 事实校验
├── hotspot_scanner.py  — NewsNow API + LLM历史过滤 + 豆瓣辅证
├── database.py         — PostgreSQL 6表持久化（含comments CRUD）
├── scheduler.py        — 三级时间窗口调度 (日/周/月)
├── connector.py        — 管道对接模块
├── fact_checker.py     — 事实断言→交叉验证→争议标注
├── douban.py           — 豆瓣书评+小组爬虫
├── mirofish.py         — MiroFish Lite 推演+生成管道
├── engines.py          — BettaFish 3引擎桥接
├── graph_analyzer.py   — 知识图谱分析(中心度/聚类/盲区)
├── mindspider_bridge.py — MindSpider深层爬取桥接 v2.0 (comments表路由)
├── analytics.py        — 历史文章7维诊断+批量分析
├── monitor.py          — Sentry+钉钉告警+日志轮转+磁盘清理 [NEW]
└── wechat_backend.py   — 公众号API对接框架(Token/草稿/发布/统计) [NEW]
```

## API 端点总览

```
POST /generate              — 选题生成（含事实校验+实体+情感）
GET  /hotspot               — 今日历史热点
POST /hotspot/generate      — 热点自动选题+生成
GET  /health                — 健康检查
GET  /trends?days=30        — 热点趋势统计
GET  /topic/{topic}/history  — 话题历史生成记录
GET  /hotspots/recent?days=7 — 近N天热点
POST /webhook/trigger/{window} — 手动触发调度(daily/weekly/monthly)
GET  /scheduler/status      — 调度器状态
GET  /mirofish/quick/{topic} — "历史如果"快速选题
POST /mirofish/predict      — 完整历史推演
POST /mirofish/generate     — 推演→文章一键生成
GET  /stats                 — 数据看板JSON
GET  /dashboard             — 数据看板HTML
GET  /graph/stats           — 知识图谱统计
GET  /graph/centrality      — 实体中心度
GET  /graph/clusters        — 话题聚类
GET  /graph/gaps            — 内容盲区
GET  /analyze/{topic}       — 三引擎并行分析
POST /analytics/diagnose    — 单篇文章诊断
POST /analytics/diagnose/url — URL诊断
GET  /monitor/health        — 系统健康指标 [NEW]
GET  /monitor/errors        — 错误统计 [NEW]
POST /monitor/cleanup       — 磁盘清理触发 [NEW]
GET  /comments/{post_id}     — 帖子评论查询 [NEW]
GET  /comments/stats         — 评论统计 [NEW]
GET  /wechat/status          — 微信对接状态 [NEW]
POST /wechat/push            — 话题生成→推送微信草稿 [NEW]
GET  /wechat/stats           — 拉取微信阅读数据 [NEW]
GET  /wechat/drafts          — 微信草稿箱列表 [NEW]
GET  /wechat/verify          — 微信服务器验证 [NEW]
```

## 下次继续

- MindSpider DeepSentimentCrawling: 需克隆 MediaCrawler 子模块（GitHub 被墙，需代理/镜像）
- 配置 DINGTALK_WEBHOOK / SENTRY_DSN (已可被 Telegram 替代)
- 知识图谱(Neo4j/GraphRAG) — 发现话题密度盲区
