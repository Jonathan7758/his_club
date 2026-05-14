# CLAUDE.md — 历史公众号系列分析引擎 开发纲领

> **最后更新**: 2026-05-14
> **当前阶段**: MVP v3.0 (已冻结) → **v4.0 已完成** ✅
> **重构方向**: 从"公众号内容生成"重构为"TG驱动的系列分析引擎"
> **设计文档**: `docs/10-v4-refactor-plan.md` (v4.0唯一权威设计文件)
> **开发模式**: 严格TDD (RED → GREEN → REFACTOR)

---

## 1. 项目概述

**项目名称**：历史公众号系列分析引擎 (History Series Analysis Engine)

**核心目标**：基于 BettaFish/MiroFish 多Agent技术，为微信公众号历史领域内容运营提供"多角度深度分析→系列子主题设计→MD文档导出"的分析工作流。

**v4.0 关键变化**:
- ❌ 移除公众号内容生成（图文/视频脚本）
- ❌ 移除微信API对接
- ✅ 保留并强化分析层（ForumEngine / MiroFish / 3Engines / 知识图谱）
- ✅ TG Bot 命令行入口
- ✅ 3维评分系统（互联网热度 / 角度独特度 / 预测传播热度）
- ✅ 系列子主题拆分 → MD文档导出

---

## 2. 服务器资产

| 服务器 | IP | 规格 | 角色 | 状态 |
|--------|-----|------|------|------|
| 生产 | 124.174.42.6 | 4C8G 火山引擎北京 | 主服务 | ✅ 运行中 |
| 开发 | 115.190.167.220 | 4C4G 火山引擎北京 | 开发测试 | ⚠️ 网络受限 |

**SSH**: root / 1Qxcjyb!@

---

## 3. v4.0 目标架构

### 3.1 模块清单

```
src/
├── tg_bot.py           — ⭐ Telegram Bot入口 (/analysis等命令)
├── session_manager.py  — ⭐ Session状态机 (内容收集→触发分析)
├── forum_engine.py     — ⭐ ForumEngine 7维辩论 (从generator.py拆分)
├── scorer.py           — ⭐ 3维评分引擎 + 证据
├── series_designer.py  — ⭐ 主主题→子系列拆分
├── doc_exporter.py     — ⭐ MD系列设计文档导出
│
├── hotspot_scanner.py  — ✅ 保留: NewsNow热点扫描(外部数据源)
├── douban.py           — ✅ 保留: 豆瓣书评+小组(外部数据源)
├── engines.py          — ✅ 保留: 3引擎桥接(外部数据源)
├── mirofish.py         — ✅ 保留: 7方利益博弈推演(内部辩论)
├── graph_analyzer.py   — ✅ 保留: 知识图谱分析(内部辩论)
├── fact_checker.py     — ✅ 保留: 事实校验(内部辩论)
├── database.py         — 🔧 重构: 新增 analysis_sessions / series_designs 表
├── api.py              — 🔧 裁剪: 移除生成类端点, 新增TG webhook
├── analytics.py        — 🔧 裁剪: 移除文章生成评测部分
├── scheduler.py        — 🔧 简化: 移除自动生成调度
├── monitor.py          — ✅ 保留: 告警+监控
├── mindspider_bridge.py— ✅ 保留
├── env_loader.py       — ✅ 保留
│
├── CONNECTOR.md        — ✕ 移除: connector.py
└── WECHAT_BACKEND.md   — ✕ 移除: wechat_backend.py
```

### 3.2 新架构数据流

```
TG /analysis → session_mgr(收集内容) → 用户确认主题
  → 外部数据源(hotspot/engines/douban) + 内部辩论(forum_engine/mirofish/graph/fact_check)
  → scorer(3维评分+证据) → 用户确认
  → series_designer(7维拆分+子主题) → 用户确认
  → scorer(子主题独立评分)
  → doc_exporter(MD导出) → TG返回
```

---

## 4. 技术栈

- **LLM**: DeepSeek-chat (sk-3ded85b7ccb4438fbe95ec7d45416e44)
- **数据库**: PostgreSQL 16 (localhost:5432, user:bettafish, pass:bettafish)
- **搜索验证**: 搜狗微信搜索 + 搜狗网页搜索
- **爬虫**: NewsNow API + Playwright (MindSpider)
- **Web**: FastAPI (port 5050, TG webhook)
- **TG**: python-telegram-bot
- **测试**: pytest + pytest-asyncio + pytest-cov
- **Python**: 3.12.3

---

## 5. 快速命令

```bash
# SSH到生产服务器
ssh root@124.174.42.6

# 重启API
pkill -f api.py
cd /opt/hisclub && nohup python3 api.py > /tmp/api.log 2>&1 &

# 运行测试
cd /opt/hisclub && python -m pytest tests/ -v

# 测试覆盖率
cd /opt/hisclub && python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## 6. 开发指令

### 6.1 TDD 铁律

每个新模块必须按以下顺序开发：
1. **RED**: 写测试 (`tests/test_xxx.py`), 运行确认失败
2. **GREEN**: 写最少代码使测试通过
3. **REFACTOR**: 在绿色状态下重构, 保持全绿

### 6.2 Phase 执行顺序

1. `session_manager.py` + `tg_bot.py` (基础设施)
2. `forum_engine.py` (从generator.py拆分)
3. `scorer.py` (评分引擎)
4. `series_designer.py` + `doc_exporter.py` (设计+导出)
5. 旧模块裁撤 (`connector.py`, `wechat_backend.py` 删除)
6. `api.py` 重构 + `database.py` 新增表
7. 集成测试 (端到端)

### 6.3 设计权威

所有v4.0开发决策以 `docs/10-v4-refactor-plan.md` 为准。冲突时以该文档为准。

---

## 7. v3.0 历史存档

v3.0 (公众号内容生成工作流) 已完成28/28模块, 35端点全部投产。v4.0在此基础上去掉生成层+微信对接, 转为纯分析引擎。如需回看v3.0架构, 参考 git tag `v3.0-final` (如已打标) 或 git log。

---

## 8. 完成情况

| 优先级 | 任务 | 状态 |
|--------|------|------|
| **P0** | Phase 1: session_manager + tg_bot (TDD) | ✅ 完成 |
| **P0** | Phase 2: forum_engine 拆分 (TDD) | ✅ 完成 |
| **P0** | Phase 3: scorer 评分引擎 (TDD) | ✅ 完成 |
| **P0** | Phase 4: series_designer + doc_exporter (TDD) | ✅ 完成 |
| **P0** | Phase 5: 旧模块裁撤 + api重构 (TDD) | ✅ 完成 |
| **P0** | Phase 6: 集成测试 | ✅ 完成 |
| **Bonus** | search 搜索验证模块 | ✅ 完成 |
| P1 | 知识图谱(Neo4j/GraphRAG) — 盲区检测升级 | 后续 |
| P2 | Web管理面板 | 远期 |

**总计: 164 tests, 0 failures** (6.56s, 14个测试文件)
