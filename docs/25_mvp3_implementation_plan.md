# MVP 3 实施计划

## Phase 1：设计与审计

- 完成 docs/20 到 docs/25。
- 确认旧 Loop、审批、版本和 Context Builder 边界。

验收：明确哪些能力只设计、不实现。

## Phase 2：单章 P0

实现：

- `AutoRunPolicy` 与 Review Mode。
- `ReferencePack`，支持章节和版本。
- CheckReport 到 `RevisionPlan`。
- 单章 Auto Revise。
- 满足阈值后的安全 Auto Commit。
- Auto Commit 后 `Chapter.summary` 和 `StoryMemoryRecord`。
- 前端运行模式、引用选择和自动状态反馈。

不实现：多章调度、反向提取、完整 Canon 自动更新、完整 Memory 页面。

## Phase 3：多章 P0

- `MultiChapterRun`。
- 1/3/5 章串行运行。
- 每章复用 Phase 2 管线。
- blocker、调用数、计划缺失等条件暂停。
- checkpoint。

## Phase 4：反向提取 P0

- 已批准章节到 staging candidates。
- 故事框架、角色、世界规则和后续计划。
- 人工接受后才进入项目资料。

## Phase 5：前端完善

- 多章运行设置。
- 完整引用选择器。
- Revision diff。
- Story Memory 与 extraction staging 面板。

## Phase 2 文件计划

新增：

```text
services/api/app/models/auto_entities.py
services/api/app/schemas/auto.py
services/api/app/routers/auto_runs.py
services/api/app/routers/references.py
services/api/app/services/reference_service.py
services/api/app/services/auto_pipeline.py
services/api/app/services/story_memory.py
services/api/tests/test_mvp3_auto_pipeline.py
```

修改：

```text
workflow/runner.py
workflow/states.py
models/__init__.py
db.py
main.py
schemas/loop.py
routers/loop_runs.py
services/context_builder.py
prompts/novel_loop/continuity_checker.md
apps/web/src/types.ts
apps/web/src/features/chapters/ChapterWorkspaceV2.tsx
apps/web/src/features/runs/RunDetailPage.tsx
```

数据库使用新的 Alembic migration。回滚先停止 API，再 downgrade 一版；不会改旧 generate 表。
