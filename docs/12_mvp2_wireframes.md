# MVP 2 关键页面 Wireframes

## 1. Projects 首页

### 页面目标

快速恢复最近工作、发现待审批 run、创建项目；创建表单不压过项目。

### 主要组件

- GlobalNav
- ProjectSummaryHeader
- PendingApprovalBanner
- ProjectCard
- CreateProjectDialog
- ModelHealthBadge

### 用户操作

- 继续写作。
- 打开待审批 run。
- 创建/删除项目。
- 跳转 Models。

### API

- 当前可用：`GET /projects`、`GET /projects/{id}`。
- 建议新增：项目摘要、待审批 run 聚合。

### 状态

- Loading：项目卡 skeleton。
- Empty：创建第一本小说。
- Error：后端连接失败，可重试。

### Wireframe

```text
┌ Novel Local AI ────────────────────────────────────────────────┐
│ Projects     Runs (2)     Models ✓     Prompts     Settings   │
├───────────────────────────────────────────────────────────────┤
│ Projects                                      [+ New Project] │
│ 2 runs waiting for approval                   [Review now]    │
│ Model health: Writer ✓  Checker ✓                            │
├───────────────────────────────────────────────────────────────┤
│ Recent                                                        │
│ ┌──────────────────────┐ ┌──────────────────────┐             │
│ │ 潮汐城               │ │ 旧宅                 │             │
│ │ 8/20 chapters        │ │ 3/12 chapters        │             │
│ │ Next: Chapter 9      │ │ 1 failed run         │             │
│ │ Last: waiting review │ │ Last: 15 min ago     │             │
│ │ [Continue writing]   │ │ [Open project]       │      [...]  │
│ └──────────────────────┘ └──────────────────────┘             │
│                                                               │
│ All Projects                                                  │
│ ...                                                           │
└───────────────────────────────────────────────────────────────┘
```

## 2. Project Overview

### 页面目标

恢复项目上下文，并给出唯一明确的下一步。

### 主要组件

- ProjectHeader
- NextActionCard
- ChapterProgress
- RecentRuns
- StoryBibleCompleteness
- ModelRoleStatus

### 用户操作

- 继续当前章节。
- 审批 waiting run。
- 修复 failed run。
- 创建章节。
- 打开设定/人物。

### API

- 当前：project、chapter list、characters、world rules、providers。
- 建议新增：project run list/summary。

### Wireframe

```text
┌ Projects / 潮汐城                                           ┐
│ Overview  Story Bible  Characters  Timeline  Chapters        │
│ Runs  Versions  Logs                                         │
├───────────────────────────────────────────────────────────────┤
│ NEXT ACTION                                                   │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ Chapter 8 has a draft waiting for approval               │ │
│ │ Continuity: passed · Version 12 · 4 min ago              │ │
│ │ [Review and approve]                [Open chapter]        │ │
│ └───────────────────────────────────────────────────────────┘ │
│                                                               │
│ Progress              Recent chapters         Models          │
│ Approved 7/20         Ch.8 Waiting             Writer ✓        │
│ Draft 1               Ch.7 Approved            Checker ✓       │
│ Outlined 12           Ch.6 Approved            Summary inherit │
│                                                               │
│ Story Bible: Outline ✓  Characters 6  Rules 18  Timeline 0    │
└───────────────────────────────────────────────────────────────┘
```

## 3. Chapter Workspace

### 页面目标

在不干扰正文编辑的情况下显示章节结构、相关上下文和当前 run。

### 主要组件

- ChapterTree
- ChapterStatusBadge
- ContentModeSwitch
- ChapterEditor
- ContextInspector
- CurrentRunCard

### 用户操作

- 编辑并保存正式正文。
- 编辑目标和大纲。
- 启动 Loop。
- 打开当前 run。
- 查看 draft 但不误认为正式正文。

### API

- Chapter CRUD/context。
- `POST /projects/{project}/chapters/{chapter}/run`。
- `GET /projects/{project}/runs/{run}`。

### 状态

- 无章节：创建章节。
- Active run：禁用重复启动，显示 current step。
- Waiting：突出审批入口。
- Failed：显示 error code 和 Run Detail。

### Wireframe

```text
┌ 潮汐城 / Chapters / Chapter 8 ────────────────────────────────┐
│ [Published] [Run version v12] [Compare]       Status: Waiting │
├──────────────┬───────────────────────────────┬────────────────┤
│ Chapters     │ Chapter 8 午夜锁死            │ Inspector      │
│              │                               │ Goal           │
│ ✓ Ch.7       │ [title____________________]    │ ...            │
│ ● Ch.8 WAIT  │                               │ Characters     │
│ ○ Ch.9       │ [正文或选中版本]              │ 林澈           │
│ ○ Ch.10      │                               │ Rules          │
│              │                               │ 00:00-00:07    │
│ [+ Chapter]  │                               │ Context 486/2400│
│              │                               │                │
│              │                               │ Current Run    │
│              │                               │ WAIT APPROVAL  │
│              │                               │ [Open Run]     │
├──────────────┴───────────────────────────────┴────────────────┤
│ [Save published content]                   [Start Loop Run]   │
└───────────────────────────────────────────────────────────────┘
```

“Published”和“Run version”必须使用不同底色和明确标签。

## 4. Loop Run Page

### 页面目标

观察状态机、审查版本、理解检查结果并做人工决策。

### 主要组件

- RunHeader
- RunStateTimeline
- VersionPreview
- ContinuityReport
- DecisionBar
- ModelCallLink

### 用户操作

- approve。
- reject。
- revise。
- 查看原始日志。
- 返回章节。

### API

- GET run detail。
- POST approve/reject/revise。

### 状态

- Running：定时轮询。
- Waiting：决策栏可用。
- Approved/Rejected：只读决策记录。
- Failed：错误卡和日志入口。

### Wireframe

```text
┌ Chapter 8 / Run 9f58... ─────────────────────────────────────┐
│ WAITING FOR APPROVAL   Writer: qwen-27b   Started 10:30      │
│ This version has NOT been written to Chapter.content.        │
├───────────────────────────────────────────────────────────────┤
│ ✓ Load project  ✓ Context  ✓ Draft  ✓ Continuity  ● Approval │
├───────────────────────────────┬───────────────────────────────┤
│ Version 12 · draft            │ Continuity Report             │
│ [v11] [v12 current]           │ Passed · severity none        │
│                               │ 0 issues                       │
│ 23:58，林澈……                 │                               │
│                               │ Context                       │
│                               │ 486 / 2400 tokens             │
│                               │ [View model calls]            │
├───────────────────────────────┴───────────────────────────────┤
│ [Reject]   [Request revision]             [Approve version]  │
└───────────────────────────────────────────────────────────────┘
```

### Approve modal

```text
Approve Version 12?

This will copy Version 12 into the official chapter content.
The existing ChapterVersion history will remain unchanged.

[Cancel] [Approve and publish]
```

### Revise drawer

```text
Revision feedback (required)
[____________________________________________________________]

The current version will remain unchanged.
A new revision version will be created and checked again.

[Cancel] [Generate revision]
```

## 5. Model Configuration

### 页面目标

让用户先理解“任务角色”，再管理连接和本机模型。

### 主要组件

- ModelRoleAssignments
- ProviderList
- ProviderEditor
- ProviderTestResult
- LocalModelInventory
- AdvancedParametersDisclosure

### 用户操作

- 指定 Writer/Checker/Summary。
- 新增/编辑 Provider。
- 测试连接。
- 加载 LM Studio 模型。
- 查看诊断。

### API

- 现有 Provider CRUD/test/inventory/load/unload。
- 角色映射需要新增后端 API。

### Wireframe

```text
┌ Models ───────────────────────────────────────────────────────┐
│ Task roles                                                    │
│ Writer  [LM Studio · qwen-27b ▼]  ✓ Available                │
│ Checker [LM Studio · qwen-27b ▼]  ✓ Available                │
│ Summary [Inherit checker      ▼]                              │
├───────────────────────────────────────────────────────────────┤
│ Providers                              [+ Add Provider]        │
│ ┌─────────────────┐  ┌─────────────────────────────────────┐ │
│ │ LM Studio ✓     │  │ Connection                          │ │
│ │ llama.cpp ?     │  │ Type / URL / Model / Timeout       │ │
│ │ Ollama failed   │  │ [Advanced generation parameters ▸] │ │
│ └─────────────────┘  │ [Save] [Test connection]            │ │
│                      │                                     │ │
│                      │ Test result: MODEL_NOT_FOUND        │ │
│                      │ Target: ... Model: ...              │ │
│                      │ Try: load model / verify alias      │ │
│                      └─────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ Local models: [Downloaded] [Loaded] [API available] [Search] │
└───────────────────────────────────────────────────────────────┘
```

## 6. Run Logs

### 页面目标

为失败诊断和审计提供完整信息，但不干扰普通写作。

### 主要组件

- RunFilterBar
- RunStepList
- ModelCallList
- RawPayloadViewer
- JsonErrorCard
- CopyDiagnosticsButton

### 用户操作

- 按状态、章节、日期筛选。
- 展开 step。
- 查看 prompt、response、parsed JSON、raw response。
- 复制诊断信息。
- 跳转模型或 Prompt 修复入口。

### API

- 当前单个 run detail 已包含全部日志。
- 项目级 list/filter/pagination 需要后端 API。

### Wireframe

```text
┌ Runs / Logs ──────────────────────────────────────────────────┐
│ Status [Failed ▼] Chapter [All ▼] Date [Today ▼] [Search]   │
├──────────────────────┬────────────────────────────────────────┤
│ Runs                 │ Run 48d25...                           │
│ FAILED Ch.8 10:30    │ Error: JSON_PARSE_ERROR                │
│ WAITING Ch.9 10:22   │ Step 4 CHECK_CONTINUITY · failed       │
│ APPROVED Ch.7 09:50  │                                        │
│                      │ Steps                                  │
│                      │ ✓ LOAD_PROJECT  3ms                    │
│                      │ ✓ ASSEMBLE_CONTEXT 5ms                 │
│                      │ ✓ WRITE_DRAFT  11ms                    │
│                      │ ✕ CHECK_CONTINUITY  JSON_PARSE_ERROR   │
│                      │                                        │
│                      │ Model call: continuity_checker         │
│                      │ [Prompt] [Response] [Parsed] [Raw]     │
│                      │ Response: {"passed": true, ...         │
│                      │ [Copy diagnostics] [Open Prompt]       │
└──────────────────────┴────────────────────────────────────────┘
```

## 7. 交互一致性

所有页面统一使用：

- `running`：蓝色/动态点。
- `waiting`：琥珀色，表示需要人。
- `approved`：绿色。
- `rejected`：中性灰红。
- `failed`：红色。

颜色必须同时配文字和图标，不能只依赖颜色表达状态。
