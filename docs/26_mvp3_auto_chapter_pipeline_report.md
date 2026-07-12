# MVP 3 自动章节生产线 Phase 2 报告

## 1. 本轮实现

本轮完成单章 P0：

- Review Mode：`manual_review`、`ai_review_suggest`、`ai_auto_revise`、
  `ai_auto_commit`，以及仅限单章的 `full_autonomous` 权限确认。
- `AutoRunPolicy`。
- `@章节`、`@章节版本` Reference Pack。
- Continuity Report 到确定性的 `RevisionPlan`。
- 单章 Auto Revise、复检和安全 Auto Commit。
- Auto Commit 前备份旧正文为不可变 `pre_auto_commit_backup` ChapterVersion。
- Auto Commit 后生成 `Chapter.summary` 和带来源证据的 `StoryMemoryRecord`。
- 前端运行模式、单章边界、引用搜索/chip、自动状态与修订计划展示。

旧人工审批、approve/reject/revise、旧 generate API 均保留。

## 2. 只完成设计、未实现

- `MultiChapterRun` 和 1/3/5 章串行生产。
- Reverse Story Engineering 及 staging acceptance。
- 完整人物、关系、时间线、伏笔、物品和世界规则记忆更新。
- CheckpointSnapshot。
- 多 Provider 角色分配。
- 自动暂停后的 resume/stop API。
- 版本 diff 和一键回滚 UI。

## 3. 新增文件

```text
docs/20_mvp3_auto_chapter_pipeline_design.md
docs/21_reference_system_design.md
docs/22_reverse_story_engineering_design.md
docs/23_auto_review_revise_commit_design.md
docs/24_story_memory_design.md
docs/25_mvp3_implementation_plan.md
docs/26_mvp3_auto_chapter_pipeline_report.md
services/api/app/models/auto_entities.py
services/api/app/schemas/auto.py
services/api/app/routers/auto_runs.py
services/api/app/routers/references.py
services/api/app/services/auto_pipeline.py
services/api/app/services/reference_service.py
services/api/app/services/story_memory.py
services/api/migrations/versions/c8d6e4a1b203_mvp3_single_chapter_auto_pipeline.py
services/api/tests/test_mvp3_auto_pipeline.py
```

## 4. 修改文件

```text
services/api/app/db.py
services/api/app/main.py
services/api/app/models/__init__.py
services/api/app/models/loop_entities.py
services/api/app/prompts/novel_loop/continuity_checker.md
services/api/app/routers/loop_runs.py
services/api/app/schemas/loop.py
services/api/app/services/context_builder.py
services/api/app/workflow/runner.py
services/api/app/workflow/states.py
apps/web/src/types.ts
apps/web/src/features/chapters/ChapterWorkspaceV2.tsx
apps/web/src/features/runs/ContinuityReportPanel.tsx
apps/web/src/features/runs/RunDetailPage.tsx
apps/web/src/features/runs/RunStateTimeline.tsx
```

## 5. 新增 API

```text
POST /api/projects/{project_id}/chapters/{chapter_id}/auto-run
GET  /api/projects/{project_id}/references/search?q=
POST /api/projects/{project_id}/reference-packs
GET  /api/projects/{project_id}/reference-packs/{pack_id}
GET  /api/projects/{project_id}/story-memory
```

原 `POST /api/projects/{project_id}/chapters/{chapter_id}/run` 仍是人工审批 Loop。
原 `POST /api/chapters/{id}/generate` 未修改。

## 6. 新增数据表

- `auto_run_policies`
- `reference_packs`
- `revision_plans`
- `story_memory_records`

Alembic head：

```text
c8d6e4a1b203
```

fresh SQLite 已验证 upgrade 到 head 和 downgrade 到 `6f75c1ad2931`。

## 7. 自动模式权限边界

允许：

- 在当前项目和章节内生成草稿。
- 创建不可变修订版本。
- 运行 Checker。
- 达到阈值后写入正式正文。
- 创建正文备份、摘要和 Story Memory。

禁止：

- 删除项目、章节或版本。
- 修改模型配置。
- 绕过 RunStep/ModelCall。
- blocker 存在时自动写入。
- 引用其他项目内容。
- 把整本小说正文加入上下文。

`full_autonomous` 当前只执行单章，且必须提交 `permission_confirmed=true`。

## 8. Auto Revise 流程

```text
Draft v1
-> Continuity Checker
-> Pydantic-valid CheckReport
-> BUILD_REVISION_PLAN
-> RevisionWriter
-> ChapterVersion v2
-> Recheck
-> WAIT_HUMAN_APPROVAL 或 AUTO_COMMITTING
```

RevisionPlan 由已验证的 issue 确定性生成，不增加一次结构化模型调用。

## 9. Auto Commit 流程

写入前检查：

- 当前版本属于本 Run 和 Chapter。
- 无 blocker。
- major 符合阈值，P0 默认必须为 0。
- Writer 和 Checker 都有 completed ModelCall。
- 修订轮次和模型调用次数未超限。

写入动作：

```text
AUTO_COMMITTING
-> 旧 Chapter.content 保存为 pre_auto_commit_backup ChapterVersion
-> 当前版本写入 Chapter.content
-> COMMITTED
-> UPDATING_STORY_MEMORY
-> MEMORY_UPDATED
```

所有动作都有 RunStep。旧版本不会被删除。

## 10. @引用机制

P0 支持章节和章节版本。后端验证 project/novel ownership，创建引用快照并记录：

- source ID、版本 ID、标题和参考目的。
- 受预算限制的摘要或 excerpt。
- token estimate、content hash 和约束。

Context Builder 只加载本次 Reference Pack，并为它保留约 15% 上下文预算；不会加载全部章节全文。

## 11. Story Memory

P0 在 Auto Commit 后：

- 更新 `Chapter.summary`。
- 写入 `record_type=chapter_summary` 的 `StoryMemoryRecord`。
- evidence 保存 chapter ID、source version ID 和 content hash。

摘要目前是长度受限的 extractive summary，不增加一次可能失败的模型调用。它不是完整的角色、
时间线或 Canon 更新。

## 12. 测试结果

后端：

```text
27 passed in 18.98s
```

新增定向测试：

```text
5 passed
```

覆盖 Manual Review、major 自动修订、RevisionPlan、新 revision、Auto Commit、旧正文备份、
摘要、Story Memory、blocker 暂停、章节/版本引用和上下文隔离。

前端：

```text
npm run build
41 modules transformed
build passed
```

项目没有 `npm run e2e` script，因此未声称运行前端自动化 E2E。

浏览器冒烟：

- 页面可选择五种模式。
- Auto Commit 显示自动写入与备份提示。
- 生成章数明确限制为 Phase 2 的 1 章。
- `@第` 可搜索章节和版本。
- 选择引用后显示 chip 与参考目的输入。
- 浏览器控制台错误为 0。

为保护现有项目，本轮没有在生产数据库中启动真实 Auto Commit；自动写入链路使用隔离 SQLite
和 mock OpenAI-compatible Provider 验证。

## 13. 部署

已部署到：

```text
~/Library/Application Support/NovelLocalAI/
```

部署数据库备份：

```text
~/Library/Application Support/NovelLocalAI/data/
novel_local_ai.before-mvp3-20260612-160842.db
```

部署后 API/Web 均返回 200，原有 4 个项目和 7 个章节仍在。

## 14. 当前风险

1. `full_autonomous` 目前仅是单章授权，不是多章生产。
2. 摘要是 extractive P0，复杂事件和伏笔信息可能不足。
3. 暂停后需要人工检查并创建新 Run，尚无 resume。
4. 备份版本已存在，但缺少面向用户的一键回滚 API/UI。
5. Writer、Checker 仍共用一个 Provider，模型角色尚未后端持久化。
6. `min_plot_score` 已持久化，但 Checker 尚未输出 plot score，因此暂不参与阈值。

## 15. 下一轮建议

进入 Phase 3 前先补两个小能力：

1. ChapterVersion 一键恢复 API 和 Version Diff。
2. PAUSED Run 的明确 resume/abort 语义。

随后实现 `MultiChapterRun` 的 1/3/5 章串行调度，直接复用本轮单章 Policy、
Reference Pack、Auto Revise、Auto Commit 和 Story Memory，不新建第二套章节执行器。
