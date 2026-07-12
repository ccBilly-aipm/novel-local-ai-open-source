# Novel Local AI Agent Guide

本文件是 AI Agent、自动化编码工具和新接手工程师的第一阅读入口。仓库基线版本为 `v1.0.0`。

## 1. 项目目标与当前阶段

Novel Local AI 是面向 macOS 的本地优先小说写作工作台。它把“想法、故事资料、章节计划、正文生成、连续性检查、修订、审批、长期记忆”组织成可追踪流程，并优先调用本机模型服务。

当前是可运行的 MVP 3 原型，不是商业发布完成品。已经实现单章 Loop、人工审批、AI 自动修订/提交、多章生产线、Reference Pack、最小 Story Memory、正向故事工程和反向拆解 P0。详细用户视角见 `docs/USER_GUIDE.md`，项目全貌见 `PROJECT_HANDOFF.md`。

## 2. 开始工作前的阅读顺序

1. `AGENTS.md`：协作规则与不可破坏约束。
2. `PROJECT_HANDOFF.md`：产品、进度、目录和已知问题。
3. `docs/AI_CURRENT_STATUS.md`：代码能力索引。该文件可能有日期滞后，结论必须对照代码和测试复核。
4. `docs/AI_ARCHITECTURE_MAP.md`：系统关系图。
5. `docs/AI_CODE_TOUCH_MAP.md`：功能到文件的映射。
6. `docs/AI_RUN_AND_TEST_GUIDE.md`：运行、迁移和测试方式。
7. 与任务直接相关的最新报告，优先阅读 `docs/26` 到 `docs/31`。

早期 `docs/01` 到 `docs/08` 是历史设计和测试记录，不能直接当作当前事实。

## 3. 不可破坏的工程约束

1. 保留旧接口 `POST /api/chapters/{chapter_id}/generate` 的行为。
2. 保留旧 `WritingTask`、`GenerationRun` 和 `services/api/app/pipelines/chapter_pipeline.py`。
3. `ChapterVersion` 是不可变历史。不得原地改写或删除已有版本。
4. 手动审批模式下，只有 approve 才能更新 `Chapter.content`。
5. 自动提交遇到 blocker、校验失败、模型异常或缺少必要上下文时必须暂停，不能写入正文。
6. 所有工作流步骤写 `RunStep`，所有模型调用写 `ModelCall`；失败也必须有记录。
7. 所有结构化模型输出都必须通过 Pydantic/`JsonGuard`，不得用宽松字典绕过校验。
8. 模型输出不得直接污染 Canon。结构提取先进入 staging，显式接受后再落入正式资料。
9. 不把整本小说全文、全部 raw output 或全部历史检查报告塞进上下文。
10. 不允许自动模式删除项目、章节、版本，修改模型配置，或绕过审计日志。
11. 不用 `create_all()` 代替 Alembic 迁移。模型字段或索引变化必须新增 migration 和测试。
12. 不对用户数据库运行破坏性 Git/文件操作；数据库实验使用独立临时库。

## 4. 两份目录必须区分

开发仓库：

```text
$HOME/Documents/vibe-coding/novel-local-ai-open-source
```

本机 LaunchAgent 运行的部署副本通常是：

```text
$HOME/Library/Application Support/NovelLocalAI
```

浏览器看到的 `127.0.0.1:5173` 可能来自部署副本，而不是当前 Git 工作树。改代码前先检查 LaunchAgent 的 `WorkingDirectory` 和端口进程。除非用户明确要求部署，不要直接覆盖部署副本。同步脚本为 `scripts/sync_to_deployed.sh`，执行前必须确认备份和目标路径。

## 5. 架构速览

```text
apps/web/                  React 18 + TypeScript + Vite + Tailwind
  src/App.tsx              hash 路由、全局数据加载、页面入口
  src/components/          项目、创作中心、人物、世界观、模型和 Prompt 页面
  src/features/chapters/   章节工作区与上下文检查
  src/features/runs/       Loop/MultiChapter 运行列表、详情、审批和报告
  src/services/api.ts      前端 REST API 封装
  src/types.ts             前端共享类型

services/api/              FastAPI + SQLAlchemy + Alembic + SQLite
  app/main.py              API 入口与本地队列生命周期
  app/models/              基础实体、Loop 实体、自动生产线实体
  app/schemas/             Pydantic 输入输出契约
  app/routers/             REST 路由
  app/providers/           统一模型 Provider adapter
  app/agents/              Writer、RevisionWriter、Checker 等 Agent
  app/workflow/            单章 Loop 状态机
  app/services/            上下文、自动修订、多章、记忆、引用、恢复和日志
  app/prompts/             文件化 Prompt 模板
  migrations/versions/     Alembic migration 链
  tests/                   后端回归测试
```

前端没有 React Router、Redux/Zustand 或大型组件库。路由由 `apps/web/src/App.tsx::parseRoute()` 解析 `window.location.hash`。新增页面时先延续现有模式，除非任务明确包含路由重构。

## 6. 核心数据与流程

基础内容：`Project -> Novel -> Chapter`，角色和世界规则归属 Novel。

单章 Loop：

```text
LOAD_PROJECT -> ASSEMBLE_CONTEXT -> WRITE_DRAFT -> CHECK_CONTINUITY
-> WAIT_HUMAN_APPROVAL / AUTO_REVISE / AUTO_COMMIT / PAUSED / FAILED
```

关键实现：

- `services/api/app/workflow/runner.py`：单章状态机。
- `services/api/app/services/auto_pipeline.py`：自动审稿、修订、复检和提交。
- `services/api/app/services/loop_approval.py`：人工 approve/reject/revise。
- `services/api/app/services/version_manager.py`：版本创建与备份。
- `services/api/app/services/run_logger.py`：步骤和模型调用审计。

多章生产线由 `services/api/app/services/multi_chapter.py` 串行协调。每章沿用单章策略，提交后更新摘要/Story Memory，再进入下一章；达到章节数、blocker、模型调用上限或用户停止时结束/暂停。

引用由 `reference_service.py` 生成精简 `ReferencePack`。故事工程和拆解候选先写入 staging；正式接受逻辑必须保留来源证据。

## 7. 模型接入规则

所有模型调用必须经过 `services/api/app/providers/` 的统一接口，不得在业务路由里直接写某个服务的 HTTP 调用。

当前适配 LM Studio、llama.cpp/OpenAI-compatible、Ollama、KoboldCpp 和 text-generation-webui。不要假设服务已启动、上下文无限或所有模型都能稳定输出 JSON。调用必须保留 timeout、错误码、原始输出和截断状态；正文因 token 上限截断时不能静默当成完整成功。

Writer/Checker/Summary 的前端角色选择目前主要保存在浏览器 localStorage，尚未成为完整后端持久化配置。修改角色分配前要同时检查前端选择器和后端 run 请求契约。

## 8. 数据库与迁移安全

默认开发数据库是根目录 `data/novel_local_ai.db`，但它不进入 Git。部署数据库位于部署副本的 `data/`。两者的 schema 和数据可能不同。

任何迁移前：

1. 明确目标数据库绝对路径。
2. 创建外部备份并执行 `PRAGMA integrity_check`。
3. 检查 `alembic_version` 和 `.venv/bin/alembic heads`。
4. 只在一次性数据库上测试 downgrade；用户库以备份恢复为回滚方案。
5. 不执行 `alembic stamp`，除非已确认现有 schema 与目标 revision 完全匹配。

## 9. 修改与验证流程

动手前：查看 `git status`，阅读相关测试，列出文件范围，确认是否会碰旧生成接口、Loop、迁移或部署数据。

完成后至少运行：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/services/api
.venv/bin/pytest -q

cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/apps/web
npm run build
```

如果 `.venv` 不存在，按 `docs/USER_GUIDE.md` 安装依赖。当前没有前端 E2E 脚本；涉及关键页面交互时必须在本地浏览器做最小手动回归，并在交付中说明范围。

提交前检查：

```bash
git status --short
git diff --check
git diff --cached --check
git ls-files | rg '(\.db($|-)|\.sqlite|\.env($|\.)|\.log$)'
```

不得提交真实 API Key、本地数据库、WAL/SHM、模型权重、运行日志、缓存、部署备份或用户小说正文数据。

## 10. 当前优先技术债

1. 增加 Playwright/E2E，覆盖项目创建、模型配置、Loop、审批、自动提交和失败恢复。
2. 增加 Version Diff UI 与独立 MultiChapterRun 详情。
3. 将 Writer/Checker/Summary/Extractor 模型角色持久化到后端。
4. 扩展 Story Memory 的人物关系、时间线、伏笔、物品和地点状态。
5. 引入 SSE/WebSocket 或更稳的事件机制，替代高频轮询。
6. 把 API Key 迁移到 macOS Keychain。
7. 在不破坏本地优先原则的前提下评估持久任务队列。

## 11. 版本与交付约定

- 当前初版标签：`v1.0.0`。
- 版本号记录在根目录 `VERSION`，并同步到前端 `package.json`、后端 `pyproject.toml` 和 FastAPI 元数据。
- 行为变化写入 `CHANGELOG.md`。
- 新功能优先使用 additive migration 和独立路由，保留旧行为。
- 交付说明必须列出改动文件、测试结果、数据库影响、部署影响、风险和回滚方式。
