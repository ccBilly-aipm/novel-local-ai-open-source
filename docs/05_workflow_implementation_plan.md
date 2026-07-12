# Loop Agent 代码级工作流实施计划

## 1. 实施原则

1. 不替换现有 `/api/chapters/{id}/generate` 行为。
2. 新增 `/api/projects/{project_id}/chapters/{chapter_id}/run` 作为实验入口。
3. 先使用现有 SQLite 和 Provider Adapter。
4. 新 Loop 表通过 Alembic migration 增加；在引入 Alembic 前不修改生产数据库。
5. 每个状态迁移先持久化，再执行下一步。
6. 所有模型调用通过统一 `call_agent()`。

## 2. 推荐核心类

### NovelLoopRunner

```python
class NovelLoopRunner:
    def run(self, run_id: str) -> None: ...
    def resume(self, run_id: str) -> None: ...
    def cancel(self, run_id: str) -> None: ...
    def transition(self, run_id: str, expected_state: str, next_state: str) -> None: ...
```

负责读取持久状态、调用当前 step handler、判断停止条件和迁移状态。它不直接拼 Prompt。

### ChapterRunContext

```python
class ChapterRunContext(BaseModel):
    run_id: str
    project_id: str
    novel_id: str
    chapter_id: str
    provider_id: str
    state: LoopState
    revision_round: int
    plan: ChapterPlan | None
    assembled_context: AssembledContext | None
    current_version_id: str | None
    check_report_ids: list[str]
    cancel_requested: bool
```

### PromptRegistry

```python
class PromptRegistry:
    def get(self, name: str, version: int | None = None) -> PromptSpec: ...
    def render(self, name: str, payload: dict) -> RenderedPrompt: ...
```

PromptRegistry 应兼容现有 `PromptTemplate`，但新 Agent 必须绑定 schema version。

### ModelClient

```python
class ModelClient:
    def call(
        self,
        provider_id: str,
        prompt: RenderedPrompt,
        options: dict,
        timeout_seconds: int,
    ) -> RawModelResult: ...
```

内部复用 `services/api/app/providers/adapters.py`。后续可增加 cancel token 和 streaming。

### JsonGuard

```python
class JsonGuard:
    def parse_and_validate(self, raw: str, schema: type[BaseModel]) -> BaseModel: ...
    def repair_once(self, raw: str, errors: list[dict], schema_json: dict) -> str: ...
```

不得使用当前 `parse_json_response(..., fallback={})` 的静默策略。

### StateStore

```python
class StateStore:
    def load_snapshot(self, novel_id: str, chapter_id: str) -> StateSnapshot: ...
    def stage_update(self, run_id: str, update: StateUpdate) -> str: ...
    def validate_staged_update(self, staging_id: str) -> ValidationReport: ...
    def commit_staged_update(self, staging_id: str) -> None: ...
```

### ProjectStore

负责读取 Project、Novel、ChapterPlan、Story Bible 和 workflow config。避免 Runner 直接写 SQLAlchemy 查询。

### RunLogger

```python
class RunLogger:
    def start_step(self, run_id: str, state: LoopState, input_payload: dict) -> str: ...
    def record_model_call(self, step_id: str, call: ModelCallRecord) -> str: ...
    def complete_step(self, step_id: str, output_payload: dict) -> None: ...
    def fail_step(self, step_id: str, error: RunError) -> None: ...
    def event(self, run_id: str, event_type: str, payload: dict) -> None: ...
```

### ChapterVersionManager

```python
class ChapterVersionManager:
    def append(self, chapter_id: str, content: str, kind: str, parent_id: str | None) -> ChapterVersion: ...
    def diff(self, old_version_id: str, new_version_id: str) -> str: ...
    def approve(self, version_id: str) -> None: ...
```

### HumanGate

```python
class HumanGate:
    def approve(self, run_id: str, version_id: str, note: str = "") -> None: ...
    def reject(self, run_id: str, feedback: str) -> None: ...
```

## 3. 推荐状态 handler

| State | Handler | 产物 |
|---|---|---|
| INIT | `initialize_run()` | run policy snapshot |
| LOAD_PROJECT | `load_project()` | validated project snapshot |
| PLAN_CHAPTER | `plan_chapter()` | ChapterPlan |
| ASSEMBLE_CONTEXT | `assemble_context()` | AssembledContext |
| WRITE_DRAFT | `write_draft()` | draft ChapterVersion |
| CHECK_CONTINUITY | `check_continuity()` | CheckReport |
| CHECK_CHARACTER | `check_character()` | CheckReport |
| CHECK_PLOT_RHYTHM | `check_plot_rhythm()` | CheckReport |
| REVISE_DRAFT | `revise_draft()` | revision ChapterVersion |
| RECHECK | `prepare_recheck()` | 清理当前轮报告引用 |
| WAIT_HUMAN_APPROVAL | 无后台 handler | durable gate |
| APPROVED | `mark_approved()` | approved version |
| UPDATE_STATE | `update_project_state()` | staged + committed update |
| REFLECT | `reflect()` | ReflectionRecord |
| DONE | `finish_run()` | final metrics |
| FAILED | `fail_run()` | error summary |

## 4. 关键函数伪代码

### run_chapter_loop

```python
def run_chapter_loop(project_id, chapter_id, provider_id, request_id):
    existing = run_store.find_by_request_id(request_id)
    if existing:
        return existing

    with chapter_lock(chapter_id):
        if run_store.has_active_run(chapter_id):
            raise Conflict("chapter already has an active run")

        run = run_store.create(
            project_id=project_id,
            chapter_id=chapter_id,
            provider_id=provider_id,
            state="INIT",
            max_revision_rounds=3,
        )
        queue.put(run.id)
        return run
```

### Runner 主循环

```python
def process_run(run_id):
    while True:
        run = run_store.get(run_id)

        if run.cancel_requested:
            run_store.fail(run_id, code="USER_CANCELLED")
            return

        if run.state in {"WAIT_HUMAN_APPROVAL", "DONE", "FAILED"}:
            return

        handler = handlers[run.state]
        step_id = logger.start_step(run_id, run.state, handler.input_snapshot(run))

        try:
            next_state = handler.execute(run)
            logger.complete_step(step_id, {"next_state": next_state})
            run_store.transition(run_id, expected=run.state, target=next_state)
        except RunError as error:
            logger.fail_step(step_id, error)
            run_store.fail(run_id, error.code, error.message)
            return
```

### assemble_context

```python
def assemble_context(project_id, chapter_id):
    plan = project_store.get_chapter_plan(chapter_id)
    snapshot = state_store.load_snapshot(project_id, chapter_id)

    sections = [
        required(plan.chapter_goal, priority=100),
        required(plan.required_events, priority=100),
        required(snapshot.relevant_character_states, priority=95),
        required(snapshot.previous_chapter_summary, priority=95),
        optional(snapshot.recent_summaries, priority=80),
        optional(snapshot.relevant_world_rules, priority=75),
        optional(snapshot.open_hooks, priority=70),
        optional(snapshot.story_outline, priority=40),
        optional(snapshot.style_examples, priority=20),
    ]

    result = deterministic_budgeter.fit(sections, token_budget)
    if result.required_sections_overflow:
        result = call_agent("context_assembler_prompt", result.to_payload())

    validate_context_ids(result, snapshot)
    return result
```

与当前 Context Builder 的区别：按 item 和优先级裁剪，不把近三章先拼成一个只能保留前缀的大字符串。

### call_agent

```python
def call_agent(agent_name, input_payload, run_id, step_id):
    spec = prompt_registry.get(agent_name)
    validated_input = spec.input_model.model_validate(input_payload)
    rendered = prompt_registry.render(spec, validated_input)

    for attempt in range(1, MAX_MODEL_RETRIES + 2):
        call_id = logger.start_model_call(
            run_id=run_id,
            step_id=step_id,
            prompt_name=spec.name,
            prompt_version=spec.version,
            schema_version=spec.schema_version,
            input_payload=validated_input.model_dump(),
            rendered_prompt=rendered.text,
            attempt=attempt,
        )
        try:
            raw = model_client.call(rendered, timeout=policy.timeout_for(agent_name))
            parsed = json_guard.parse_and_validate(raw.text, spec.output_model)
            logger.complete_model_call(call_id, raw, parsed)
            return parsed
        except JsonValidationError as error:
            repaired = json_guard.repair_once(raw.text, error.errors, spec.output_schema)
            parsed = json_guard.parse_and_validate(repaired, spec.output_model)
            logger.complete_model_call(call_id, raw, parsed, repaired_text=repaired)
            return parsed
        except RetryableModelError as error:
            logger.retry_model_call(call_id, error)
            if attempt > MAX_MODEL_RETRIES:
                raise
            backoff(attempt)
```

### validate_json

```python
def validate_json(output, schema):
    if not output.strip():
        raise EmptyOutput()
    cleaned = strip_json_fence(output)
    try:
        value = json.loads(cleaned)
    except JSONDecodeError as error:
        raise JsonParseError(error)
    return schema.model_validate(value)
```

### write_draft

```python
def write_draft(context):
    result = call_agent("draft_writer", context.writer_payload())
    if not result.draft_markdown.strip():
        raise EmptyContent()
    if result.chapter_id != context.chapter_id:
        raise ReferenceMismatch()
    return version_manager.append(
        chapter_id=context.chapter_id,
        content=result.draft_markdown,
        kind="draft",
        parent_id=None,
    )
```

### run_checks

```python
def run_checks(run, version):
    reports = []
    reports.append(call_agent("continuity_checker", build_continuity_payload(run, version)))
    reports.append(call_agent("character_consistency_checker", build_character_payload(run, version)))
    reports.append(call_agent("plot_rhythm_checker", build_rhythm_payload(run, version)))
    return report_store.save_all(run.id, version.id, reports)
```

MVP 1 建议串行，避免本地模型同时加载/推理。以后不同 Provider 才考虑并行。

### revise_until_passed

```python
def decide_after_checks(run, reports):
    if any(report.has_blocker for report in reports):
        return "WAIT_HUMAN_APPROVAL"
    if all(report.passed for report in reports):
        return "WAIT_HUMAN_APPROVAL"
    if run.revision_round >= run.max_revision_rounds:
        raise RevisionLimitReached()
    return "REVISE_DRAFT"


def revise_until_passed(run):
    issues = report_store.actionable_issues(run.id, run.current_version_id)
    result = call_agent("revision_writer", build_revision_payload(run, issues))
    version = version_manager.append(
        chapter_id=run.chapter_id,
        content=result.revised_markdown,
        kind="revision",
        parent_id=run.current_version_id,
    )
    run_store.increment_revision_round(run.id, version.id)
    return "RECHECK"
```

### update_project_state

```python
def update_project_state(run):
    approved = version_manager.get_approved(run.chapter_id)
    extracted = call_agent("state_updater", build_state_payload(run, approved))
    staging_id = state_store.stage_update(run.id, extracted)
    validation = state_store.validate_staged_update(staging_id)

    if not validation.passed:
        raise StateValidationError(validation.errors)

    with transaction():
        state_store.commit_staged_update(staging_id)
        chapter_store.publish_content(run.chapter_id, approved.content_markdown)
        chapter_store.update_summary(run.chapter_id, extracted)
```

### save_run_log

日志不应依赖手工调用一个“最后保存”函数。每个 step/model call 都增量写入；`save_run_log()` 只生成最终聚合摘要和文件工件。

## 5. 错误处理策略

| 场景 | 错误码 | 自动处理 | 最终行为 |
|---|---|---|---|
| 模型 timeout | `MODEL_TIMEOUT` | 同 Provider 最多重试 2 次 | 失败或按 policy fallback |
| HTTP 429/503/连接重置 | `MODEL_TRANSIENT` | 指数退避重试 | 重试耗尽后失败 |
| JSON 解析失败 | `JSON_PARSE_ERROR` | 清理 + 一次 repair | step failed |
| 字段缺失/类型错误 | `SCHEMA_VALIDATION_ERROR` | 一次 repair | step failed |
| 正文为空 | `EMPTY_CONTENT` | 视为 retryable 一次 | 失败，不创建版本 |
| 检查报告互相冲突 | `CHECKER_DISAGREEMENT` | 代码以最高 severity 为准 | 进入 Human Gate |
| 修订 3 轮未通过 | `REVISION_LIMIT` | 不再调用模型 | FAILED，允许人工接管 |
| 状态写入失败 | `STATE_COMMIT_ERROR` | 事务 rollback | FAILED，可从 APPROVED 重试 |
| 文件锁/并发写入 | `CHAPTER_LOCKED` | 不排队重复 run | HTTP 409 |
| 前端断开 | 无错误 | 后端继续到 gate/terminal | 用户重连查询 |
| 用户取消 | `USER_CANCELLED` | 设置 flag；请求返回后停止 | FAILED/CANCELLED |
| Provider 不支持参数 | `UNSUPPORTED_MODEL_OPTION` | 参数映射层过滤 | 过滤不了则失败 |
| 引用未知实体 ID | `UNKNOWN_ENTITY` | 不写入 | 停在 UPDATE_STATE 失败 |

### Fallback 策略

MVP 1 默认不自动切模型，避免不同模型造成不可复现变化。可选策略：

- Planner/checker 可 fallback 到项目配置的 secondary provider。
- Draft/Revision 默认不 fallback，除非用户显式开启。
- 每次 fallback 必须记录原 Provider、错误和新 Provider。

## 6. 日志与可观察性

每个 Chapter Loop 生成一个 `run_id`。

### ChapterLoopRun

- project_id、novel_id、chapter_id
- provider policy snapshot
- 当前 state
- revision round / max rounds
- current version
- cancel requested
- started/finished time
- final status/error

### RunStep

- step_id、run_id
- state/agent name
- input payload
- output payload
- started/finished time
- status/error code/error detail

### ModelCall

- prompt name/version/schema version
- provider/model
- 合并参数
- rendered prompt
- raw output
- repaired output
- parsed JSON
- validation errors
- retry attempt
- input/output token 或字符统计
- duration

### RunEvent

- state transition
- user approve/reject/cancel
- retry
- fallback
- version creation
- state commit

### 日志输出

1. SQLite 是查询主源。
2. Python `logging` 输出 JSON line 到终端/文件。
3. 可选生成 `data/projects/<id>/runs/<run_id>/manifest.json`。
4. 大文本可先继续放 SQLite；数据量上升后改为 artifact path + hash。

## 7. 前端改造建议

| 页面 | 页面目标 | 主要组件 | API | 状态/操作 |
|---|---|---|---|---|
| 项目列表页 | 创建、打开项目 | ProjectCard、CreateProject | `/projects` | 项目状态、最近 run |
| 故事框架页 | 编辑/生成结构化框架 | FrameworkEditor、RiskNotes | story-framework API | draft/approved |
| 人物管理页 | 人物模型和当前状态 | CharacterProfileEditor、StateHistory | characters API | 版本、关系、状态 |
| 时间线页 | 查看事件和冲突 | TimelineTable、ConflictBadge | timeline API | planned/occurred |
| 章节计划页 | 编辑 ChapterPlan | ChapterPlanEditor、HookPicker | chapter plan API | valid/invalid |
| 章节运行页 | 启动和观察 Loop | StateTimeline、RunControls、DraftPreview | chapter run API | 当前 state、轮次、取消 |
| 检查报告页 | 查看三个 checker | IssueList、SeverityFilter | run reports API | passed/blocker |
| 版本对比页 | 比较草稿和修订 | DiffViewer、VersionSelector | versions API | approve/revert |
| 运行日志页 | 审计模型调用 | StepList、ModelCallDetail | run API | retry、错误 |
| 设置页 | Provider、Prompt、policy | ProviderForm、WorkflowPolicy | settings API | timeout、重试、轮次 |

### 章节运行页最小 UI

- 顶部：run 状态、模型、开始时间、取消。
- 左栏：状态机步骤列表。
- 中间：当前版本正文。
- 右栏：检查报告和 revision round。
- Gate 区：Approve、Reject with feedback、手工编辑后批准。

## 8. API 设计

沿用现有 REST 风格和 `/api` 前缀。

### 项目与框架

```text
POST /api/projects
GET  /api/projects
GET  /api/projects/{project_id}
POST /api/projects/{project_id}/story-framework
GET  /api/projects/{project_id}/story-framework
```

`POST story-framework` 可先创建异步 task，不能沿用当前同步 Creative route。

### 人物与时间线

```text
POST /api/projects/{project_id}/characters
GET  /api/projects/{project_id}/characters
POST /api/projects/{project_id}/timeline
GET  /api/projects/{project_id}/timeline
```

兼容期内部可代理到当前 novel-scoped API。

### 章节计划

```text
POST /api/projects/{project_id}/chapters/{chapter_id}/plan
GET  /api/projects/{project_id}/chapters/{chapter_id}/plan
PATCH /api/projects/{project_id}/chapters/{chapter_id}/plan
```

### Loop Run

```text
POST /api/projects/{project_id}/chapters/{chapter_id}/run
GET  /api/projects/{project_id}/runs/{run_id}
GET  /api/projects/{project_id}/runs/{run_id}/events
POST /api/projects/{project_id}/runs/{run_id}/cancel
POST /api/projects/{project_id}/runs/{run_id}/approve
POST /api/projects/{project_id}/runs/{run_id}/reject
POST /api/projects/{project_id}/runs/{run_id}/retry
```

创建请求示例：

```json
{
  "provider_id": "uuid",
  "request_id": "client-generated-uuid",
  "max_revision_rounds": 3,
  "context_budget": 12000,
  "require_human_approval": true
}
```

### Reports 与 Versions

```text
GET /api/projects/{project_id}/runs/{run_id}/reports
GET /api/projects/{project_id}/runs/{run_id}/model-calls
GET /api/projects/{project_id}/chapters/{chapter_id}/versions
GET /api/projects/{project_id}/chapters/{chapter_id}/versions/{version_id}
GET /api/projects/{project_id}/chapters/{chapter_id}/versions/{version_id}/diff?against=...
```

### Human Gate

Approve：

```json
{
  "version_id": "uuid",
  "note": "确认进入 Canon"
}
```

Reject：

```json
{
  "feedback": "第二场人物动机仍不成立",
  "action": "revise"
}
```

## 9. 数据库迁移建议

第一批新增表：

- `chapter_loop_runs`
- `run_steps`
- `model_calls`
- `chapter_versions`
- `check_reports`
- `state_update_staging`
- `reflection_records`

不要直接把所有 Canon JSON 拆表。MVP 1 可继续读取 `CanonState`，只新增 staging 和 version/run 表。

在新增表之前先引入 Alembic，并创建一份“当前 schema baseline”；否则部署副本与开发库容易漂移。

## 10. 测试计划

### 单元测试

- 状态合法迁移
- revision 上限
- JsonGuard 成功、repair、失败
- Context budget 优先级
- StateStore 未知 ID 拒绝
- ChapterVersion append/diff

### 集成测试

- Mock Provider 跑完整单章到 WAIT_HUMAN_APPROVAL
- 首次检查失败、修订后通过
- blocker 直接进入 gate
- approve 后正文和 Canon 更新
- backend restart 后恢复 active run
- duplicate request_id 不重复创建
- 同章并发返回 409

### 真实本地模型验收

使用当前已验证的 LM Studio `qwen3.6-27b-crack`：

1. 固定同一 ChapterPlan。
2. 跑一次 Draft + 三项 Checker。
3. 至少制造一个可修订 issue。
4. 完成一次 Revision + Recheck。
5. 人工批准。
6. 验证状态 staging 和最终写入。
