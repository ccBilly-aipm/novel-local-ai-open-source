# 前端 MVP 2 最小改造路线

## 总原则

1. 保留当前 `App.tsx`、Dashboard、Workspace、ModelSettings。
2. 新页面先并行接入，不删除旧入口。
3. Loop UI 只调用新 Loop API。
4. 旧生成按钮明确标识后逐步降级，不改变 API 行为。
5. 每阶段保持 `npm run build` 和后端 pytest 通过。

## Phase 1：审计，不改前端代码

### 目标

确认页面、导航、API、状态、用户路径和竞品模式。

### 文件

新增：

- `docs/09_frontend_ux_audit.md`
- `docs/10_reference_product_patterns.md`
- `docs/11_mvp2_frontend_information_architecture.md`
- `docs/12_mvp2_wireframes.md`
- `docs/13_frontend_mvp2_roadmap.md`

### 验收

- 当前页面与 API 有完整清单。
- 四条核心用户路径可视化。
- MVP 2 页面边界明确。

### 风险

- 设计脱离真实 API。

### 回滚

- 删除新增文档，不影响运行代码。

## Phase 2：首页和模型配置轻量优化

### 目标

降低首次使用和恢复项目的摩擦，不引入 Router。

### 修改文件

- `src/components/Dashboard.tsx`
- `src/components/ModelSettings.tsx`
- `src/components/LocalModelCenter.tsx`
- `src/types.ts`

### 新增文件

```text
src/components/CreateProjectDialog.tsx
src/components/ProjectCard.tsx
src/components/ProviderTestResult.tsx
src/components/ModelRoleSummary.tsx
src/components/StatusBadge.tsx
```

### 最小内容

1. 创建表单改为 dialog/drawer。
2. 项目卡增加小说名、章节数和最近更新时间；run 摘要若无聚合 API则暂不伪造。
3. Models 顶部增加“任务角色”说明性卡片；持久化 API 未完成前标记为 planned，不保存假配置。
4. Provider 测试错误使用结构化卡片。
5. 高级参数折叠。

### 验收

- 项目列表成为首页视觉主体。
- 创建项目仍可完成并自动进入工作区。
- Provider CRUD/test 行为不变。
- 用户能区分模型文件、loaded model、Provider。

### 风险

- 后端测试接口当前错误只返回 message，分类能力有限。

### 回滚

- 保留旧表单组件分支或 feature flag。

## Phase 3：新增项目内 WorkspaceShell

### 目标

建立 Overview 和稳定的项目位置感，保留现有 tabs 内容。

### 修改文件

- `src/App.tsx`
- `src/components/WorkspaceShell.tsx`

### 新增文件

```text
src/features/workspace/ProjectOverview.tsx
src/features/workspace/ProjectHeader.tsx
src/features/workspace/ProjectNav.tsx
src/features/workspace/NextActionCard.tsx
src/features/workspace/projectSummary.ts
```

### 内容

- 默认 tab 改为 Overview。
- Prompt 从项目 tab 暂不删除，但标记 Advanced，等全局导航完成后迁移。
- Overview 使用已有 project/chapter/provider API生成保守摘要。
- 没有 run list API时不显示虚假待审批数量。

### 验收

- 进入项目首先看到项目状态和继续写作动作。
- 现有 CreativeStudio、Workspace、Characters、Worldbuilding 仍可访问。
- 切换项目不会残留上一项目状态。

### 风险

- Overview 可能触发过多并行 API。

### 回滚

- feature flag 将默认 tab 切回 `create`。

## Phase 4：新增 Loop Run Page

### 目标

产品化 MVP 1.1 的核心价值：启动、观察、审批。

### 后端前置

至少补一个查询能力：

```text
GET /api/projects/{project_id}/runs
GET /api/chapters/{chapter_id}/loop-runs
```

否则前端无法可靠发现刷新前的 run_id。

### 修改文件

- `src/components/WorkspaceShell.tsx`
- `src/components/Workspace.tsx`
- `src/types.ts`
- `src/services/api.ts`（如需错误 detail 结构支持）

### 新增文件

```text
src/features/loop-runs/types.ts
src/features/loop-runs/loopApi.ts
src/features/loop-runs/ChapterRunPage.tsx
src/features/loop-runs/RunStateTimeline.tsx
src/features/loop-runs/RunVersionPreview.tsx
src/features/loop-runs/ContinuityReport.tsx
src/features/loop-runs/ApprovalBar.tsx
src/features/loop-runs/RevisionDialog.tsx
src/features/loop-runs/useRunPolling.ts
```

### 内容

- 章节页增加“Start Loop Run”。
- 若 active slot 已占用，显示打开现有 run。
- 轮询 run detail。
- approve/reject/revise。
- 明确 draft 未写入正式正文。
- 终态停止轮询。

### 验收

- 页面刷新后可通过 run_id 查询恢复。
- approve 后 Chapter.content 更新。
- reject/revise 前后 Chapter.content 不更新。
- JSON/timeout 错误可定位到 step 和 ModelCall。
- 同一章节不会发出第二个 active run。

### 风险

- 无 Router 时 run 深链仍有限。
- 完整 prompt/response 体积可能影响渲染。

### 回滚

- 关闭 `VITE_FEATURE_LOOP_RUNS`。
- 后端 Loop API 和旧 Workspace 保留。

## Phase 5：Version Diff 和 Run Logs

### 目标

将审查与工程诊断从章节编辑器右栏拆出。

### 后端前置

建议新增：

```text
GET /api/chapters/{chapter_id}/versions
GET /api/projects/{project_id}/runs?status=&chapter_id=
GET /api/projects/{project_id}/runs/{run_id}/model-calls
```

日志最好支持分页或字段裁剪。

### 修改文件

- `src/features/loop-runs/ChapterRunPage.tsx`
- `src/types.ts`

### 新增文件

```text
src/features/versions/VersionList.tsx
src/features/versions/VersionDiff.tsx
src/features/logs/RunLogsPage.tsx
src/features/logs/RunStepList.tsx
src/features/logs/ModelCallDetail.tsx
src/features/logs/JsonErrorPanel.tsx
src/utils/textDiff.ts
```

### 验收

- 可比较 draft/revision/approved。
- 旧版本只读。
- 可按状态筛选 runs。
- 失败 step 默认展开。
- 原始 prompt/response 默认折叠。

### 风险

- 自行实现复杂 diff 容易性能差。

### 回滚

- 移除独立 tab；Run Detail 保留简版版本预览和错误摘要。

## Phase 6：Router 与轻量状态管理

### 目标

支持深链、刷新恢复、浏览器返回和稳定的数据缓存。

### 修改文件

- `src/main.tsx`
- `src/App.tsx`
- 所有导航入口。

### 新增文件

```text
src/router.tsx
src/layouts/AppShell.tsx
src/layouts/ProjectLayout.tsx
src/state/preferences.ts
src/hooks/useProject.ts
```

### 技术选择

- Router：React Router，只有此时页面数量已证明需要。
- 状态管理：先用 route params + local hooks；不要默认引入 Redux。
- 若跨页面缓存明显重复，再评估 TanStack Query，而不是一次加入多套库。

### 验收

- 刷新保留 project/tab/chapter/run。
- Back/Forward 正常。
- 可复制 run URL。
- 无效 ID 有 Not Found 和返回入口。

### 风险

- Router 一次改动所有导航。
- 旧 local state 与 route state 可能短期重复。

### 回滚

- 保留旧 `App.tsx` 条件渲染入口一个发布周期。

## 推荐执行顺序

```text
Phase 2 Projects
-> Phase 3 Project Overview
-> 后端补 run list
-> Phase 4 Loop Run
-> Phase 5 Logs/Diff
-> Phase 6 Router
```

## 哪些页面晚点做

1. Timeline 可等 MVP 3 Canon staging。
2. 独立 Story Bible 可先复用总纲、角色、世界观页面。
3. Settings 在默认模型角色和 workflow policy API 出现后再实装。
4. Canvas、关系图、GraphRAG 不进入 MVP 2。

## 前端绝不能写死的内容

1. Provider 类型只允许固定几个值。
2. Writer/Checker 必须是同一个模型。
3. Loop 状态永远只有当前六七种；应容忍未知状态。
4. approve 可以直接 PATCH Chapter。
5. continuity passed 就自动 approve。
6. JSON 解析失败可以当空报告。
7. active run 可以靠前端禁用按钮保证。
8. Prompt/ModelCall 一定足够小，可一次渲染。

## 下一轮建议实施

下一轮只实现 Phase 2：

1. 首页创建项目 dialog。
2. 项目卡层级和“继续写作”动作。
3. Provider 测试结果诊断卡。
4. Models 页面分成“任务角色说明 / Provider / 本地模型库存”三层。

同时为 Phase 4 先补后端项目/章节 run list API 设计，不提前实现复杂 Loop UI。
