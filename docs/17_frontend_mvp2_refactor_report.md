# 前端 MVP 2 交互重构报告

## 1. 改动目标

本轮不更换视觉体系，重点修正任务路径：

- 首页优先呈现继续写作、待审批、运行中和失败。
- 项目默认进入 Overview，而不是创意生成。
- 章节页区分正式正文与不可变 AI Version。
- Loop Run 具备状态、版本、检查结果和人工决策入口。
- Models 先解释 Writer、Checker、Summary，再展示 Provider 和模型库存。
- Prompt 进入全局导航，旧生成和 Canon/原始日志降级到 Advanced。

## 2. 新增文件

### 文档

- `docs/14_frontend_interaction_refactor_decision.md`
- `docs/15_frontend_api_gap_report.md`
- `docs/16_frontend_refactor_implementation_plan.md`
- `docs/17_frontend_mvp2_refactor_report.md`

### 全局与项目组件

- `apps/web/src/components/AppShell.tsx`
- `apps/web/src/components/GlobalNav.tsx`
- `apps/web/src/components/ProjectOverview.tsx`
- `apps/web/src/components/ProjectWorkspaceShell.tsx`

### Projects

- `apps/web/src/features/projects/CreateProjectDialog.tsx`
- `apps/web/src/features/projects/ProjectCardV2.tsx`

### Chapters

- `apps/web/src/features/chapters/ChapterWorkspaceV2.tsx`
- `apps/web/src/features/chapters/CurrentRunCard.tsx`
- `apps/web/src/features/chapters/ContextInspector.tsx`

### Runs

- `apps/web/src/features/runs/RunListPage.tsx`
- `apps/web/src/features/runs/RunDetailPage.tsx`
- `apps/web/src/features/runs/RunStateTimeline.tsx`
- `apps/web/src/features/runs/RunDecisionBar.tsx`
- `apps/web/src/features/runs/ContinuityReportPanel.tsx`
- `apps/web/src/features/runs/VersionPreview.tsx`

### Models

- `apps/web/src/features/models/ModelRoleAssignments.tsx`
- `apps/web/src/features/models/ProviderDiagnosticsCard.tsx`

## 3. 修改文件

### 前端

- `apps/web/src/App.tsx`
- `apps/web/src/types.ts`
- `apps/web/src/services/api.ts`
- `apps/web/src/components/Dashboard.tsx`
- `apps/web/src/components/ModelSettings.tsx`

### 后端

- `services/api/app/schemas/loop.py`
- `services/api/app/routers/loop_runs.py`
- `services/api/tests/test_loop_stability.py`

旧 `Workspace.tsx`、`WorkspaceShell.tsx`、`CreativeStudio.tsx`、
`PromptManager.tsx`、`LocalModelCenter.tsx` 均保留。

## 4. API 补丁

新增只读摘要接口：

```text
GET /api/loop-runs
GET /api/projects/{project_id}/runs
GET /api/chapters/{chapter_id}/loop-runs
```

支持 `status`、`limit` 及全局接口的 `project_id`、`chapter_id` 过滤。列表不返回
prompt、response、assembled context 或版本正文。

旧 `POST /api/chapters/{id}/generate` 没有修改。新 Loop 仍使用独立
`POST /api/projects/{project_id}/chapters/{chapter_id}/run`。

## 5. 页面前后对比

| 页面 | 改造前 | 改造后 |
| --- | --- | --- |
| 首页 | 项目列表与常驻创建表单并列 | 项目为主体；创建使用 modal；显示 waiting/running/failed 和模型健康 |
| 项目入口 | 默认创作中心 | 默认 Overview，只有一个 Next Action |
| 章节 | 正文、旧生成、Canon、审稿和日志混排 | 左章节、中正式正文、右 Loop/Context；旧工具进入 Advanced |
| Run | 无完整入口 | 时间线、Version、Continuity、approve/reject/revise、折叠日志 |
| Models | Provider 表单优先，参数长页 | Task Roles 优先；Provider 第二层；高级参数默认折叠 |
| Prompts | 项目内 tab | 全局导航入口 |

## 6. 用户路径前后对比

### 继续写作

```text
改造前：首页 -> 项目 -> 默认创作中心 -> 猜测章节入口
改造后：首页 Continue writing -> Overview Next Action -> Chapters
```

### 审批草稿

```text
改造前：前端无法发现 waiting run
改造后：首页/Overview/Runs -> Run Detail -> Approve / Reject / Revise
```

### 模型配置

```text
改造前：Provider、参数教学、库存混排
改造后：任务角色 -> Provider 连接与测试 -> 高级参数 -> 本地库存
```

## 7. 未实现功能

- 完整 Timeline 页面。
- 独立 Versions 页面与版本 Diff。
- 完整 Logs 搜索、筛选和导出。
- Prompt 版本系统。
- Loop retry/cancel。
- 自动 Canon 更新 UI。
- 移动端适配。
- React Router 或大型状态管理。

## 8. 仍有 API 缺口

1. 没有持久化 Writer/Checker/Summary 的 settings API。
2. 当前 Loop Writer 与 Checker 仍使用同一个 Provider。
3. 没有独立 ChapterVersion list/detail API。
4. Provider test 没有结构化 category、target、tested_at 和建议字段。
5. 没有 Loop retry/cancel API。
6. 没有首页 Project Summary 聚合接口；项目卡当前会额外读取项目与章节。

模型角色选择因此明确标为浏览器偏好；只有 Writer 偏好会成为新 Loop 表单的默认选项，
Checker 和 Summary 目前只是交互草案。

## 9. 测试结果

### 后端

```text
services/api/.venv/bin/pytest
18 passed in 14.00s
```

新增摘要接口定向测试：

```text
services/api/.venv/bin/pytest tests/test_loop_stability.py -q
9 passed
```

覆盖全局、项目和章节列表，并确认摘要不包含 steps、versions、model_calls。

### 前端

```text
npm run build
41 modules transformed
build passed
```

最终产物：

```text
dist/assets/index-DkwTldFp.js
dist/assets/index-0T0m4e1W.css
```

### 浏览器冒烟

在部署页面 `http://127.0.0.1:5173/` 验证：

- Projects V2 与全局状态可见。
- 项目卡异步显示真实小说名、章节进度和主动作。
- 点击项目默认进入 Overview。
- Overview Next Action 可进入 Chapters。
- Chapters 显示 Published Content、Start Loop 和 Context Inspector。
- Models 首屏显示 Writer/Checker/Summary，Provider 删除不在主界面暴露。
- 全局 Runs 空状态可用。
- 直接刷新项目 Chapters 深链后恢复成功。
- 浏览器控制台错误数为 0。

部署数据库当前没有 Loop Run。为避免伪造数据或触发一次昂贵的真实模型任务，本轮没有在
生产数据中浏览器点击 approve/reject/revise；这些后端决策由现有 E2E pytest 覆盖，前端
Run Detail 已通过 TypeScript 生产构建。

## 10. 部署与数据保护

已同步到：

```text
~/Library/Application Support/NovelLocalAI/
```

部署前备份：

```text
~/Library/Application Support/NovelLocalAI/data/
novel_local_ai.before-mvp2-20260612-112743.db
```

部署后：

- API health 返回 200。
- `GET /api/loop-runs` 返回 200。
- Alembic 标记为 `0f19e48aa920`。
- 原有 3 个项目仍存在。
- 前端由 LaunchAgent 在 5173 提供。

## 11. 当前风险

1. 角色分配只在浏览器保存，不是后端全局真配置。
2. hash 路由足够支撑 MVP，但缺少成熟 Router 的参数和 404 管理。
3. 项目卡存在本地规模可接受的额外 API 请求，项目很多时需要聚合接口。
4. Run Detail 读取完整日志，虽默认折叠，超长模型输出仍可能增大响应。
5. 真实浏览器审批链路仍需要隔离测试数据库的自动化 E2E。

## 12. 回滚

1. 停止 `com.novel-local-ai.api` 与 `com.novel-local-ai.web` LaunchAgent。
2. 用上述 `before-mvp2` 备份恢复 SQLite。
3. 恢复部署目录上一版 `apps/web/dist` 与 `services/api/app`。
4. 重新启动两个 LaunchAgent。

新增只读 API 不修改业务数据，也可保留而只回滚前端。

## 13. 下一轮建议

优先实现两项：

1. 增加后端 model role settings，并让 Writer 与 Checker 可独立选择 Provider。
2. 使用隔离 SQLite 和 mock provider 增加前端 Playwright E2E，完整覆盖
   Start Loop、waiting、approve、reject、revise 与刷新恢复。

随后再做 Version Diff、Run Logs 筛选和 Project Summary 聚合接口。
