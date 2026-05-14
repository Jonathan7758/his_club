# AGENTS.md — 项目工作指引

## 当前状态

历史公众号系列分析引擎 — **v4.0 已完成** ✅
v3.0 (公众号内容生成工作流) 已冻结归档
设计文档: `docs/10-v4-refactor-plan.md` (v4.0 唯一权威)
开发纲领: `CLAUDE.md` (完整技术细节)
开发模式: **严格TDD** (RED → GREEN → REFACTOR)
测试: **164 tests, 0 failures** (全部6个Phase通过)

## 服务器

| 用途 | IP | SSH |
|------|-----|-----|
| 生产 | 124.174.42.6 | root/1Qxcjyb!@ |
| 开发(备) | 115.190.167.220 | root/1Qxcjyb!@ |

## v4.0 模块总览

### 新模块 (TDD先行) ⭐
```
src/
├── tg_bot.py           — Telegram Bot: /analysis /restart /status /export
├── tg_bot_runner.py    — TG Bot 启动/停止管理
├── session_manager.py  — Session状态机: 内容收集→触发分析
├── forum_engine.py     — ForumEngine 7维辩论 (从generator.py拆分)
├── scorer.py           — 3维评分: 热度/独特度/传播 + 证据
├── series_designer.py  — 主主题→7维子系列拆分+大纲+金句
├── doc_exporter.py     — MD系列设计文档导出
└── search.py           — 搜索验证 (搜狗微信+网页)
```

### 保留模块 ✅
```
src/
├── hotspot_scanner.py  — NewsNow热点 (外部数据源)
├── douban.py           — 豆瓣书评 (外部数据源)
├── engines.py          — 3引擎桥接 (外部数据源)
├── mirofish.py         — 7方博弈推演 (内部辩论)
├── graph_analyzer.py   — 知识图谱 (内部辩论)
├── fact_checker.py     — 事实校验 (内部辩论)
├── monitor.py          — 告警+监控
├── mindspider_bridge.py
└── env_loader.py
```

### 重构/裁剪模块 🔧
```
src/
├── database.py   — 新增 analysis_sessions / series_designs 表
├── api.py        — 移除生成端点, 新增TG webhook
├── analytics.py  — 裁剪文章评测部分
└── scheduler.py  — 简化, 移除自动生成
```

### 移除模块 ✕
```
src/connector.py     — 管道对接
src/wechat_backend.py — 公众号API
```

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行覆盖率
python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 运行单个模块测试
python -m pytest tests/test_scorer.py -v
```

## 关键约定

1. **TDD铁律**: 禁止跳过测试直接写实现
2. **设计权威**: 任何设计歧义以 `docs/10-v4-refactor-plan.md` 为准
3. **Phase顺序**: 严格按 Phase 1→6 执行, 不跳跃
4. **代码风格**: 参考现有代码库的 Python 规范 (无注释/最小化/docstring仅关键处)

## 完成情况

- ✅ Phase 1: session_manager + tg_bot (基础设施)
- ✅ Phase 2: forum_engine (7维辩论)
- ✅ Phase 3: scorer (3维评分引擎)
- ✅ Phase 4: series_designer + doc_exporter (设计+导出)
- ✅ Phase 5: 旧模块裁撤 + API重构
- ✅ Phase 6: 集成测试
- ✅ Bonus: search (搜索验证模块)
- **164 tests, 0 failures** — 全部通过

## 后续

- 生产部署: 数据库迁移 + TG webhook 配置
- P1: 知识图谱(Neo4j/GraphRAG) — 盲区检测升级
- P2: Web管理面板
