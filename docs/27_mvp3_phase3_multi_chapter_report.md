# MVP 3 Phase 3 多章生产线交付报告

## 本轮实现

- 新增 `MultiChapterRun`，支持从指定章节开始连续处理 1 / 3 / 5 章。
- 每章复用现有 `ChapterLoopRun`，保留 Draft、Continuity Check、Auto Revise、
  Auto Commit、ChapterVersion、ModelCall 与 RunStep 日志。
- 支持人工审批模式：父生产线在子 Run 进入 `WAIT_HUMAN_APPROVAL` 后等待，用户批准后
  可恢复并进入下一章。
- 支持生产线暂停、恢复、终止以及同一本小说唯一活动生产线约束。
- 遇到章节不存在、章节计划缺失、子 Run blocker/失败、模型调用达到上限时暂停。
- 每完成 3 章创建一个最小 `CheckpointSnapshot`，证据指向来源章节和章节版本。
- 新增 ChapterVersion 恢复 API。恢复前保存 `pre_restore_backup`，并记录
  `VERSION_RESTORED` RunStep。
- 单章 PAUSED Run 可以继续或终止。
- 前端章节页可选择 1 / 3 / 5 章；Runs 页面显示生产线进度、暂停原因和操作入口。

## 新增后端

- `services/api/app/services/multi_chapter.py`
- `services/api/app/routers/multi_chapter_runs.py`
- `services/api/tests/test_mvp3_multi_chapter.py`
- `services/api/migrations/versions/f3a421d91870_mvp3_phase3_multi_chapter_pipeline.py`

## 新增前端

- `apps/web/src/features/runs/MultiChapterRunsPanel.tsx`

## 主要 API

- `POST /api/projects/{project_id}/multi-chapter-runs`
- `GET /api/projects/{project_id}/multi-chapter-runs`
- `GET /api/projects/{project_id}/multi-chapter-runs/{run_id}`
- `POST /api/projects/{project_id}/multi-chapter-runs/{run_id}/pause`
- `POST /api/projects/{project_id}/multi-chapter-runs/{run_id}/resume`
- `POST /api/projects/{project_id}/multi-chapter-runs/{run_id}/stop`
- `GET /api/projects/{project_id}/checkpoints`
- `GET /api/chapters/{chapter_id}/versions`
- `POST /api/projects/{project_id}/chapters/{chapter_id}/versions/{version_id}/restore`
- `POST /api/projects/{project_id}/runs/{run_id}/resume`
- `POST /api/projects/{project_id}/runs/{run_id}/abort`

## 安全边界

- 多章生产线不会创建、删除或重排章节。
- 目标章节缺少目标和大纲时进入 `CHAPTER_PLAN_MISSING`，不会猜测后续计划。
- blocker 子 Run 不会自动写入正文，父 Run 同步进入暂停。
- 同一本小说同一时间只允许一个 active MultiChapterRun。
- 自动写入继续沿用 ChapterVersion 和正文备份机制。
- 恢复旧版本不会删除新版本或历史正文备份。

## 测试结果

- 后端：`34 passed in 23.89s`
- 前端：`npm run build` 通过，Vite 生成生产构建。
- Migration：空 SQLite 从 baseline 连续升级至 `f3a421d91870`，确认创建
  `multi_chapter_runs` 与 `checkpoint_snapshots`。

## 尚未实现

- Reverse Story Engineering：从已批准章节提取故事框架、角色卡、世界规则和后续计划。
- 缺少章节计划时自动生成 staging 计划并等待接受。
- Story Memory 独立管理页和逐条 staging 审批。
- 角色、世界规则、时间线、伏笔的结构化自动更新。
- 5 章之外的自定义 N 章与高级确认。
- 父生产线专属详情路由、跨版本 diff 和 checkpoint 可视化详情。
- 浏览器自动化 E2E 测试；当前前端以 TypeScript build 和人工冒烟测试覆盖。

## 下一版建议

进入 MVP 3 Phase 4，先实现 P0 Reverse Story Engineering。所有抽取结果进入 staging，
必须带来源章节与证据，用户接受后才写入项目资料；不要直接污染 Canon。

## 回滚

1. 停止本地前后端服务。
2. 恢复部署前 SQLite 备份。
3. 恢复上一版应用目录。
4. 若只回退数据库 schema，可执行 `alembic downgrade c8d6e4a1b203`；执行前必须备份，
   此操作会删除多章生产线和 checkpoint 表。
