# AI Current Status

Last verified: **2026-06-13**

## Current stage

**MVP 3 Phase 3 + multi-chapter fallback and automatic revision-loop fixes.**

The latest implementation reports are:

- `docs/26_mvp3_auto_chapter_pipeline_report.md`
- `docs/27_mvp3_phase3_multi_chapter_report.md`
- `docs/28_multi_chapter_fallback_patch_report.md`
- `docs/29_auto_revision_loop_fix_report.md`

Earlier `docs/01` to `docs/08` describe historical states. Their old “not implemented” statements
must be checked against current code before use.

## Implemented

| Capability | Current evidence |
|---|---|
| Project, novel, chapter, character, world-rule CRUD | `services/api/app/routers/`, `services/api/tests/test_api.py` |
| Legacy direct chapter generation | `services/api/app/routers/chapters.py::generate_chapter()` |
| Single-chapter Loop | `services/api/app/routers/loop_runs.py::create_loop_run()` |
| Human approve/reject/revise | `services/api/app/services/loop_approval.py` |
| Immutable ChapterVersion | `services/api/app/models/loop_entities.py::ChapterVersion` |
| Database active-run guard | partial unique index in `ChapterLoopRun.__table_args__` |
| Draft text guard and retry | `services/api/app/services/draft_text_guard.py`, `services/api/app/agents/base.py` |
| Pydantic JSON validation and repair | `services/api/app/services/json_guard.py`, structured agent path in `services/api/app/agents/base.py` |
| Writer streaming and polling preview | provider adapters plus `ChapterLoopRun.draft_preview`; UI in `RunDetailPage.tsx` |
| Raw draft recovery and rerun | `loop_runs.py::recover_loop_draft()` and `rerun_loop()` |
| Auto Review / Revise / Commit | `services/api/app/services/auto_pipeline.py` |
| Reference Pack for chapter/version | `services/api/app/services/reference_service.py` |
| Multi-chapter production | `services/api/app/services/multi_chapter.py` |
| Positive integer chapter count | `services/api/app/schemas/auto.py::MultiChapterRunCreate` |
| Missing chapter/plan fallback | `services/api/app/services/chapter_plan_fallback.py` |
| Provider local recovery/fallback | `services/api/app/services/provider_recovery.py` |
| Chapter summary memory | `services/api/app/services/story_memory.py` |
| Forward Story Engineering（想法→结构化前置物料→staging→接受落库） | `services/api/app/services/story_engineering.py`, `routers/story_engineering.py` |
| 章节提交后结构化状态推进（staging→接受推进 CanonState） | `services/api/app/services/story_memory.py::stage_state_changes`, `agents/checkers.py::StateChangeExtractorAgent` |
| 拆解参考小说（10 维度、整本异步分块 Map-Reduce、候选落库到人物/世界/时间线/情节/伏笔/Novel） | `services/api/app/services/deconstruction.py`, `routers/deconstruction.py`, `models/auto_entities.py::DeconstructionRun` |
| 仿写（基于已采纳 bible 生成全新原创框架） | `services/api/app/prompts/story_engineering/pastiche_framework.md`, `services/story_engineering.py` |
| Checkpoint every N chapters | `services/api/app/services/multi_chapter.py::_create_checkpoint()` |
| Version restore with backup | `loop_runs.py::restore_chapter_version()` |
| Hash-based deep links and run UI | `apps/web/src/App.tsx`, `apps/web/src/features/runs/` |
| Alembic migration chain | `services/api/migrations/versions/` |

## Not implemented

- Forward Story Engineering（想法→结构化前置物料）与角色状态推进 **已实现 P0**，见
  `docs/30_story_engineering_report.md`。仍未实现：结构化 RelationshipState、TimelineEvent、
  Foreshadowing、PlotThread、ItemState、LocationState 的抽取与落库。
- 低风险候选自动接受策略（默认关闭，尚未实现开关）。
- 独立的状态候选/前置物料专属前端页（目前在创作中心列表内采纳）。
- RAG, vector database or GraphRAG.
- Backend-persisted Writer / Checker / Summary model roles. The current role selector uses browser
  localStorage in `apps/web/src/features/models/ModelRoleAssignments.tsx`; a Loop run still uses one
  provider for Writer and Checker.
- Version diff UI.
- Dedicated multi-chapter parent detail page.
- Paginated ModelCall and RunStep log APIs.
- SSE/WebSocket event delivery. Run detail polls once per second.
- Frontend Playwright/E2E suite. `apps/web/package.json` has no `e2e` script.
- API-key storage in macOS Keychain.
- Multi-process durable queue.
- Data retention, prompt/response redaction and log cleanup policy.

## Proven by tests

Current command:

```bash
cd services/api
.venv/bin/pytest -q
```

Current result:

```text
59 passed
```

（2026-06-13：原 48 + Forward Story Engineering 2 + 状态推进 2 + 拆解/仿写 7。详见
`docs/30_story_engineering_report.md`、`docs/31_reverse_story_engineering_report.md`。）

The suite proves:

- Legacy generate, summarize, review and export still work:
  `services/api/tests/test_api.py`.
- Manual Loop reaches the human gate without overwriting content:
  `services/api/tests/test_loop_runner.py`.
- Invalid Checker JSON fails explicitly and is logged:
  `services/api/tests/test_loop_runner.py`.
- Approve alone updates content; reject does not; revise appends a version:
  `services/api/tests/test_loop_stability.py`.
- EMPTY_CONTENT, SCHEMA_VALIDATION_ERROR and MODEL_TIMEOUT propagate:
  `services/api/tests/test_loop_stability.py`.
- Database-level active-run uniqueness and Alembic upgrade:
  `services/api/tests/test_loop_stability.py`.
- Auto revise, auto commit, blocker pause and reference isolation:
  `services/api/tests/test_mvp3_auto_pipeline.py`.
- Multi-chapter commit, fallback planning, checkpoint, resume, restore and provider fallback:
  `services/api/tests/test_mvp3_multi_chapter.py`.

Frontend verification:

```bash
cd apps/web
npm run build
```

Current result:

```text
tsc --noEmit && vite build
42 modules transformed
build passed
```

## Real local model validation

Real LM Studio validation is recorded, not merely inferred:

- `docs/19_writer_streaming_and_recovery_report.md`: real streaming output, raw-output recovery,
  Continuity Checker and WAIT_HUMAN_APPROVAL.
- `docs/29_auto_revision_loop_fix_report.md`: non-blocker major issues triggered RevisionWriter
  instead of a second DraftWriter.
- On 2026-06-12, run `b6a00400-4ec4-44d0-95b7-528490c9d614` used
  `LM Studio · qwen3.6-27b-crack`, created revision versions through round 3, rechecked and reached
  `committed / MEMORY_UPDATED`.

This proves one real local configuration. It does not prove all models or providers.

## Not proven yet

- Browser automation of the full start-run, approve, reject, revise and refresh-recovery path.
- Long-duration stress runs across dozens of chapters.
- Concurrent multi-process uvicorn workers writing SQLite.
- Crash recovery during an active streaming model call.
- Quality of deterministic fallback chapter plans for long novels.
- Quality and safety of automatic writing across arbitrary third-party models.
- Cloud provider behavior and credential handling.
- Migration of every historical user database shape.

## Database status

There are two important databases:

### Repository development database

Path:

```text
data/novel_local_ai.db
```

Observed on 2026-06-12:

- Alembic version: `0f19e48aa920`.
- It does not contain MVP 3 tables such as `story_memory_records`.
- `services/api/.venv/bin/alembic heads` reports `f3a421d91870`.

This database is stale relative to the current migration head. Do not use it as proof that migrations
are current, and do not stamp it without backup and schema inspection.

### Deployed application database

Path:

```text
~/Library/Application Support/NovelLocalAI/data/novel_local_ai.db
```

Observed on 2026-06-12:

- Alembic version: `f3a421d91870`.
- `PRAGMA integrity_check`: `ok`.
- Contains AutoRunPolicy, ReferencePack, RevisionPlan, StoryMemoryRecord, MultiChapterRun and
  CheckpointSnapshot tables.
- Runtime API at `127.0.0.1:8000` is using this deployed copy.

Deployment launch configuration is in:

- `~/Library/LaunchAgents/com.novel-local-ai.api.plist`
- `~/Library/LaunchAgents/com.novel-local-ai.web.plist`
- `~/Library/LaunchAgents/com.novel-local-ai.llama.plist`

## Frontend status

- React 18.3.1, TypeScript, Vite 8 and Tailwind 3:
  `apps/web/package.json`.
- No React Router; `apps/web/src/App.tsx::parseRoute()` implements hash routing.
- No state-management library or component library.
- Project pages, chapters, runs, model settings and prompts are accessible.
- Run detail shows state timeline, versions, Continuity Report, revision plans, raw model logs and
  approval actions.
- Production build passes.
- No automated frontend E2E.

## Backend status

- FastAPI, SQLAlchemy, Pydantic and SQLite:
  `services/api/pyproject.toml`, `services/api/app/db.py`.
- Three in-process queues start in `services/api/app/main.py::lifespan()`:
  legacy WritingTask queue, single-chapter Loop queue and MultiChapter queue.
- The queues are daemon threads, not durable external workers.
- `create_tables()` still runs at startup in addition to Alembic. This creates missing tables but
  does not safely migrate changed columns.

## Provider status

Provider support is implemented in `services/api/app/providers/adapters.py`:

- OpenAI-compatible / llama.cpp / text-generation-webui.
- LM Studio.
- Ollama.
- KoboldCpp.

Local service recovery is implemented in `services/api/app/services/provider_recovery.py`.

Observed runtime on 2026-06-12:

- LM Studio `qwen3.6-27b-crack` is configured and has successfully recovered before a Loop run.
- Managed llama.cpp is configured at `127.0.0.1:18081`.
- Other configured providers may be untested; inspect `/api/model-providers` before relying on them.

## 故事地图后端（阶段 1，已实现）

- 新增聚合读接口 `GET /api/novels/{id}/story-map`：一次返回 chapters / characters /
  timeline_events / plot_threads / foreshadowing / 归一化 relationships / unmatched / stats。
- 时间线事件 / 情节线 / 伏笔各有独立 additive CRUD 路由；`TimelineEvent` 新增可空 `story_order`。
- AI 逐章提取管线（`POST /novels/{id}/story-map/extract` + 轮询 extract-runs）：候选写 staging
  （record_type=`staged_storymap_*`），复用 story-engineering 的 list/accept/reject 接口；无模型服务时
  优雅失败并留 PARTIAL 记录。详见 `docs/32_story_map_backend_report.md`。

## Most trustworthy conclusions

1. The legacy API and new Loop path coexist and the backend regression suite passes.
2. ChapterVersion is append-only at the ORM layer.
3. Manual content is not updated before approve.
4. Auto commit creates a backup and is blocked by blocker issues.
5. Structured Checker output is validated by Pydantic and cannot silently succeed on invalid JSON.
6. Multi-chapter orchestration works with mock providers and has one real LM Studio progression.

## Misleading assumptions to avoid

- Do not say “current stage is MVP 1” because the code includes MVP 3 Phase 3.
- Do not say “multi-chapter is limited to 1/3/5”; the schema now accepts any positive integer.
- Do not say “missing plans always pause”; the current code creates a conservative fallback plan.
- Do not say “all Story Memory is automatic”; only chapter-summary records are implemented.
- Do not say “full autonomous has system access”; it is restricted to writing workflow actions.
- Do not say “all tests use a real model”; most are mock-provider tests.
- Do not assume the repository DB and deployed DB have the same schema or data.
