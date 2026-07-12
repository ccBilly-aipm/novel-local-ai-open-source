# 实现报告：拆解参考小说 + 仿写（Reverse Story Engineering）2026-06-13

## 背景

创作中心原本只能「从想法正向生成」。本次新增：**上传/粘贴一部参考小说 → 自动拆解出结构化 Story Bible（全维度）→ 逐条接受落库 → 基于这套 bible 仿写一部形似神似的新作**。原文很长（整本）时自动分块 Map-Reduce，每个维度独立抽取（专门提示词）。

复用已落地的 staging（`StoryMemoryRecord`）+ accept/reject 接口（`routers/story_engineering.py`）+ 现成落库表（`Character`/`WorldRule`/`TimelineEvent`/`PlotThread`/`Foreshadowing`/`Novel`）。

## 拆解维度（10）

人物线(characters)、世界观(worldbuilding)、时间线(timeline)、情节线(plot_threads)、定位(meta)、结构节拍(structure)、伏笔回收(setup_payoff)、主题(theme)、叙事视角(pov)、文风指纹(style_fingerprint)。每维度一个 map 提示词，结构化 JSON + 原文引文 + 置信度。

## D1：核心闭环（同步、首块）

- `app/services/novel_chunker.py`：按「第N章」/Markdown 标题 → 段落 → 字符窗口分块，带重叠。
- `app/schemas/deconstruction.py`、`app/prompts/deconstruction/*_map.md`、`app/services/deconstruction.py::run_sync`。
- `accept_candidate` 扩展 `staged_decon_*` 落库；`routers/deconstruction.py::POST /novels/{id}/deconstruction/run`（同步）。
- 前端 `CreativeStudio` 加「从想法生成 / 拆解参考小说」模式切换。

## D2：异步整本 Map-Reduce + 全维度

- **新表** `DeconstructionRun`（`models/auto_entities.py`）+ **Alembic 迁移** `a1b2c3d4e5f6`（down_revision=`f3a421d91870`，独立测试库验证 upgrade/downgrade 通过）。
- `DeconstructionRunner` + `deconstruction_queue`（仿 `multi_chapter.py` 后台线程），`main.py::lifespan` 启动。
- 编排：分块 → 每维度逐块 **Map**（`get_adapter`+`JsonGuard`）→ **Reduce 程序按键聚合去重**（同名/同标题合并，单条维度取置信度最高）→ 写候选 → 更新进度。单块失败不阻断整本（记 PARTIAL）。
- 补齐 6 维度（meta/structure/setup_payoff/theme/pov/style_fingerprint）schema + map 提示词；accept 扩展：`setup_payoff→Foreshadowing`，`meta/structure/theme/pov/style_fingerprint→Novel`（synopsis/story_outline/style_guide，空写或追加，不覆盖已有非空）。
- 接口：`POST /novels/{id}/deconstruction-runs`（202 入队）+ `GET …/deconstruction-runs[/{id}]`（进度）。
- 前端：异步发起 + 进度轮询 + 进度条；10 维度多选；候选按维度标签展示。

## D3：仿写（pastiche）

- `app/prompts/story_engineering/pastiche_framework.md`：读已采纳的 bible（文风/总纲）+ 用户新方向 → 保留文风与结构骨架、替换具体人物情节 → 输出全新原创框架。
- `story_engineering` 新增 `pastiche` operation（复用 `staged_framework` 候选与落库）；前端「仿写新作」入口。接受后可接已有多章生产线生成新作。

## 数据与迁移

- **新增 1 张表 `deconstruction_runs` + 1 个迁移 `a1b2c3d4e5f6`**（只 create_table，down 为 drop，additive）。候选仍复用 `story_memory_records`，落库目标均为既有表。
- `record_type` 新增 `staged_decon_<dim>`（10 种）；`status` 沿用 staged/accepted/rejected。

## 验证

```
cd services/api && .venv/bin/pytest -q     # 59 passed（含 chunker 单测、同步/异步拆解、仿写）
cd apps/web && npm run build               # tsc + vite build 通过
```

部署生效：后端整目录同步 `./scripts/sync_to_deployed.sh --all` + 重启；**部署 DB 需 `alembic upgrade head` 到 `a1b2c3d4e5f6`（迁移前先备份部署 DB）**；前端同步 dist + 重启 web。

## 未完成 / 后续

- Reduce 目前是程序按键聚合；跨块语义合并（如同一人物不同称呼）可后续加模型 reduce。
- 拆解任务的暂停/恢复/取消未做（目前一次性跑完或失败）。
- 仿写目前生成「框架」；基于 bible 批量生成「新人物原型/新章节计划」可后续扩展 pastiche 的 operation。
- 拆解候选的独立管理页（目前在创作中心列表内采纳）。

## 回滚

D1/D3 全 additive（新文件/新 operation，不注册即恢复）。D2 迁移 additive，down 为 drop_table；迁移前备份部署 DB。候选默认不自动接受，未接受不影响正式数据。
