# AI Code Touch Map

## Safe to add

These areas are suitable for additive work when accompanied by tests:

- New documentation under `docs/`.
- New backend feature modules under `services/api/app/services/`.
- New isolated routers under `services/api/app/routers/`.
- New schemas under `services/api/app/schemas/`.
- New prompts under `services/api/app/prompts/`.
- New tests under `services/api/tests/`.
- New frontend feature components under `apps/web/src/features/`.
- New additive Alembic revisions under `services/api/migrations/versions/`.

For Reverse Story Engineering, prefer new extraction-specific files rather than expanding
`auto_entities.py` into an unrelated catch-all.

## Safe to modify carefully

### `services/api/app/routers/loop_runs.py`

Can change:

- additive read-only endpoints;
- recovery metadata;
- new decision diagnostics.

Risks:

- content writes;
- active-slot release;
- HTTP status compatibility;
- eager-loaded payload size.

Required tests:

- `test_loop_stability.py`
- `test_loop_runner.py`
- `test_mvp3_auto_pipeline.py`

### `services/api/app/workflow/`

Can change:

- explicit new states and guarded transitions.

Risks:

- loops that never terminate;
- skipped logs;
- duplicate model calls;
- unsafe auto commit.

Every new state must have:

- RunStep logging;
- a transition;
- terminal/error behavior;
- tests for success and failure.

### `services/api/app/agents/`

Can change:

- prompt variables;
- additional structured agents;
- bounded retries.

Risks:

- local model format instability;
- large prompts;
- error-code regressions.

Writer text should continue through DraftTextGuard. Structured outputs must continue through JsonGuard
and Pydantic.

### `services/api/app/services/json_guard.py`

Can change:

- conservative extraction and error detail.

Do not:

- return defaults on invalid JSON;
- coerce invalid schema into success.

Required tests:

- JSON_PARSE_ERROR;
- SCHEMA_VALIDATION_ERROR;
- valid fenced JSON.

### `services/api/app/services/run_logger.py`

Can change:

- additive fields;
- redaction hooks;
- pagination support.

Do not:

- omit model failure logs;
- remove raw diagnostics without a migration and retention policy.

### `services/api/app/services/version_manager.py`

Can change:

- additive version kinds;
- concurrency retry.

Do not:

- update existing ChapterVersion;
- create empty versions;
- reuse version numbers.

### `services/api/app/models/loop_entities.py`

Can change only with:

- a new Alembic migration;
- upgrade/downgrade tests;
- database backup instructions.

High-impact fields:

- `active_slot`
- `state`
- `status`
- `current_version_id`
- `approved_version_id`

### `services/api/app/schemas/loop.py`

Can change:

- additive optional response fields;
- validated request controls.

Coordinate any state or field rename with frontend types and tests.

### `services/api/app/providers/`

Can change:

- provider-specific protocol support;
- streaming compatibility;
- error classification.

Do not assume all OpenAI-compatible servers behave identically. Preserve non-stream fallback and
Provider raw logs.

### `apps/web/src/`

Can change:

- scoped feature components;
- clearer status and error messaging;
- new read-only pages;
- feature flags.

Current constraints:

- hash routing in `App.tsx`;
- no external component library;
- no global state library;
- TypeScript build is the only automated frontend verification.

## High risk, avoid unless necessary

### `services/api/app/routers/chapters.py`

Contains the old generation API. New Loop behavior must not be inserted into
`generate_chapter()` without explicit migration requirements.

### `services/api/app/pipelines/chapter_pipeline.py`

Legacy WritingTask behavior directly updates chapter content and summary. It is covered by
`services/api/tests/test_api.py`.

### `services/api/app/db.py`

Changes affect every process, test database and migration. In particular:

- `DATABASE_URL` is resolved at import time;
- SQLite pragmas are registered here;
- `create_tables()` is called at startup.

### `services/api/app/services/task_queue.py`

Legacy queue compatibility area. Do not merge it with Loop queues casually.

### `services/api/app/services/auto_pipeline.py`

Controls automatic revision and content writes. Any change can bypass safety thresholds.

### `services/api/app/services/multi_chapter.py`

Coordinates parent/child state and restart recovery. Avoid broad refactors without restart and
resume tests.

### `services/api/migrations/versions/`

Never edit an applied migration revision. Add a new revision.

### `data/`

Contains local SQLite data and backups. It is not a fixture directory. The repository database is
currently behind migration head.

## Do not modify without explicit instruction

- Existing user database records.
- Existing ChapterVersion content.
- Existing Alembic revision IDs or history.
- Deployed files under `~/Library/Application Support/NovelLocalAI/`.
- LaunchAgents under `~/Library/LaunchAgents/`.
- API keys or provider credentials.
- Historical RunStep and ModelCall logs.

## Path-by-path decision table

| Path | Classification | Notes |
|---|---|---|
| `services/api/app/routers/loop_runs.py` | Modify carefully | Core lifecycle and content decisions |
| `services/api/app/workflow/` | High risk | State machine and queue |
| `services/api/app/agents/` | Modify carefully | Model contracts and retries |
| `services/api/app/services/json_guard.py` | Modify carefully | Never silent-success invalid JSON |
| `services/api/app/services/run_logger.py` | Additive only | Audit and privacy |
| `services/api/app/services/version_manager.py` | High risk | Append-only guarantee |
| `services/api/app/models/loop_entities.py` | High risk | Requires migration |
| `services/api/app/schemas/loop.py` | Modify carefully | Coordinate frontend types |
| `services/api/app/routers/chapters.py` | Do not alter behavior | Legacy generate compatibility |
| `services/api/app/pipelines/chapter_pipeline.py` | Do not alter behavior | Legacy direct-write path |
| `services/api/app/providers/` | Modify carefully | Protocol differences |
| `apps/web/src/` | Scoped changes safe | Build after every change |
| `docs/` | Safe | Keep evidence and dates current |
| `data/` | Do not modify casually | User/database state |

## 故事地图后端（阶段 1，additive）

| File | Guidance | Reason |
|---|---|---|
| `services/api/app/services/story_map.py` | Additive only | 聚合读 + 提取管线 + 新 record_type 接受逻辑；不改旧 record_type 行为 |
| `services/api/app/routers/story_map.py` | Additive only | 独立路由：聚合读 / 三实体 CRUD / 提取 run |
| `services/api/app/schemas/story_map.py` | Additive only | 独立 schema，不动既有 *Out schema |
| `services/api/app/prompts/story_map_extraction.md` | Editable | 单章结构提取模板（注册键 `sm_extract`） |
| `services/api/app/models/auto_entities.py`（`StoryMapExtractRun`） | Requires migration | 提取进度表；改字段须新增 migration |
| `services/api/app/services/story_engineering.py` | Do not alter old branches | 仅新增 storymap 委派分支，旧接受行为不动 |

故事地图数据接口详见 `docs/32_story_map_backend_report.md`。候选的 list/accept/reject/restore
复用 story-engineering 接口（record_type=`staged_storymap_*`）。

## Mandatory invariant

The old endpoint:

```text
POST /api/chapters/{chapter_id}/generate
```

must continue to use the legacy WritingTask path until an explicit deprecation and migration plan is
approved. It must not be silently redirected to ChapterLoopRun.
