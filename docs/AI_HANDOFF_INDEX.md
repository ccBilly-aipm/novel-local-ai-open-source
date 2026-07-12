# AI Handoff Index

## Project in one sentence

Novel Local AI 是一个 macOS 本地优先的小说写作系统：React Web UI 调用 FastAPI，
通过本地 Provider 生成章节，并用 append-only ChapterVersion、Continuity Checker、
人工审批或受控自动提交、多章生产线和完整 Run 日志保护正式正文。

当前代码入口见：

- `apps/web/src/App.tsx`
- `services/api/app/main.py`
- `services/api/app/workflow/runner.py`
- `services/api/app/services/multi_chapter.py`

## Current stage

**MVP 3 Phase 3 + 生产稳定性补丁。**

这不是早期文档描述的 MVP 1。当前已经实现：

- 单章人工审批 Loop。
- approve / reject / revise。
- AI Auto Revise 与 AI Auto Commit。
- 任意大于 0 的连续章节数量。
- 多章暂停、恢复、终止。
- `@章节`、`@章节版本` Reference Pack。
- Writer 流式预览、草稿恢复和 Provider 自动恢复。
- ChapterVersion 恢复、正文备份、最小 Story Memory 和 checkpoint。

证据：

- `docs/26_mvp3_auto_chapter_pipeline_report.md`
- `docs/27_mvp3_phase3_multi_chapter_report.md`
- `docs/28_multi_chapter_fallback_patch_report.md`
- `docs/29_auto_revision_loop_fix_report.md`
- `services/api/tests/test_mvp3_auto_pipeline.py`
- `services/api/tests/test_mvp3_multi_chapter.py`

## Most important current conclusions

1. 旧 `POST /api/chapters/{chapter_id}/generate` 仍保留，由
   `services/api/app/routers/chapters.py::generate_chapter()` 和
   `services/api/app/pipelines/chapter_pipeline.py` 执行。
2. 新 Loop 走独立 API，由 `services/api/app/routers/loop_runs.py`、
   `services/api/app/routers/auto_runs.py` 和
   `services/api/app/routers/multi_chapter_runs.py` 提供。
3. Writer 先写不可变 `ChapterVersion`；人工模式只有 approve 才写
   `Chapter.content`。自动模式只有通过阈值后才由
   `services/api/app/services/auto_pipeline.py::commit_version()` 写入。
4. blocker 或 `must_pause=true` 不允许自动提交，判断位于
   `services/api/app/services/auto_pipeline.py::next_state_after_check()`。
5. 当前 Story Memory 只实现有来源证据的章节摘要记录，不是完整 Canon 自动更新，
   见 `services/api/app/services/story_memory.py`。
6. Reverse Story Engineering 仅有设计文档，**未实现**，见
   `docs/22_reverse_story_engineering_design.md`。
7. 仓库默认数据库与实际部署数据库不是同一份，迁移状态不同，详见
   `docs/AI_CURRENT_STATUS.md`。

## Read these first

1. `CLAUDE.md`
2. `docs/AI_HANDOFF_INDEX.md`
3. `docs/AI_CURRENT_STATUS.md`
4. `docs/AI_ARCHITECTURE_MAP.md`
5. `docs/AI_CODE_TOUCH_MAP.md`
6. `docs/AI_NEXT_TASKS.md`
7. `docs/AI_RUN_AND_TEST_GUIDE.md`
8. `docs/AI_RISK_REGISTER.md`
9. 最新实现报告：`docs/26_mvp3_auto_chapter_pipeline_report.md` 到
   `docs/29_auto_revision_loop_fix_report.md`

`docs/01` 到 `docs/08` 用于理解历史演进，其中的“未实现”列表不能当作当前状态。

## Safe next action

最高优先级是 **MVP 3 Phase 4 Reverse Story Engineering P0**：

- 从已批准章节抽取故事框架、角色卡、世界规则和后续章节计划候选。
- 所有候选先进入 staging。
- 每条候选必须带来源章节、证据和置信度。
- 未经接受不能写入正式项目资料或 Canon。

执行前先按 `docs/AI_NEXT_TASKS.md` 输出设计和修改计划，不要直接改代码。

## Safe to do

- 在独立新模块中增加 staging 抽取实体、schema、router、service 和测试。
- 增加只读诊断 API、分页日志 API、版本 diff。
- 增加测试和文档。
- 修正 README 中与当前代码不一致的边界描述，但不要把文档修正和业务重构混在一起。

## Do not touch

- 不得破坏 `services/api/app/routers/chapters.py::generate_chapter()`。
- 不得删除 `WritingTask`、`GenerationRun` 或
  `services/api/app/pipelines/chapter_pipeline.py`。
- 不得修改或删除已有 ChapterVersion。
- 不得让模型输出绕过 JsonGuard、DraftTextGuard、RunStep 或 ModelCall。
- 不得让抽取结果或 Story Memory 直接污染 Canon。
- 不得对结构不明的 SQLite 数据库直接 `alembic stamp`。

## Verification commands

```bash
cd services/api
.venv/bin/pytest -q
```

当前验证：`38 passed`，2026-06-12。

```bash
cd apps/web
npm run build
```

当前验证：通过，42 modules transformed，2026-06-12。

## Common paths

| Purpose | Path |
|---|---|
| Frontend entry and hash routing | `apps/web/src/App.tsx` |
| Project workspace | `apps/web/src/components/ProjectWorkspaceShell.tsx` |
| Chapter generation UI | `apps/web/src/features/chapters/ChapterWorkspaceV2.tsx` |
| Run detail UI | `apps/web/src/features/runs/RunDetailPage.tsx` |
| FastAPI entry | `services/api/app/main.py` |
| Old generation API | `services/api/app/routers/chapters.py` |
| Loop APIs | `services/api/app/routers/loop_runs.py` |
| Auto-run APIs | `services/api/app/routers/auto_runs.py` |
| Multi-chapter APIs | `services/api/app/routers/multi_chapter_runs.py` |
| Single-chapter state machine | `services/api/app/workflow/runner.py` |
| Multi-chapter coordinator | `services/api/app/services/multi_chapter.py` |
| Auto revise/commit policy | `services/api/app/services/auto_pipeline.py` |
| Loop models | `services/api/app/models/loop_entities.py` |
| Auto/multi models | `services/api/app/models/auto_entities.py` |
| Migrations | `services/api/migrations/versions/` |
| Tests | `services/api/tests/` |

## Advice for Claude Code

Treat this repository as an evolved prototype with two coexisting generation paths. Prefer additive
changes. Read the tests before changing state transitions. Always verify both the old generation test
in `services/api/tests/test_api.py` and the Loop tests. Use a test database for migrations and never
experiment on the deployed SQLite file without a timestamped backup.

## Copy this prompt to Claude Code

```text
You are taking over this repository from another AI coding agent.

Before making changes:
1. Read CLAUDE.md
2. Read docs/AI_HANDOFF_INDEX.md
3. Read docs/AI_CURRENT_STATUS.md
4. Read docs/AI_NEXT_TASKS.md
5. Inspect the key files listed there

Then output:
- Your understanding of the project
- Current stage
- What is already working
- What must not be broken
- Your proposed next task
- Files you plan to touch
- Verification commands

Do not edit code until the user confirms.
```
