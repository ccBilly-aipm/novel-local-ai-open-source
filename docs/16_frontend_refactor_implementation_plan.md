# 前端交互重构实施计划

## 1. 范围

本轮实现：

- GlobalNav 与 AppShell。
- Projects V2 + 创建 modal。
- Project Overview。
- Chapters V2。
- 项目/全局 Runs 最小列表。
- Run Detail、timeline、version、continuity、decisions。
- Models 顶部角色草案与 Provider 诊断卡。
- hash 深链恢复。
- 最小只读 Loop list API。

不实现：

- Timeline、完整 Versions、完整 Logs 搜索。
- Prompt 版本系统。
- 自动 Canon UI。
- React Router。
- 移动端。
- 多章循环。

## 2. 后端新增

### 修改

- `services/api/app/routers/loop_runs.py`
- `services/api/app/schemas/loop.py`
- `services/api/tests/test_loop_stability.py`

### 职责

- 提供全局、项目、章节级 run summary list。
- 保留现有 detail 与 decision API。
- 添加过滤、limit 和排序测试。

## 3. 前端新增组件

| 文件 | 职责 |
| --- | --- |
| `components/AppShell.tsx` | 全局页面容器 |
| `components/GlobalNav.tsx` | Projects/Runs/Models/Prompts/Settings |
| `components/ProjectOverview.tsx` | 项目恢复上下文与唯一 Next Action |
| `components/ProjectWorkspaceShell.tsx` | 项目二级导航与 Run Detail 切换 |
| `features/projects/CreateProjectDialog.tsx` | 创建项目 modal |
| `features/projects/ProjectCardV2.tsx` | 项目进度、最近章节、run 主动作 |
| `features/chapters/ChapterWorkspaceV2.tsx` | 正文/Version、Loop 启动与章节导航 |
| `features/chapters/CurrentRunCard.tsx` | 当前 active/waiting/failed run |
| `features/chapters/ContextInspector.tsx` | 目标、角色、规则、context |
| `features/runs/RunListPage.tsx` | 全局/项目 run summary |
| `features/runs/RunDetailPage.tsx` | 轮询、版本审阅、错误和审批 |
| `features/runs/RunStateTimeline.tsx` | 状态时间线 |
| `features/runs/RunDecisionBar.tsx` | approve/reject/revise |
| `features/runs/ContinuityReportPanel.tsx` | 结构化检查报告 |
| `features/runs/VersionPreview.tsx` | 当前不可变版本正文 |
| `features/models/ModelRoleAssignments.tsx` | 浏览器级 Writer 偏好与角色限制说明 |
| `features/models/ProviderDiagnosticsCard.tsx` | Provider test 诊断 |

## 4. 前端修改

| 文件 | 修改 |
| --- | --- |
| `App.tsx` | 全局页面状态、hash 深链、项目恢复、全局 runs/providers |
| `types.ts` | Loop detail/summary/version/step/model call 类型 |
| `services/api.ts` | 保留结构化 detail 错误 |
| `Dashboard.tsx` | 项目列表主体、全局状态、创建 modal |
| `WorkspaceShell.tsx` | 兼容导出，委托 ProjectWorkspaceShell |
| `ModelSettings.tsx` | 角色优先、诊断卡、高级参数折叠 |

旧 `Workspace.tsx` 不删除，放在“Advanced / Legacy”项目入口。

## 5. 新交互流程

### 首页

```text
打开应用
-> 查看 waiting/running/failed
-> Review waiting draft 或 Continue writing
-> New Project 打开 modal
```

### 项目

```text
打开项目
-> Overview
-> 唯一 Next Action
-> Chapters 或 Run Detail
```

### 章节

```text
选择章节
-> Published Content / Run Version
-> 无 active run: Start Loop
-> 有 active run: Open Run
```

### Run

```text
状态时间线
-> Version + Continuity
-> approve / reject / revise
-> API 状态刷新
```

### Models

```text
任务角色说明
-> Provider connections
-> Test diagnostics
-> Advanced parameters
-> Local inventory
```

## 6. Hash 深链

不用大型 Router，使用 `hashchange`：

```text
#/projects
#/projects/{id}/overview
#/projects/{id}/chapters
#/projects/{id}/runs
#/projects/{id}/runs/{run_id}
#/runs
#/models
#/prompts
#/settings
```

刷新 Run Detail 时，App 根据 project_id 重新读取项目，再查询 run。

## 7. 验收标准

1. 首页项目列表为主体，创建使用 modal。
2. 首页显示真实 run summary 和 Provider 健康状态。
3. 项目默认 Overview。
4. Overview 只有一个推荐主动作。
5. Chapters 可启动 Loop 或打开现有 Run。
6. Published Content 与 Run Version 明确区分。
7. Run Detail 可轮询并显示时间线。
8. approve 有确认，reject/revise 有反馈输入。
9. revise 后版本数量增加，旧版本保留。
10. Failed 显示 step/error_code，无假 Retry。
11. Prompt 移到全局入口。
12. Models 先显示角色草案。
13. Legacy Generation 仍可从 Advanced 找到。
14. `npm run build`、`pytest` 通过。

## 8. 风险

- 无正式 Router，hash 解析必须保持简单。
- role assignment 不是后端真配置，必须明显标注。
- Run Detail 包含完整日志，默认折叠避免性能和隐私问题。
- 项目卡为取得章节进度会调用项目/章节 API；本地单用户规模可接受，后续应改 summary API。

## 9. 回滚

1. 恢复旧 `App.tsx` 条件渲染。
2. `WorkspaceShell.tsx` 直接渲染旧 tabs。
3. `Dashboard.tsx` 恢复常驻创建表单。
4. 删除新增 feature 组件。
5. 保留新增只读 Loop list API，不影响旧行为；也可单独移除。
6. 不需数据库回滚。
