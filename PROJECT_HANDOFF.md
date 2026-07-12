# 项目名称
Novel Local AI

版本基线：**v1.0.0**。这是公开源码仓库的首个可追溯版本，代表当前本地可用原型的初始快照，不等同于商业发布完成度。

本地优先的 AI 小说写作工具。当前 slogan/定位可以概括为：**Local-first Studio for AI Novel Writing**，也就是“尽量在本机完成小说构思、生成、审稿、修订和长期记忆管理”。

## 一句话说明
本地 AI 小说写作工作台。

## 它解决什么问题
这个项目面向想用本地大模型辅助写长篇小说的人，尤其是希望“自己的文本、设定、角色资料和生成记录尽量留在本机”的用户。

它要解决的核心痛点不是“让 AI 写一小段文字”，而是：

- 写长篇时容易忘记前文设定、人物状态、时间线和伏笔。
- 单次模型上下文有限，不能把几十章、上百章全文都塞进 prompt。
- AI 生成一章后，用户需要知道它是否跑题、是否和前文冲突、是否应该修订。
- 用户希望本地模型，例如 LM Studio、llama.cpp、Ollama、KoboldCpp、text-generation-webui，能统一接入同一个写作流程。
- 用户希望可以从一个想法开始，逐步生成故事框架、角色、世界观、章节计划，再进入逐章生产。
- 用户希望自动模式可控：可以自动审稿、自动修订、自动写入正文，但遇到 blocker 或模型异常时必须暂停、可追踪、可回滚。

用更通俗的话说：它想做一个“本地小说生产工作台”，不是一次性聊天，而是围绕一本小说长期维护资料、章节、版本、检查报告和运行日志。

## 当前进度
当前阶段：**开发中，可用原型，约等于 MVP 3 Phase 3**。

它不是商业发布完成品，但已经不是纯设计稿。当前已经能在本机启动 Web UI 和 FastAPI 后端，使用 SQLite 保存数据，并通过本地模型服务跑通写作流程。

已经做完的主要部分：

- 基础项目/小说/章节/人物/世界观管理。
- 本地 Web UI。
- 模型 Provider 配置。
- 本地模型清单扫描与展示。
- 单章 Loop Run：生成草稿、连续性检查、生成不可变版本、等待/执行审批。
- 人工 approve / reject / revise。
- AI Auto Review / Auto Revise / Auto Commit。
- 多章自动章节生产线。
- ChapterVersion 版本保存与恢复。
- GenerationRun / RunStep / ModelCall 日志。
- Story Memory 最小版本。
- Reference Pack：可以引用章节、版本等内容给模型参考。
- 从已有内容/想法反向或正向提取结构化资料的 P0 能力。
- Markdown 导出。
- 基础测试套件。

正在做或做了一部分的内容：

- Story Memory 已有最小记录和 checkpoint，但还不是完整的“长篇小说状态数据库”。
- 自动修订能根据检查报告生成新版本，但质量和策略还需要持续优化。
- 多章生产线能跑，但长时间稳定性、复杂失败恢复和 UI 细节仍需要加强。
- 本地模型列表已经能扫描和同步，但不同模型的真实质量、速度、默认参数仍需要逐个样稿验证。
- 前端已经可用，但还没有系统级 E2E 自动化测试。

还没开始或尚未完整实现：

- 完整 RAG / GraphRAG。
- 完整人物关系图、时间线编辑器、伏笔管理工作台。
- 版本 diff UI。
- 后端持久化的模型角色分配，例如 Writer / Checker / Summary 分别固定使用不同 provider。
- SSE/WebSocket 实时推送，目前主要靠轮询。
- 云同步、多用户、权限系统。
- Tauri 桌面端正式打包。
- EPUB/PDF 专业排版。
- macOS Keychain 保存 API Key。

## 功能清单
- 已完成功能（列出主要功能点）

  - 项目管理：创建、查看、编辑、删除项目。
  - 小说管理：创建小说，维护标题、简介、故事总纲、风格要求。
  - 章节管理：章节树、章节目标、章节大纲、正文编辑、保存。
  - 角色卡：角色列表、角色描述、当前状态、人物弧光和关系备注。
  - 世界观规则：规则、地点、组织、物品等设定条目。
  - Prompt 模板管理：可查看和编辑核心 prompt。
  - 模型配置：支持 LM Studio、llama.cpp、Ollama、KoboldCpp、text-generation-webui、OpenAI-compatible API。
  - 本地模型中心：扫描本地模型，显示参数量、量化、本体大小、估算运行内存、推荐上下文、推荐用途。
  - 统一模型调用接口：所有生成都经过 ModelProvider adapter。
  - Context Builder：生成前动态拼装故事总纲、章节目标、角色、世界观、最近摘要、伏笔等上下文。
  - 单章生成：生成草稿，保存为不可变 ChapterVersion，不直接覆盖正式正文。
  - 连续性检查：输出问题、严重程度、证据和建议。
  - 人工审批：approve 后才写入 Chapter.content，reject 不写入，revise 生成新版本。
  - AI 自动审稿与自动修订：可从检查报告生成 RevisionPlan，再生成修订版本。
  - AI Auto Commit：达到阈值后自动写入正式正文，写入前保留版本和日志。
  - 多章生产线：可设置生成章数为正整数，逐章生成、检查、修订、写入或暂停。
  - Provider 自动恢复：本地模型服务未启动时，尝试启动或加载；失败时尝试其他在线本地 provider。
  - Story Memory 最小实现：章节提交后保存摘要、状态记忆和 checkpoint。
  - Reference Pack：支持将章节/版本等引用打包成精简上下文，而不是把所有全文塞给模型。
  - 导出 Markdown：按章节顺序导出小说正文。
  - 日志追踪：RunStep、ModelCall、prompt、response、raw output、错误码、耗时等。

- 部分完成功能（写清楚做到了什么程度、还差什么）

  - 自动章节生产线：已经能跑 1 / 多章生成、修订、写入和暂停；还需要更好的 UI 进度展示、失败原因解释、恢复策略和长时间压力测试。
  - Story Memory：已有最小记录；还缺完整的 CharacterState、RelationshipState、TimelineEvent、Foreshadowing、PlotThread、ItemState、LocationState 的结构化更新和落库策略。
  - 反向故事工程：已有从文本/章节提取结构化资料的 P0；还缺更稳定的冲突处理、批量接受/拒绝体验和质量基准。
  - 模型管理：已能扫描 LM Studio、oMLX、Ollama、llama.cpp、本地 Hugging Face/MLX 缓存；但模型真实质量、最佳采样参数、内存占用仍需固定样稿验证。
  - 前端信息架构：项目、章节、运行记录、本地模型、提示词等页面已可用；但交互仍偏原型，缺少更清晰的新手引导和完整 E2E 测试。
  - 自动修订：能根据 Continuity Report 生成修订版本；还需改进“问题转修订任务”的质量、复检阈值和剩余问题展示。

- 未完成功能（按优先级排序）

  1. 完整前端 E2E 测试：覆盖创建项目、选模型、启动 run、查看版本、approve/reject/revise、Auto Commit、多章暂停恢复。
  2. 独立 Version Diff UI：让用户清楚看到 v1/v2/v3 改了什么。
  3. 后端持久化模型角色：Writer、Checker、Summary、Extractor 可分别配置模型，而不是只靠浏览器 localStorage。
  4. 更完整 Story Memory 页面：展示章节摘要、角色状态、时间线、伏笔、世界规则、checkpoint 来源。
  5. SSE/WebSocket 或更稳的实时状态更新：替代当前轮询。
  6. 完整 RAG / GraphRAG：先做轻量向量检索，再考虑图谱。
  7. macOS Keychain：保存 API Key，避免明文存在 SQLite。
  8. Tauri 桌面包：把本地 Web UI 封装成桌面应用。
  9. EPUB/PDF 导出与排版。

## 技术栈与架构
据当前代码和文档推断，技术栈如下。

前端：

- React 18.3.1
- TypeScript 6.0.3
- Vite 8.0.16
- Tailwind CSS 3.4.10
- 无 React Router；使用 `window.location.hash` 自己实现简单路由。
- 无 Redux/Zustand 等状态管理库。
- 无大型组件库，主要是自定义组件和 Tailwind 样式。

后端：

- Python 3.9+
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- SQLite
- httpx
- pytest

模型接入：

- OpenAI-compatible API 作为统一抽象。
- 已支持或适配：
  - LM Studio
  - llama.cpp / llama-server
  - Ollama
  - KoboldCpp
  - text-generation-webui
  - 其他 OpenAI-compatible 服务
  - 云端 OpenAI-compatible API 可选，但项目目标是本地优先。

部署方式：

- 开发运行：后端 `uvicorn`，前端 `vite dev`。
- 当前用户机器上还有一份部署副本在：
  `$HOME/Library/Application Support/NovelLocalAI`
- 当前 LaunchAgent 启动项据历史文档和本机状态包括：
  - `~/Library/LaunchAgents/com.novel-local-ai.api.plist`
  - `~/Library/LaunchAgents/com.novel-local-ai.web.plist`
  - `~/Library/LaunchAgents/com.novel-local-ai.llama.plist`
- 当前源码已迁移到：
  `$HOME/Documents/vibe-coding/novel-local-ai-open-source`

整体架构：

- 前端是单页应用，负责项目、章节、运行记录、模型配置和 prompt 管理。
- 后端 FastAPI 提供 REST API。
- SQLite 保存所有本地数据，包括项目、章节、版本、运行日志、模型配置等。
- 写作任务通过后端本地队列/后台线程执行，不使用 Celery、Redis、Temporal。
- 所有模型调用经过 provider adapter，统一记录 ModelCall。
- ChapterVersion 是不可变版本；正式正文 `Chapter.content` 只在 approve 或 auto commit 后更新。

## 项目结构速览
当前迁移后的项目根目录：

```text
$HOME/Documents/vibe-coding/novel-local-ai-open-source
```

简化目录说明：

```text
novel-local-ai/
  README.md
  PROJECT_HANDOFF.md              # 本交接文档
  CLAUDE.md                       # 给 Claude/AI agent 的额外协作说明
  docs/                           # 大量设计、审计、报告、路线图
  data/
    novel_local_ai.db             # 本地 SQLite 数据库副本
    sample_project/               # 示例数据
  apps/
    web/
      package.json                # 前端依赖和脚本
      src/
        App.tsx                   # 前端主入口，hash 路由
        components/               # 页面壳、Dashboard、模型设置、创作中心等
        features/
          chapters/               # 章节工作区
          runs/                   # Loop Run 列表和详情
          models/                 # 模型角色分配、诊断卡等
        services/
          api.ts                  # 前端 API 封装
        types.ts                  # 前端 TypeScript 类型
      dist/                       # build 产物
  services/
    api/
      pyproject.toml              # 后端依赖
      alembic.ini                 # Alembic 配置
      app/
        main.py                   # FastAPI 入口和后台队列生命周期
        db.py                     # SQLite/SQLAlchemy 连接
        models/
          entities.py             # 基础实体：Project、Novel、Chapter、ModelProvider 等
          loop_entities.py        # Loop Run、RunStep、ModelCall、ChapterVersion 等
          auto_entities.py        # MVP3 自动生产线、Reference、Story Memory 等
        schemas/                  # Pydantic schema
        routers/                  # API 路由
        providers/
          adapters.py             # 模型 provider adapter
        agents/
          base.py                 # TextAgent / StructuredAgent
          writer.py               # DraftWriter / RevisionWriter
          checkers.py             # Continuity Checker 等
        services/
          context_builder.py      # 上下文组装
          auto_pipeline.py        # 单章自动审稿/修订/写入
          multi_chapter.py        # 多章生产线
          local_model_inventory.py# 本地模型扫描与同步
          provider_recovery.py    # 本地模型服务恢复/回退
          story_memory.py         # Story Memory 最小实现
          reference_service.py    # Reference Pack
          json_guard.py           # JSON 解析和 Pydantic 校验
          draft_text_guard.py     # 草稿文本校验
          run_logger.py           # RunStep / ModelCall 日志
        prompts/
          novel_loop/             # 单章 Loop prompt
          story_engineering/      # 故事工程/仿写/拆解 prompt
      migrations/
        versions/                 # Alembic migration
      tests/                      # pytest 测试
  scripts/
    dev.sh                        # 本地开发启动脚本
    checker_bench/                # 检查器基准脚本
    writer_bench/                 # 写作器基准脚本
  _ai_fix_backup/                 # 历史修复备份
```

重点文档位置：

- `docs/AI_CURRENT_STATUS.md`：当前状态总览，但日期是 2026-06-13，后续有改动需复核。
- `docs/AI_HANDOFF_INDEX.md`：面向 AI 接手的索引文档。
- `docs/AI_RUN_AND_TEST_GUIDE.md`：运行和测试指南。
- `docs/AI_NEXT_TASKS.md`：下一步任务。
- `docs/26_mvp3_auto_chapter_pipeline_report.md`：MVP3 自动章节生产线报告。
- `docs/27_mvp3_phase3_multi_chapter_report.md`：多章生产线报告。
- `docs/28_multi_chapter_fallback_patch_report.md`：多章兜底补丁报告。
- `docs/29_auto_revision_loop_fix_report.md`：自动修订循环修复报告。
- `docs/30_story_engineering_report.md`：故事工程报告。
- `docs/31_reverse_story_engineering_report.md`：反向故事工程报告。

## 如何运行 / 查看
当前机器上已经有一份运行中的部署副本：

```text
$HOME/Library/Application Support/NovelLocalAI
```

访问地址：

```text
http://127.0.0.1:5173/
```

后端健康检查：

```text
http://127.0.0.1:8000/api/health
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

如果要从迁移后的源码目录本地开发运行：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/services/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开一个终端启动前端：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/apps/web
npm install
npm run dev
```

然后打开：

```text
http://127.0.0.1:5173/
```

如果要明确使用迁移目录中的 SQLite 数据库：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/services/api
NOVEL_AI_DB_URL=sqlite:///$HOME/Documents/vibe-coding/novel-local-ai-open-source/data/novel_local_ai.db \
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

测试命令：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/services/api
source .venv/bin/activate
pytest
```

前端构建：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/apps/web
npm run build
```

当前项目没有必须的云账号或 token。可选云模型 API Key 会作为 ModelProvider 的 `api_key` 存入本地 SQLite。注意：目前还没有接入 macOS Keychain。

本地模型服务常见地址：

```text
LM Studio:              http://127.0.0.1:1234/v1
llama.cpp llama-server: http://127.0.0.1:18081/v1 或用户自定义端口
Ollama:                 http://127.0.0.1:11434
KoboldCpp:              http://127.0.0.1:5001
text-generation-webui:  http://127.0.0.1:5000/v1
```

## 已知问题与卡点
- 当前源码目录已经迁移到 `$HOME/Documents/vibe-coding/novel-local-ai-open-source`，但正在运行的 LaunchAgent 服务仍使用部署副本 `$HOME/Library/Application Support/NovelLocalAI`。如果修改源码后想让网页使用新代码，需要重新部署或改 LaunchAgent 指向新目录。
- 数据库有多个副本：迁移目录中的 `data/novel_local_ai.db` 是从部署数据库复制来的；部署服务实际使用的数据库仍在 `~/Library/Application Support/NovelLocalAI/data/novel_local_ai.db`。
- 后端仍有 `create_tables()`，这能创建缺失表，但不能替代 Alembic 的安全迁移。不要把它当作完整 migration。
- 后台队列是进程内线程，不是持久化任务队列。进程崩溃时，正在跑的模型调用恢复能力有限。
- SQLite 适合本地单用户；不要用多个 uvicorn worker 同时写同一个 SQLite 数据库。
- ModelCall / raw output 日志可能会快速膨胀，尚未做日志清理、脱敏和保留策略。
- API Key 目前保存在 SQLite，不适合共享数据库。
- 前端没有 Playwright/Cypress E2E 测试，主要靠 TypeScript build 和后端 pytest。
- Run Detail 主要靠轮询，没有 SSE/WebSocket。
- 模型质量不稳定，尤其是用户本机有很多微调/非官方模型。模型名不能代表实际写作质量，必须用固定章节样稿测试。
- 自动写入模式虽然有安全阈值，但仍可能把质量不高的内容写入正式正文；好在有 ChapterVersion 可回滚。
- Story Memory 还很初级，不能假设它已经解决长篇一致性的全部问题。
- 文档很多，历史文档里的“未实现”可能已经过期。优先看 `AI_CURRENT_STATUS.md` 和最新编号报告，再核对代码。

## 下一步建议
1. **先统一运行目录和源码目录。** 决定是继续使用 `$HOME/Library/Application Support/NovelLocalAI` 作为部署副本，还是把 LaunchAgent 改到 `$HOME/Documents/vibe-coding/novel-local-ai-open-source`。做之前先备份数据库。
2. **补前端 E2E 测试。** 最小覆盖：打开项目、进入章节、选择模型、启动单章 run、查看版本、approve/reject/revise、Auto Commit、多章暂停/恢复。
3. **做 Version Diff UI。** 用户需要看到 AI 修订前后到底改了什么，这是自动修订可信度的关键。
4. **把模型角色分配持久化到后端。** Writer、Checker、Summary、Extractor 应该可以选择不同 provider，并保存到项目或全局设置。
5. **完善 Story Memory 页面。** 先展示已有章节摘要、角色状态、时间线、伏笔、世界规则和 checkpoint，并显示来源章节和更新时间。

## 外部依赖与第三方服务
必需依赖：

- macOS
- Python 3.9+
- Node.js 18+
- SQLite
- 本地浏览器

后端 Python 依赖：

- FastAPI
- Uvicorn
- SQLAlchemy
- Alembic
- Pydantic
- httpx
- pytest

前端依赖：

- React
- React DOM
- TypeScript
- Vite
- Tailwind CSS
- PostCSS
- Autoprefixer

可选本地模型服务：

- LM Studio：当前用户机器已使用过，端口通常是 `1234`。
- llama.cpp / llama-server：当前历史配置中有 `qwen2.5-coder-0.5b-q4km` 用于健康检查。
- Ollama：如果本机安装并有模型，可用 `11434`。
- KoboldCpp：支持但具体端点取决于用户启动方式。
- text-generation-webui：需要启用 OpenAI API 扩展。
- oMLX：项目中已有一定扫描/配置支持，实际运行状态需确认。

可选云服务：

- 任意 OpenAI-compatible 云 API。项目不强依赖云服务，也不应假设用户一定有 OpenAI API Key。

第三方项目源码：

- 项目不应直接复制调研报告里的第三方源码。
- AGPL 项目只能作为架构参考，不能未经确认复制代码。
- MIT / Apache 2.0 代码如复用必须保留 license 和 attribution。

## 重要备注
- 用户非常在意“本地优先”。基础写作流程应尽量不依赖云服务。
- 用户的硬件是 macOS、64GB 统一内存，优先支持本地模型、llama.cpp、GGUF、LM Studio、Ollama、KoboldCpp、text-generation-webui 和 OpenAI-compatible API。
- 用户不希望一上来做庞大复杂系统。每次推进都应该先做可验证的最小版本，再扩展。
- 用户明确要求：不要破坏旧 `/api/chapters/{id}/generate` 行为；不要删除旧 WritingTask、GenerationRun、chapter_pipeline.py。
- 新 Loop 能力最初被要求走独立路由，例如 `/api/projects/{project_id}/chapters/{chapter_id}/run`；后来又增加了 `/auto-run` 和 multi-chapter routes。改动时不要混淆 legacy generate 和 Loop/Auto pipeline。
- ChapterVersion 是核心安全机制：AI 草稿、修订稿都必须保存为不可变版本。不能直接覆盖 `Chapter.content`。
- `Chapter.content` 只有在人工 approve 或 Auto Commit 满足阈值后才能更新。即使是 Full Autonomous，也不能删除项目、删除章节、删除历史版本、修改模型配置或绕过日志。
- 连续性报告不只是展示问题；在 AI 自动迭代模式下，报告里的 issue 应该转成修订任务，让 RevisionWriter 定向修改，再复检。
- 如果本地模型服务没启动，要有托底机制：尝试启动服务、加载模型、或回退到其他在线 provider；失败时必须把错误讲清楚，不能静默成功。
- 用户希望模型选择框里显示本机已有模型的详细信息，包括参数量、量化、本体大小、估算运行内存、推荐上下文和默认参数。
- 用户希望生成章数是可填写的大于 0 的整数，而不是固定选项。
- 用户希望默认策略更偏 AI 自动审批/自动修订，而不是每次都等待人工审批；但自动模式仍要有暂停条件、日志、回滚和安全阈值。
- 当前本机历史默认主力模型是 LM Studio 的 `qwen3.6-27b-crack`，曾被加载到 `32768` context，默认输出上限调到约 `8192 tokens`。但接手者不要假设这台机器当前一定仍加载它，应调用 LM Studio 或 API 重新确认。
- 如果输出因为 `finish_reason=length` 被截断，系统应记录 `OUTPUT_TRUNCATED` 并自动尝试重写更紧凑但完整的正文，不能把半章当成功。
- 命名上有一些历史包袱：`Loop Run`、`Auto Run`、`MultiChapterRun`、`WritingTask`、`GenerationRun` 并存。不要贸然删旧结构；先确认哪个页面和测试仍依赖它。
- 这个项目是原型期快速演进出来的，文档和代码都很多。接手时建议先跑测试，再改小步，不要一次性重构全系统。
