# AI Next Tasks

This file preserves the requested historical MVP 2 gates and marks their current status. The actual
next product task is MVP 3 Phase 4 Reverse Story Engineering P0.

# P0 Must Fix Before MVP 2

## Task: Human approve / reject / revise APIs

Status: **Done**

Goal:

Close the human gate without overwriting official content before approval.

Files likely involved:

- `services/api/app/routers/loop_runs.py`
- `services/api/app/services/loop_approval.py`
- `services/api/tests/test_loop_stability.py`

Do not modify:

- `services/api/app/routers/chapters.py::generate_chapter()`
- existing ChapterVersion rows

Acceptance criteria:

- approve updates `Chapter.content`;
- reject does not;
- revise creates a new immutable version;
- old versions remain.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py -q
```

Rollback plan:

Revert only approval route/service changes. Do not delete decision logs or versions from a populated
database.

Evidence:

- `services/api/app/services/loop_approval.py`
- `docs/08_mvp_1_1_stability_patch_report.md`

## Task: Database-level active-run concurrency protection

Status: **Done**

Goal:

Guarantee one active child Loop per chapter and one active MultiChapterRun per novel.

Files likely involved:

- `services/api/app/models/loop_entities.py`
- `services/api/app/models/auto_entities.py`
- `services/api/migrations/versions/0f19e48aa920_mvp_1_1_stability_fields_and_active_run_.py`
- `services/api/migrations/versions/f3a421d91870_mvp3_phase3_multi_chapter_pipeline.py`

Do not modify:

- unique indexes without a migration and concurrency tests

Acceptance criteria:

- competing inserts produce one success and one conflict;
- API converts IntegrityError to HTTP 409.

Verification commands:

```bash
cd services/api
.venv/bin/pytest \
  tests/test_loop_stability.py::test_database_unique_active_slot_blocks_concurrent_runs \
  tests/test_mvp3_multi_chapter.py::test_only_one_active_multi_chapter_run_per_novel -q
```

Rollback plan:

Restore the pre-migration database backup. Do not drop the indexes from a live database without
stopping the API.

## Task: Alembic migration baseline

Status: **Done, with a stale repository database warning**

Goal:

Provide an auditable migration chain.

Files likely involved:

- `services/api/alembic.ini`
- `services/api/migrations/versions/`

Do not modify:

- existing revision IDs or `down_revision` links

Acceptance criteria:

- fresh database upgrades to `f3a421d91870`;
- required tables and indexes exist;
- downgrade is tested only on disposable databases.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_alembic_baseline_and_stability_upgrade -q
.venv/bin/alembic heads
```

Rollback plan:

Use a timestamped database backup. Never rely on downgrade alone for a user database.

Warning:

`data/novel_local_ai.db` was observed at `0f19e48aa920`; the deployed database is at
`f3a421d91870`. See `docs/AI_CURRENT_STATUS.md`.

# P1 Stability Tests

## Task: EMPTY_CONTENT E2E

Status: **Done**

Goal:

Empty Writer output must fail without creating ChapterVersion.

Files likely involved:

- `services/api/app/services/draft_text_guard.py`
- `services/api/tests/test_loop_stability.py`

Do not modify:

- failure code semantics without updating UI and tests

Acceptance criteria:

- run fails with `EMPTY_CONTENT`;
- ModelCall and RunStep contain the error;
- no ChapterVersion is created.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_empty_draft_fails_without_chapter_version -q
```

Rollback plan:

Revert only the guard/test change. Never replace failure with an empty draft.

## Task: SCHEMA_VALIDATION_ERROR E2E

Status: **Done**

Goal:

Invalid structured Checker fields must fail explicitly.

Files likely involved:

- `services/api/app/services/json_guard.py`
- `services/api/app/agents/base.py`
- `services/api/tests/test_loop_stability.py`

Do not modify:

- Pydantic validation into permissive dict acceptance

Acceptance criteria:

- error code is `SCHEMA_VALIDATION_ERROR`;
- run, step and model call all retain the failure.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_schema_validation_error_fails_run_and_model_call -q
```

Rollback plan:

Revert schema additions if necessary; never silently coerce invalid severity or issue types.

## Task: MODEL_TIMEOUT / provider error E2E

Status: **Partially done**

Goal:

Classify timeout and provider HTTP failures with actionable logs.

Files likely involved:

- `services/api/app/agents/base.py`
- `services/api/app/services/provider_recovery.py`
- `services/api/tests/test_loop_stability.py`

Do not modify:

- error propagation to RunStep and ModelCall

Acceptance criteria:

- timeout is `MODEL_TIMEOUT`;
- HTTP/provider failure is `PROVIDER_ERROR` or `PROVIDER_UNAVAILABLE`;
- no silent success.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_model_timeout_is_logged_and_fails_run -q
```

Remaining:

Add a focused non-timeout provider HTTP failure test.

Rollback plan:

Keep the previous error classification and raw response. Do not collapse every provider failure into
`LOOP_EXECUTION_ERROR`.

## Task: Real local model manual acceptance

Status: **Done for one LM Studio model; repeat for other providers**

Goal:

Verify behavior that mock providers cannot prove.

Files likely involved:

- no code required;
- results belong in a new report under `docs/`.

Do not modify:

- production data without backup

Acceptance criteria:

- stream or final Writer output creates ChapterVersion;
- Checker returns Pydantic-valid JSON;
- manual or auto policy reaches the expected terminal state;
- logs and content safety are confirmed.

Verification commands:

Use the curl and UI steps in `docs/AI_RUN_AND_TEST_GUIDE.md`.

Evidence:

- `docs/19_writer_streaming_and_recovery_report.md`
- `docs/29_auto_revision_loop_fix_report.md`

Remaining:

Test Ollama, KoboldCpp and text-generation-webui explicitly before claiming them production-verified.

Rollback plan:

Stop the run, restore a pre-run database backup if test data must be removed, and retain failed logs
until diagnosis is complete.

## Task: Log sensitive-information cleanup strategy

Status: **Not implemented**

Goal:

Define retention, redaction and export behavior for full prompts, responses and provider payloads.

Files likely involved:

- `services/api/app/services/run_logger.py`
- `services/api/app/models/loop_entities.py`
- a new migration only if fields are added
- `apps/web/src/features/runs/RunDetailPage.tsx`

Do not modify:

- audit completeness without a documented replacement;
- existing logs destructively by default.

Acceptance criteria:

- API keys are never logged;
- users can distinguish local manuscript logs from diagnostic metadata;
- retention is opt-in and auditable;
- tests cover redaction.

Verification commands:

```bash
cd services/api
.venv/bin/pytest -q
cd ../../apps/web
npm run build
```

Rollback plan:

Feature flag new cleanup behavior. Preserve original records until the user explicitly chooses cleanup.

# P2 Frontend MVP 2

## Task: Loop Run start button

Status: **Done**

Goal:

Start manual or automatic runs from the chapter workspace.

Files likely involved:

- `apps/web/src/features/chapters/ChapterWorkspaceV2.tsx`

Do not modify:

- legacy Advanced workspace behavior

Acceptance criteria:

- provider, mode, count, revision rounds and references are submitted correctly.

Verification commands:

```bash
cd apps/web
npm run build
```

Rollback plan:

Revert the new workspace component only; retain backend APIs.

## Task: State timeline

Status: **Done**

Goal:

Display persisted RunStep order and status.

Files likely involved:

- `apps/web/src/features/runs/RunStateTimeline.tsx`

Do not modify:

- backend state names without a coordinated migration/UI update

Acceptance criteria:

- completed, failed, paused and current states are distinguishable.

Verification commands:

```bash
cd apps/web
npm run build
```

Rollback plan:

Hide the timeline component without changing RunStep persistence.

## Task: RunStep and ModelCall panels

Status: **Done in Run Detail, not paginated**

Goal:

Expose step inputs/outputs and model diagnostics.

Files likely involved:

- `apps/web/src/features/runs/RunDetailPage.tsx`
- `services/api/app/routers/loop_runs.py`

Do not modify:

- RunLogger persistence

Acceptance criteria:

- prompt, response, parsed result, raw payload, tokens, duration and errors are visible.

Verification commands:

```bash
cd apps/web
npm run build
```

Rollback plan:

Collapse or hide the panel. Do not delete logs.

## Task: ChapterVersion preview

Status: **Done**

Goal:

Allow users to inspect immutable versions.

Files likely involved:

- `apps/web/src/features/runs/VersionPreview.tsx`
- `services/api/app/routers/loop_runs.py::list_chapter_versions()`

Do not modify:

- immutable version rows

Acceptance criteria:

- version number, kind and content are shown;
- restore warns and creates a backup.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_mvp3_multi_chapter.py::test_restore_version_backs_up_current_content_and_writes_audit -q
cd ../../apps/web
npm run build
```

Rollback plan:

Remove the restore button first; keep the read-only version API.

## Task: Continuity Report display

Status: **Done**

Goal:

Display severity, evidence, suggested fixes and automatic handling.

Files likely involved:

- `apps/web/src/features/runs/ContinuityReportPanel.tsx`

Do not modify:

- checker schema without backend tests

Acceptance criteria:

- blocker and major are visibly distinct;
- auto-revision status is explained.

Verification commands:

```bash
cd apps/web
npm run build
```

Rollback plan:

Fall back to read-only JSON display without altering stored reports.

## Task: Approve / Reject / Revise operations

Status: **Done**

Goal:

Complete the human review loop from the UI.

Files likely involved:

- `apps/web/src/features/runs/RunDecisionBar.tsx`
- `apps/web/src/features/runs/RunDetailPage.tsx`

Do not modify:

- backend content-safety rules

Acceptance criteria:

- actions are enabled only at WAIT_HUMAN_APPROVAL;
- user feedback is sent;
- state refreshes after action.

Verification commands:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py -q
cd ../../apps/web
npm run build
```

Rollback plan:

Disable action buttons and leave the backend routes intact.

## Task: Version Diff

Status: **Not implemented**

Goal:

Compare draft, revision, approved and official content without loading unrelated logs.

Files likely involved:

- new `apps/web/src/features/runs/VersionDiff.tsx`
- optional read-only diff API under `services/api/app/routers/loop_runs.py`

Do not modify:

- ChapterVersion content;
- approval semantics.

Acceptance criteria:

- select two versions;
- line or block diff handles long Chinese text;
- no version mutation;
- build passes.

Verification commands:

```bash
cd services/api
.venv/bin/pytest -q
cd ../../apps/web
npm run build
```

Rollback plan:

Remove the diff component and retain existing VersionPreview.

# P3 Later

## Task: Reverse Story Engineering P0

Status: **P0 实现（2026-06-13）**。已实现：(a) Forward 前置物料抽取（想法→框架/人物/世界规则/章节计划→staging→接受落库）+ 章节提交后角色状态推进（→CanonState），见 `docs/30_story_engineering_report.md`；(b) **拆解参考小说** 10 维度（人物/世界/时间线/情节/定位/结构/伏笔/主题/视角/文风）+ **整本异步分块 Map-Reduce** + **仿写新作**，候选落库到 Character/WorldRule/TimelineEvent/PlotThread/Foreshadowing/Novel，见 `docs/31_reverse_story_engineering_report.md`。新增表 `deconstruction_runs` + 迁移 `a1b2c3d4e5f6`（additive）。旧接口与全部测试不破（59 passed）。剩余：拆解任务暂停/恢复、模型级 reduce、独立前端管理页。下面是原始 P0 设计记录。

Goal:

Extract staged story framework, character, world-rule and next-chapter-plan candidates from approved
chapters without writing directly to Canon or project records.

Files likely involved:

- new `services/api/app/models/extraction_entities.py`
- new `services/api/app/schemas/extraction.py`
- new `services/api/app/routers/extractions.py`
- new `services/api/app/services/reverse_story_engineering.py`
- new prompts under `services/api/app/prompts/`
- new migration and tests
- later, a small project Overview entry

Do not modify:

- `services/api/app/routers/chapters.py`
- `services/api/app/pipelines/chapter_pipeline.py`
- existing ChapterVersion rows
- CanonState automatically

Acceptance criteria:

- only approved/committed chapter versions are valid sources;
- every candidate has source chapter/version, evidence, confidence and staged status;
- JSON output uses Pydantic validation;
- accept/reject is explicit;
- conflict candidates do not auto-apply;
- old APIs and 38 existing tests still pass.

Verification commands:

```bash
cd services/api
.venv/bin/pytest -q
.venv/bin/pytest tests/test_reverse_story_engineering.py -q
cd ../../apps/web
npm run build
```

Rollback plan:

Keep the migration additive. Remove route registration and new UI entry; preserve staging tables if
they contain user-reviewed data.

## Task: Persistent structured Story Memory

Status: **Not implemented beyond chapter summary**

Goal:

Add staged character, timeline, hook and world-rule updates with source evidence.

Files likely involved:

- `services/api/app/models/auto_entities.py` or new memory entities
- `services/api/app/services/story_memory.py`
- new migrations, APIs and tests

Do not modify:

- Canon directly from raw model output

Acceptance criteria:

- each record has evidence;
- conflict handling is explicit;
- acceptance policy is testable;
- rebuild is idempotent or append-only.

Verification commands:

```bash
cd services/api
.venv/bin/pytest -q
```

Rollback plan:

Disable application of staged records; retain evidence for audit.

## Task: Durable queue and event delivery

Status: **Later**

Goal:

Improve crash recovery and reduce polling without adding infrastructure prematurely.

Files likely involved:

- `services/api/app/workflow/runner.py`
- `services/api/app/services/multi_chapter.py`
- new event endpoints
- `apps/web/src/features/runs/RunDetailPage.tsx`

Do not modify:

- state persistence semantics;
- SQLite support.

Acceptance criteria:

- browser reconnect recovers state;
- backend restart behavior is deterministic;
- no duplicate model calls;
- tests cover interruption.

Verification commands:

```bash
cd services/api
.venv/bin/pytest -q
cd ../../apps/web
npm run build
```

Rollback plan:

Keep polling as fallback and gate new event delivery behind a feature flag.

## Task: RAG / GraphRAG

Status: **Not implemented; defer**

Goal:

Add retrieval only after structured memory and evidence workflows are stable.

Files likely involved:

- new isolated retrieval package and migrations

Do not modify:

- Context Builder to load all chapter full text;
- core Loop behavior during first integration.

Acceptance criteria:

- retrieval has token budgets and provenance;
- feature can be disabled;
- no mandatory cloud dependency.

Verification commands:

Run the full backend suite, build the frontend and add retrieval-specific tests.

Rollback plan:

Disable retrieval and fall back to summaries, current state and explicit Reference Packs.
