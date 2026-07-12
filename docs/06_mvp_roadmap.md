# 小说 Loop Agent 最小可行改造路线

## 总原则

- 每个阶段都保持现有章节生成 API 可用。
- 新能力使用独立路由、表和前端 feature flag。
- 每个阶段有数据库备份和可执行回滚。
- 不在一个 migration 中同时重构旧表和加入 Loop。

## MVP 0：只做审计，不改运行代码

### 目标

确认当前前端、后端、Prompt、模型调用、数据流、任务队列和风险，为后续改造建立代码证据。

### 修改文件

无现有运行文件修改。

### 新增文件

- `docs/01_current_architecture_audit.md`
- `docs/02_prompt_agent_audit.md`
- `docs/prompt_inventory.json`
- `docs/03_novel_loop_agent_architecture.md`
- `docs/04_novel_prompts_design.md`
- `docs/05_workflow_implementation_plan.md`
- `docs/06_mvp_roadmap.md`
- `backend/prompts/novel_prompts_draft.py`

### 验收标准

- 所有结论引用当前仓库路径。
- 明确不存在的模块。
- Prompt inventory 是合法 JSON。
- Prompt 草稿可通过 Python 语法检查。
- 现有 pytest 和前端 build 不受影响。

### 风险

设计文档可能与后续产品取舍变化。

### 回滚方案

删除本轮新增文件即可；不涉及数据库和运行行为。

### 当前状态

本次交付已完成 MVP 0。

## MVP 1：跑通单章 Loop，无复杂前端

### 目标

通过 API 跑通：

```text
LOAD_PROJECT
→ ASSEMBLE_CONTEXT
→ WRITE_DRAFT
→ CHECK_CONTINUITY
→ REVISE_DRAFT（最多一次或配置上限）
→ RECHECK
→ WAIT_HUMAN_APPROVAL
→ APPROVED
→ UPDATE_STATE
→ DONE
```

第一版可以先只启用 Continuity Checker，但状态接口必须为三个 Checker 保留位置。

### 修改文件

- `services/api/app/main.py`：注册新 router、启动 Loop worker。
- `services/api/app/providers/adapters.py`：只增加统一错误分类，保持行为兼容。
- `services/api/app/services/context_builder.py`：增加 typed item/priority API，保留旧函数。
- `services/api/pyproject.toml`：加入 Alembic；如使用 JSON Schema 库需评估是否必要。

### 新增文件

```text
services/api/app/routers/loop_runs.py
services/api/app/workflow/runner.py
services/api/app/workflow/states.py
services/api/app/workflow/policies.py
services/api/app/agents/base.py
services/api/app/agents/writer.py
services/api/app/agents/checkers.py
services/api/app/services/json_guard.py
services/api/app/services/version_manager.py
services/api/app/services/run_logger.py
services/api/app/models/loop_entities.py
services/api/app/schemas/loop.py
services/api/app/prompts/novel_loop/*.md
services/api/tests/test_loop_runner.py
alembic.ini
services/api/alembic/
```

### 验收标准

- 创建 run 返回 run_id。
- 同章不能同时创建两个 active run。
- 每个状态和模型调用都有持久日志。
- 初稿保存为 ChapterVersion，不覆盖当前正文。
- 检查报告通过 Pydantic schema。
- 修订轮次受代码限制。
- 后端重启后能继续 pending run 或明确标记 interrupted。
- 人工 approve 后才更新 `Chapter.content`。
- 现有章节 API 测试全部通过。

### 风险

- 本地模型 JSON 可靠性不足。
- 新旧任务队列同时存在时可能争用模型。
- Alembic baseline 与已有部署数据库不一致。

### 回滚方案

- 新 router 通过 feature flag 关闭。
- 停止 Loop worker。
- 回滚新增 migration，仅删除 Loop 新表。
- 旧 `WritingTask` 和章节 API 不受影响。

## MVP 2：加入前端运行页和日志页

### 目标

用户可在浏览器启动单章 Loop，观察状态机、检查报告、版本和错误，并执行 approve/reject/cancel。

### 修改文件

- `apps/web/src/App.tsx`：加入 Loop 页面入口或项目内 tab。
- `apps/web/src/components/WorkspaceShell.tsx`：加入“章节运行”。
- `apps/web/src/services/api.ts`：保留通用封装，可增加取消请求 helper。
- `apps/web/src/types.ts`：增加 Loop 类型。

### 新增文件

```text
apps/web/src/features/loop-runs/ChapterRunPage.tsx
apps/web/src/features/loop-runs/RunStateTimeline.tsx
apps/web/src/features/loop-runs/CheckReportPanel.tsx
apps/web/src/features/loop-runs/VersionDiff.tsx
apps/web/src/features/loop-runs/ModelCallLog.tsx
apps/web/src/features/loop-runs/api.ts
apps/web/src/features/loop-runs/types.ts
```

### 验收标准

- 页面刷新后可按 run_id 恢复。
- 显示当前 state、修订轮次、Provider 和耗时。
- 显示三个 Checker 的 issue 和 severity。
- 可比较初稿/修订版本。
- Approve/Reject 只能在正确状态执行。
- 前端断开不影响后端 run。
- 增加至少一组前端组件测试或 Playwright 冒烟测试。

### 风险

- 轮询频率过高。
- 大 Prompt/Response 直接渲染影响页面性能。
- diff 对中文长文可能卡顿。

### 回滚方案

移除新 tab 或关闭 feature flag；后端 Loop API 保留，旧 Workspace 不变。

## MVP 3：人物、时间线、伏笔状态更新

### 目标

approved 后结构化更新人物状态、关系、时间线、Hook 和 Canon，并支持 staging 预览。

### 修改文件

- `services/api/app/models/entities.py`：仅在 migration 方案确认后增加必要关系或保持旧表兼容。
- `services/api/app/routers/canon.py`：增加只读兼容映射，不破坏旧 PATCH。
- `services/api/app/services/context_builder.py`：从结构化状态读取。
- `apps/web/src/components/CharacterCards.tsx`：显示状态历史。
- `apps/web/src/components/Worldbuilding.tsx`：显示 Canon 引用。

### 新增文件

```text
services/api/app/services/state_store.py
services/api/app/agents/state_updater.py
services/api/app/models/state_entities.py
services/api/app/schemas/state.py
services/api/app/routers/timeline.py
services/api/app/routers/hooks.py
services/api/tests/test_state_store.py
apps/web/src/features/state/
```

### 验收标准

- 状态抽取必须通过 known ID 校验。
- 同一章节重复 approve 不重复添加事件。
- Hook 支持 planted/resolved。
- 时间线冲突能阻止状态提交。
- 所有更新可追溯到 chapter/version/run。
- 旧 CanonState 仍可被现有 Workspace 读取。

### 风险

- 旧 JSON Canon 与新表双写不一致。
- 模型把推测当事实。
- 状态粒度设计过细导致上下文膨胀。

### 回滚方案

新状态表为 append-only；关闭新读取路径，恢复使用旧 CanonState。保留已写数据供审计。

## MVP 4：多章连续循环

### 目标

在每章人工批准后自动准备下一章，支持批量计划但不绕过 Human Gate。

### 修改文件

- `workflow/runner.py`：增加 parent run / batch run。
- `workflow/policies.py`：增加章数、停止和资源策略。
- Loop API：新增 batch endpoint。
- 前端运行页：增加章节队列。

### 新增文件

```text
services/api/app/workflow/batch_runner.py
services/api/app/models/batch_entities.py
services/api/app/schemas/batch.py
services/api/tests/test_multi_chapter_loop.py
apps/web/src/features/loop-runs/ChapterQueue.tsx
```

### 验收标准

- 可选择连续运行 N 章。
- 每章仍停在 Human Gate。
- 下一章只读取已批准状态。
- 某章失败后后续章不启动。
- 用户取消后不创建新章节任务。
- 进程重启可恢复批次位置。

### 风险

- 本地模型长时间占用资源。
- 状态错误在多章中放大。
- 用户误以为系统可以无人监督无限写作。

### 回滚方案

关闭 batch endpoint；单章 Runner 不变。已创建的单章 run 可继续单独处理。

## MVP 5：风格学习和长期记忆

### 目标

从 approved 章节与人工编辑差异中提炼可确认的风格规则和长期记忆，按需检索到上下文。

### 修改文件

- Context Assembler：增加 memory candidate 检索。
- Reflection Agent：支持跨 run 聚合。
- Prompt Manager：显示规则候选和批准状态。

### 新增文件

```text
services/api/app/services/memory_store.py
services/api/app/services/style_profile.py
services/api/app/agents/reflection.py
services/api/app/models/memory_entities.py
services/api/app/routers/memory.py
services/api/tests/test_memory_retrieval.py
apps/web/src/features/memory/
```

### 验收标准

- 只从 approved 内容和人工修改学习。
- 每条规则有来源章节、diff 和置信度。
- 用户可批准、禁用、删除规则。
- Context Assembler 只取与当前章相关的少量记忆。
- 关闭长期记忆后系统行为回到 MVP 4。

### 风险

- 错误规则长期污染文风。
- 记忆检索带来额外上下文和模型调用。
- 过度拟合少量章节。

### 回滚方案

长期记忆默认 feature flag 关闭；停用检索即可，不删除历史记录。

## 推荐下一开发任务

下一次应只实施 MVP 1 的基础设施切片：

1. 引入 Alembic baseline。
2. 新增 `ChapterLoopRun`、`RunStep`、`ChapterVersion`、`ModelCall` 四张表。
3. 实现不调用模型的状态机骨架和合法迁移测试。
4. 接入现有 Context Builder 和 ModelAdapter。
5. 用 Mock Provider 跑到 `WAIT_HUMAN_APPROVAL`。

在这个切片通过测试前，不开始前端复杂页面和多章自动循环。
