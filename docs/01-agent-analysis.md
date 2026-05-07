# 01 — BettaFish & MiroFish 深度技术分析

## 1. 背景

郭航江（GitHub: 666ghj, 北京邮电大学大四学生）在 2025-2026 年间先后发布了两款开源多 Agent 系统：

| 项目 | 定位 | Stars | 发布时间 |
|------|------|-------|---------|
| **BettaFish（微舆）** | 多Agent舆情分析，分析过去和现在 | 40.7k | 2025年中 |
| **MiroFish** | 群体智能预测引擎，预测未来 | 59.1k | 2026年3月 |

**二者关系**：BettaFish 的分析终点 = MiroFish 的预测起点。前者生成的分析报告可直接作为后者的"种子信息"输入，形成"数据采集→分析→预测"的闭环。

---

## 2. BettaFish — 7引擎架构拆解

### 2.1 MindSpider（社媒爬虫系统）

**功能**：7x24小时 AI 驱动爬虫集群，覆盖微博、小红书、抖音、快手等 30+ 国内外主流社媒。

**技术要点**：
- 基于 Playwright 的浏览器自动化
- 两层爬取：BroadTopic（热点话题提取）→ DeepSentiment（深度评论爬取）
- 多平台适配器模式（`media_platform/` 目录下每个平台独立实现）
- 支持 PostgreSQL/MySQL 双数据库

**输出**：结构化舆情数据（话题、帖子、评论、情感标签）

### 2.2 QueryEngine（全网搜索 Agent）

**功能**：国内外网页搜索，采集新闻和公开信息。

**内部结构**：
- `nodes/` 目录下按搜索→格式化→总结的管道处理
- 支持多轮反思（默认2轮 `max_reflections=2`）
- 搜索结果可配置（`max_search_results=15`, `max_content_length=8000`）

### 2.3 MediaEngine（多模态分析 Agent）

**功能**：突破图文限制，深度解析抖音、快手等短视频内容及现代搜索引擎的结构化信息卡片。

**关键能力**：
- 视频内容理解（提取画面/字幕/音频信息）
- 图片OCR和语义分析
- 综合搜索限制（`comprehensive_search_limit=10`）

### 2.4 InsightEngine（私有数据库挖掘 Agent）

**功能**：接入私有业务数据库，将外部舆情与内部数据无缝融合。

**内部组件**：
- `keyword_optimizer.py` — 基于小参数Qwen的关键词优化中间件
- `sentiment_analyzer.py` — 集成多模型的情感分析：
  - BERT-LoRA 微调（中文情感）
  - GPT-2-LoRA 微调
  - Qwen3 小参数微调
  - 多语言情感分析
  - 传统机器学习（SVM等）
- SQLAlchemy 异步引擎 + 只读查询封装

### 2.5 ForumEngine（Agent 论坛协作机制）★ 核心差异化

**核心理念**：为不同 Agent 赋予独特工具集与思维模式，引入辩论主持人模型。

**工作流程**：
1. **并行启动**：QueryAgent、MediaAgent、InsightAgent 同时开始工作
2. **初步分析**：各Agent使用专属工具概览搜索
3. **策略制定**：基于初步结果制定分块研究策略
4. **循环辩论**（核心）：
   - ForumEngine 监控各Agent发言
   - LLM 主持人生成引导性辩论方向
   - 各Agent通过 `forum_reader` 工具读取彼此发言
   - 调整研究方向，进行链式思维碰撞
5. **结果整合**：ReportAgent 收集所有分析和论坛内容

**优势**：单一模型容易陷入思维局限，多模型交流导致同质化；Forum机制通过结构化辩论避免了这两个问题。

### 2.6 ReportEngine（智能报告生成）

**流程**：模板选择→文档布局→篇幅规划→章节生成→IR中间表示→渲染

**技术实现**：
- `template_parser.py` — Markdown模板切片与解析
- `ir/schema.py` — 报告IR（Intermediate Representation）契约定义
- `stitcher.py` — 基于IR装订为完整文档
- 多格式渲染：HTML（交互式）/ PDF（WeasyPrint）/ Markdown
- `chapter_generation_node.py` — 章节级JSON生成+校验

### 2.7 SentimentAnalysisModel（情感分析模型集合）

提供5种情感分析方案，从微调BERT到传统ML，可按需选用。

---

## 3. MiroFish — 群体智能预测引擎

### 3.1 核心架构

基于 CAMEL-AI 的 OASIS（Open Agent Social Interaction Simulations）框架构建。

**5个处理阶段**：

```
Graph Building → Environment Setup → Simulation → Report Generation → Deep Interaction
```

### 3.2 Graph Building（图构建）

- **种子提取**：从输入材料（如BettaFish报告）提取关键实体和事件
- **个体/集体记忆注入**：将历史信息和背景知识注入知识图谱
- **GraphRAG**：基于图结构的检索增强生成，支持大规模知识查询

### 3.3 Environment Setup（环境设定）

- **实体关系提取**：从种子信息中提取人物、组织、事件的关系
- **Persona 生成**：为每个模拟Agent生成独立人格（职业、性格、立场、知识背景）
- **Agent 配置注入**：将人格+记忆+行为逻辑注入每个Agent

### 3.4 Simulation（模拟推演）★ 核心

- **双平台并行模拟**：同时运行多组不同初始条件的模拟
- **自动解析预测需求**：从自然语言描述提取推演变量
- **动态时序记忆更新**：使用 Zep Cloud 管理 Agent 的长期记忆
- **数千Agent自由交互**：每个Agent有独立人格和记忆，在模拟空间中产生涌现行为
- **God视角干预**：用户可在推演过程中注入变量（如"如果某事件提前发生"）

### 3.5 Report Generation & Deep Interaction

- ReportAgent 与模拟后环境深度交互，提取关键推演路径
- 支持与模拟世界中任意Agent对话
- 输出预测报告

### 3.6 技术栈

- **前端**：Vue 3
- **后端**：Python（FastAPI-like）
- **记忆**：Zep Cloud（免费额度可覆盖基础使用）
- **图数据库**：GraphRAG（知识图谱）
- **模拟引擎**：OASIS（CAMEL-AI）
- **部署**：Docker Compose（前后端 + 数据库）

---

## 4. 二者协同关系

```
BettaFish                           MiroFish
┌─────────────────────┐            ┌─────────────────────┐
│  MindSpider (爬取)    │            │  Graph Building      │
│  QueryEngine (搜索)   │──种子信息──▶│  Environment Setup    │
│  MediaEngine (多模态)  │            │  Simulation (推演)    │
│  InsightEngine (挖掘)  │            │  Report Generation   │
│  ForumEngine (辩论)    │            │  Deep Interaction    │
│  ReportEngine (报告)   │            │                     │
└─────────────────────┘            └─────────────────────┘
  分析现在 → 生成报告                 接收报告 → 预测未来
```

---

## 5. 关键评估：对历史公众号场景的适配度

| 能力 | BettaFish | MiroFish | 适配度 |
|------|-----------|----------|--------|
| 热点发现 | ★★★★★ | — | MindSpider爬虫可适配历史领域源 |
| 多角度分析 | ★★★★★ | — | ForumEngine辩论机制天然适合 |
| 内容原料生成 | ★★★★ | — | ReportEngine模板可定制 |
| 趋势预测 | — | ★★★★★ | "历史如果"选题的核心引擎 |
| 情感洞察 | ★★★★★ | — | 评论区情感分析 |
| 多模态理解 | ★★★★ | — | 历史视频/图片内容解析 |
