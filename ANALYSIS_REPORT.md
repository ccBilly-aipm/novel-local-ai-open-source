# Novel Local AI 项目分析报告

> 本报告基于 `PROJECT_HANDOFF.md`、`docs/AI_CURRENT_STATUS.md`、`docs/AI_ARCHITECTURE_MAP.md`、`docs/AI_NEXT_TASKS.md`、`docs/10_reference_product_patterns.md` 等文档，以及 `services/api/app/` 源码的结构性阅读，于 2026-07-07 完成。

---

## 一、项目定位一句话

**Local-first Studio for AI Novel Writing**：在 macOS 上，以本地大模型为核心引擎，通过受控的生成-审稿-修订-审批 Loop，逐章生产长篇小说，同时维护不可变版本历史和可追踪运行日志。

---

## 二、核心技术判断

### 2.1 架构总览

```
React 18 (SPA, hash routing, Tailwind)
        ↓
FastAPI + Pydantic v2 + SQLAlchemy 2 + SQLite
        ↓
Model Adapter Layer (LM Studio / llama.cpp / Ollama / KoboldCpp / OpenAI-compatible)
        ↓
本地模型 HTTP 服务（llama-server / LM Studio / Ollama）
```

这是一个**完全本地运行、无云依赖**的单用户桌面类应用。数据在 SQLite，模型在本地，UI 在浏览器。

### 2.2 当前核心能力（已稳定）

| 能力 | 技术实现 |
|---|---|
| 单章生成 Loop | `NovelLoopRunner` 状态机，含 Draft → Check → (Revise) → Approve |
| 自动审稿/修订/写入 | `auto_pipeline.py`，阈值策略 + blocker 暂停 |
| 多章生产线 | `MultiChapterRunner`，串行子 Run + checkpoint |
| 不可变版本 | `ChapterVersion`，append-only ORM hook |
| Reference Pack | 精选上下文打包，避免 token 爆炸 |
| Provider 兜底恢复 | `provider_recovery.py`，启动/加载/回退 |
| Story Memory P0 | 抽取式摘要 + staging 状态候选 |
| 故事工程 | Forward（想法→框架）+ 拆解参考小说 + 仿写 |
| 版本回滚 | 备份 + 恢复 + 审计 |
| 完整日志 | RunStep + ModelCall 全链路追踪 |

### 2.3 技术债务与薄弱环节

| 类别 | 具体问题 |
|---|---|
| **进程内队列** | 三个 daemon 线程队列（Legacy / Loop / MultiChapter），进程崩溃则任务丢失，无持久化 |
| **轮询替代 SSE** | Run 详情页每秒轮询，无 WebSocket/SSE，`/api/health` 也被轮询 |
| **Story Memory 初级** | 仅 extractive summary，缺少 CharacterState / RelationshipState / TimelineEvent / Foreshadowing 的结构化推进 |
| **日志隐私风险** | `ModelCall.prompt` / `raw_payload` 记录完整小说正文，无脱敏和保留策略 |
| **前端无状态管理** | 无 Zustand/Redux，hash routing 全靠 `App.tsx` 解析，复杂状态靠 prop drilling |
| **多进程写 SQLite 风险** | SQLite 单写，不可用多 uvicorn worker |
| **版本 Diff UI 缺失** | 修订前后只能分别预览，不能直接 diff |
| **模型质量黑盒** | 不同 GGUF 模型写作质量差异极大，无固定样稿验证体系 |
| **E2E 测试缺失** | 前端只有 TypeScript build，无 Playwright/Cypress |

---

## 三、优化建议与提升方向

### 3.1 优先级 P0（影响核心体验）

#### ① 版本 Diff UI（当前最大 UX 缺口）

**现状**：修订只能分别预览 v1/v2/v3，用户无法快速看出改了哪里。

**建议**：
- 实现 `apps/web/src/features/runs/VersionDiff.tsx`，选择两个版本后展示 unified diff（行级别或语义块级别）
- 后端提供只读 diff API（`GET /api/runs/{id}/versions/{v1}/{v2}/diff`），纯计算 diff，不修改数据
- diff 展示建议用 `diff-match-patch` 或类似库，支持中文章节文本
- 参考 Coding Agent 的 "result can be diffed" 模式（见 `docs/10_reference_product_patterns.md` 第 5 节）

**涉及文件**：
- 新增 `apps/web/src/features/runs/VersionDiff.tsx`
- 可选新增 `services/api/app/routers/loop_runs.py` diff endpoint

---

#### ② SSE / WebSocket 实时状态推送（替代轮询）

**现状**：Run 详情页每秒轮询，增加服务器负载和延迟。

**建议**：
- 引入 FastAPI `Broadcast`（基于 `fastapi-utils`）或 `sse-starlette`，在 Run 状态变更时推送事件
- 前端 EventSource 订阅，减少 99% 的无效请求
- 保底仍是轮询（SSE 断线重连兜底）
- 初期只需推送 `run.state` / `step.updated_at` 变更，不需要推送完整数据

**注意**：不要引入 Redis / Celery，保持 SQLite 单进程。可以用进程内 `asyncio.Queue` 广播。

---

#### ③ Story Memory 完整化（CharacterState / Timeline / Foreshadowing）

**现状**：`stage_state_changes()` 已有 staging 框架，但完整的状态推进尚未完成。

**建议**：
- 实现 `StateChangeExtractorAgent` 的完整版，从已提交章节抽取角色状态变化候选
- 每个候选带来源证据（source_version_id）和置信度
- 用户接受后写入 `CanonState`，不自动覆盖
- 参照 `docs/AI_NEXT_TASKS.md` P3 的 Persistent structured Story Memory 任务

---

### 3.2 优先级 P1（提升可用性）

#### ④ 模型角色持久化到后端

**现状**：Writer / Checker / Summary / Extractor 的模型分配存在 `ModelRoleAssignments.tsx`（浏览器 localStorage），但 Loop run 仍只用一个 provider。

**建议**：
- 将角色-模型映射持久化到 `ModelRoleAssignment` 表（已在 `auto_entities.py` 有 `writer_provider_id` / `checker_provider_id` 字段）
- UI 提供全局默认 + 项目覆盖 + 本次 run 覆盖三级（参考 AnythingLLM 模式，见 `docs/10_reference_product_patterns.md` 3.3 节）
- Writer 用较大上下文模型，Checker 用较小但精准的模型

---

#### ⑤ 模型质量验证体系

**现状**：不同 GGUF 模型写作质量差异极大，模型名不能代表质量。

**建议**：
- 建立固定样稿章节（3~5 个场景），每次更换模型后用固定 prompt 测试输出
- 记录每个模型的评分：连续性错误率、blocker 比例、修订轮次、生成速度
- 在"模型设置"页面展示测试结果（类似 LM Studio 的模型卡片）
- 这是一个持续性工作，不需要一次性完成所有模型验证

---

#### ⑥ 日志隐私与清理策略

**现状**：`ModelCall.prompt` 和 `raw_payload` 记录完整小说正文，无保留策略。

**建议**：
- 实现日志脱敏：检测并标记含小说正文的 prompt/response 字段
- 用户可选保留期限（如 30 天 / 90 天 / 永久）
- API 提供"导出日志"和"清理日志"功能
- 参考 `docs/AI_NEXT_TASKS.md` P1 的 Log sensitive-information cleanup strategy 任务

---

### 3.3 优先级 P2（系统稳定性）

#### ⑦ 进程外持久化队列（防崩溃丢失）

**现状**：三个 daemon 线程队列在进程崩溃时任务丢失。

**建议**：
- 初期方案：队列状态持久化到 SQLite（pending / running 状态），进程重启后扫描并恢复
- 中期方案：引入 `dramatiq`（轻量 Python 队列，SQLite broker）或 `huey`（同样 SQLite 友好）
- 避免引入 Celery + Redis 等重基础设施
- 注意：不需要多 worker 写 SQLite，只做任务持久化 + 单 worker 执行

---

#### ⑧ 前端 Playwright E2E 测试

**现状**：前端只有 `npm run build`，无自动化 E2E。

**建议**：
- Playwright 覆盖核心路径：创建项目 → 进入章节 → 选择模型 → 启动 run → 查看版本 → approve/reject → 多章暂停/恢复
- 用 `localhost:5173` 配合 mock provider，测试不依赖真实模型
- 可以先做 smoke test（5~8 个核心操作），再逐步扩展

---

#### ⑨ macOS Keychain 存储 API Key

**现状**：API Key 保存在 SQLite 明文，不适合共享环境。

**建议**：
- macOS 上用 `security` 命令行工具操作 Keychain，或用 `keyring` Python 库
- 云端 provider（OpenAI 兼容）的 API Key 优先存入 Keychain
- 数据库只存 Keychain 引用 ID，不存明文

---

### 3.4 优先级 P3（长期演进）

#### ⑩ Tauri 桌面打包

**现状**：当前是浏览器访问 `localhost:5173`，不是独立桌面应用。

**建议**：
- 在验证 Web UI 稳定后，再引入 Tauri 打包
- 参考 `docs/research-review.md` 的决策：先验证浏览器 UI，避免同时调试 Rust 和桌面打包
- Tauri 可以直接访问本地文件系统（模型路径）和系统托盘

---

#### ⑪ RAG / GraphRAG（延迟引入）

**现状**：未实现，向量检索不是当前瓶颈。

**建议**：
- MVP 阶段用 Reference Pack + 近期摘要 + 结构化 Story Memory 已足够
- 当小说超过 50 章、上下文溢出频繁时，再引入轻量向量检索
- 可选 Chroma（SQLite-like 部署）或 LanceDB（本地友好）
- GraphRAG 推迟到有明确的图谱查询需求

---

#### ⑫ EPUB / PDF 导出与排版

**现状**：只有 Markdown 导出。

**建议**：
- Markdown 导出后，用户可用 Pandoc 转 EPUB/PDF
- 如果要原生支持，考虑 `weasyprint`（HTML → PDF）或 `ebooklib`（EPUB 生成）
- 排版复杂度高，建议作为 P3 任务

---

## 四、类似开源项目参考

### 4.1 直接可参考架构思想

| 项目 | License | 值得借鉴的核心设计 |
|---|---|---|
| **SillyTavern** | AGPL | 多后端 agent 对话框架，但 license 需注意，仅作架构参考 |
| **TheStoryNexus** | 未知 | 三栏小说 IDE 交互思路（左侧树 / 中间编辑 / 右侧元数据） |
| **Storyteller** | AGPL | 章节/场景分割 + 分层摘要 + 近期摘要作为上下文 |
| **InkOS** | AGPL | 生成与审稿分离、人工确认状态变更 |
| **StoryCraftr** | MIT | 纯本地，无云依赖，prompt 管理 |
| **Autonovel** | MIT | 长篇 AI 写作的工程化思考 |
| **novelibre** | GPL-3 | 本地小说管理 + AI 辅助，有完整的项目/章节/角色结构 |

### 4.2 局部可复用的模块（需验证 License）

| 模块 | 可能来源 | 复用方式 |
|---|---|---|
| diff 展示组件 | `diff-match-patch` (Apache 2.0) | npm 安装，直接使用 |
| Markdown → EPUB | `pandoc` (GPL) / `ebooklib` (BSD) | CLI 调用或 Python 包 |
| 轻量向量检索 | `chromadb` / `lancedb` (both Apache 2.0) | 后期可选引入 |
| 语法高亮 / 代码块 | `@uiw/react-md-editor` (MIT) | 前端 Markdown 编辑器 |

### 4.3 不建议参考的项目特征

| 项目/技术 | 原因 |
|---|---|
| **LangGraph / AutoGen** | 单章串行 Loop 不需要图编排，引入过重 |
| **Neo4j / NetworkX** | 无足够图谱查询需求，MVP 不需要知识图谱 |
| **Chroma + Redis + Celery** | 引入过多基础设施，与本地单用户定位冲突 |
| **自动全文导入分析** | 准确率、版权、切章和 token 成本均未验证 |

### 4.4 与同类产品的差异化定位

Novel Local AI 的核心竞争力在于：

1. **完全本地**：不依赖任何云服务，模型在本地运行，数据在本地存储
2. **不可变版本 + 人工审批**：AI 输出永远是"候选版本"，不污染正文
3. **受控自动模式**：Auto Commit 有阈值和 blocker 暂停，不是无脑自动
4. **可回滚**：任何自动写入都有备份和回滚机制

这些差异化点应该在 README 和文档中更突出，而不是只强调"AI 写小说"这个通用功能。

---

## 五、具体实施路线图建议

### Phase 1（1~2 周）：填最明显的 UX 缺口
1. 版本 Diff UI（`VersionDiff.tsx`）
2. 固定样稿模型验证（建立基准测试集）

### Phase 2（2~4 周）：提升稳定性
1. SSE 实时推送（减少轮询）
2. 队列持久化（进程崩溃恢复）
3. 日志清理 UI

### Phase 3（长期）：扩展能力
1. Story Memory 完整化（CharacterState / Timeline）
2. 前端 E2E 测试（Playwright）
3. 模型角色后端持久化
4. Tauri 桌面打包
5. RAG / GraphRAG（仅在 50+ 章场景下）

---

## 六、附录

### A. 关键文档索引

| 文档 | 用途 |
|---|---|
| `CLAUDE.md` | 给 AI agent 的协作说明，核心铁律 |
| `docs/AI_HANDOFF_INDEX.md` | 面向 AI 接手的文档索引 |
| `docs/AI_CURRENT_STATUS.md` | 当前已实现/未实现能力清单（最后验证 2026-06-13） |
| `docs/AI_ARCHITECTURE_MAP.md` | 系统架构图和模块依赖表 |
| `docs/AI_NEXT_TASKS.md` | 详细任务清单，包含已完成标记 |
| `docs/10_reference_product_patterns.md` | 同类产品设计模式参考 |
| `docs/research-review.md` | 调研报告可用性审查，避免盲目复用 |

### B. 核心铁律（来自 `CLAUDE.md`，任何改动必须遵守）

1. 不得破坏旧接口 `POST /api/chapters/{chapter_id}/generate`
2. 手动模式下，审批通过之前不得覆盖 `Chapter.content`
3. 不得静默吞掉 JSON 解析错误或 Pydantic 校验错误
4. 不得把模型输出直接写入 Canon
5. 不得删除或修改已有的 ChapterVersion 行
6. 不得绕过 RunStep 与 ModelCall 日志记录
7. 优先采用增量式（additive）改动
8. 始终保持全部测试通过
9. 进行迁移工作前，先备份并检查 SQLite
10. 不要把仓库数据库与已部署的应用数据库混为一谈

### C. 测试通过基准

```bash
# 后端
cd services/api && .venv/bin/pytest -q
# 当前: 59 passed

# 前端
cd apps/web && npm run build
# 当前: build passed
```

---

*本报告于 2026-07-07 基于 PROJECT_HANDOFF.md 及 docs/ 目录下 2026-06-13 前的文档完成。建议在实施优化前，先核查 `docs/AI_CURRENT_STATUS.md` 是否有更新。*
