# CLAUDE.md — 历史公众号AI工作流 开发纲领

> **最后更新**: 2026-05-06
> **当前阶段**: MVP v3.0 — 全管道已跑通，35端点全部投产
> **架构实现度**: ~98% (28/28模块完成)
> **下次继续**: 见文末 "下一步开发任务"

---

## 1. 项目概述

**项目名称**：历史公众号AI内容工作流（History Content AI Pipeline）

**核心目标**：基于 BettaFish/MiroFish 多Agent技术，为微信公众号历史领域内容提供"热点发现→多角度分析→内容生成"的自动化工作流。

---

## 2. 服务器资产

| 服务器 | IP | 规格 | 角色 | 状态 |
|--------|-----|------|------|------|
| 生产 | 124.174.42.6 | 4C8G 火山引擎北京 | 主服务 | ✅ 运行中 |
| 开发 | 115.190.167.220 | 4C4G 火山引擎北京 | 开发测试 | ⚠️ 网络受限 |

**SSH**: root / 1Qxcjyb!@

---

## 3. 当前实现状态

### ✅ 已完成 (28/28 模块)

| 组件 | 文件 | 说明 |
|------|------|------|
| BettaFish | `/opt/hisclub/bettafish/` | Flask Web, PostgreSQL, Redis, Playwright |
| 内容生成器 | generator.py | 7维LLM辩论 + 搜狗双源验证 + 公号图文 + 视频脚本 |
| HTTP API | api.py | FastAPI :5050, 35个端点 |
| 管道对接 | connector.py | 一键获取 Markdown/视频简报 |
| 事实校验层 | fact_checker.py | 断言提取→交叉验证→争议标注→来源追溯 |
| 数据存储层 | database.py | PostgreSQL, 6表持久化 + comments CRUD |
| 时间调度器 | scheduler.py | 日6:00扫描/周一8:00汇总/月1日9:00前瞻 |
| 豆瓣爬虫 | douban.py | 历史书评+小组讨论+标签热书 |
| MiroFish Lite | mirofish.py | 7方利益体5轮博弈 + 推演→文章管道 |
| ForumEngine | generator.py | 7维完整 (政治/经济/军事/文化/人物/科技/地理) |
| MindSpider桥接 | mindspider_bridge.py | v2.0 两阶段同步: content→posts, comment→comments |
| 知识图谱分析 | graph_analyzer.py | 中心度/聚类/盲区(基于entity_relations) |
| 3 Engine桥接 | engines.py | QueryEngine/MediaEngine/InsightEngine |
| 数据看板 | api.py | /stats JSON + /dashboard HTML |
| 文章诊断 | analytics.py | 7维对比诊断 + 批量分析 + URL抓取 |
| 监控告警 [NEW] | monitor.py | Sentry+钉钉+日志轮转+磁盘清理 |
| 公众号对接 [NEW] | wechat_backend.py | Token管理/素材/草稿/发布/统计 |

---

## 4. 技术栈

- **LLM**: DeepSeek-chat (sk-3ded85b7ccb4438fbe95ec7d45416e44)
- **数据库**: PostgreSQL 16 (localhost:5432, user:bettafish, pass:bettafish)
- **搜索验证**: 搜狗微信搜索 + 搜狗网页搜索
- **爬虫**: NewsNow API + Playwright (MindSpider)
- **Web**: FastAPI (port 5050)
- **Python**: 3.12.3

---

## 5. 快速启动命令

```bash
# SSH到生产服务器
ssh root@124.174.42.6

# 重启API
pkill -f api.py
cd /opt/hisclub && nohup python3 api.py > /tmp/api.log 2>&1 &

# 验证
curl http://localhost:5050/health

# 测试生成
curl -X POST http://localhost:5050/generate -H "Content-Type: application/json" -d '{"topic":"安史之乱"}'

# 一键部署（本地执行）
python C:\projects\Ai-hisclub\deploy.py
```

---

## 6. 数据流架构

```
NewsNow API ─┬─→ hot_topics (LLM历史过滤)
             └─→ posts (原始热点)

豆瓣爬虫 ──────→ posts (书评+小组)

generate() ────→ generations (完整JSON)
             ├─→ entity_relations (LLM NER)
             └─→ sentiment_labels (LLM 5维情感)

MiroFish ──────→ /mirofish/generate (推演→文章)

3 Engines ─────→ /analyze/{topic} (并行分析)

调度器 ────────→ 日扫描/周汇总/月前瞻 (自动触发)
```

---

## 7. 下一步开发任务

**P2: 部署与运营**
- 部署到生产服务器 (124.174.42.6) 验证所有改动
- MindSpider `--complete` 大规模爬取启动 → 填充comments表
- 配置 WECHAT_APPID/WECHAT_APPSECRET 激活公众号完整对接
- 配置 DINGTALK_WEBHOOK / SENTRY_DSN 激活告警
- 知识图谱(Neo4j/GraphRAG) — 发现话题密度盲区
- 事实校验存疑项在文章中的显示优化

**P3: 功能增强**
- MiroFish推演结果接入生成管道 — "/mirofish/predict" 输出注入 /generate
- 数据看板(公众号后台回传) — 追踪阅读量/完读率
