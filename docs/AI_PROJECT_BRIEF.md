# AI Project Brief

## Project goal

Novel Local AI is a local-first novel writing application for macOS. It stores projects, chapters,
characters, world rules, prompts, model configuration, versions and run logs in SQLite, while the
main writing workflow can use LM Studio, llama.cpp, Ollama, KoboldCpp or another
OpenAI-compatible local HTTP service.

Evidence:

- Product overview: `README.md`
- Provider adapters: `services/api/app/providers/adapters.py`
- Persistent entities: `services/api/app/models/entities.py`,
  `services/api/app/models/loop_entities.py`,
  `services/api/app/models/auto_entities.py`

## User goal

The user should be able to:

1. Create a novel and maintain its outline, characters and world rules.
2. Select a local model and generate one or more chapters.
3. Review an immutable generated version before it becomes official content.
4. Let AI check and optionally revise continuity problems.
5. Use controlled auto-commit or full-autonomous mode inside one novel project.
6. Pause, inspect, recover and roll back without deleting version history.

The implemented UI for these paths is under:

- `apps/web/src/features/chapters/ChapterWorkspaceV2.tsx`
- `apps/web/src/features/runs/RunDetailPage.tsx`
- `apps/web/src/features/runs/MultiChapterRunsPanel.tsx`

## Why local

The application is designed for private manuscript data, long-running local generation and user-owned
model infrastructure. The main database is SQLite and model adapters target localhost endpoints.
Cloud OpenAI-compatible providers are technically supported by the adapter type, but no cloud service
is required for CRUD, editing, export or the intended core flow.

Evidence:

- Database selection: `services/api/app/db.py`
- Provider abstraction: `services/api/app/providers/base.py`
- Concrete adapters: `services/api/app/providers/adapters.py`

## What Loop Agent means here

“Loop Agent” is not an unrestricted autonomous agent. It is a persisted workflow with explicit states,
guarded model calls and append-only artifacts.

Single-chapter flow:

```text
LOAD_PROJECT
-> ASSEMBLE_CONTEXT
-> WRITE_DRAFT
-> CHECK_CONTINUITY
-> WAIT_HUMAN_APPROVAL
```

Auto modes may add:

```text
BUILD_REVISION_PLAN
-> REVISE_DRAFT
-> CHECK_CONTINUITY
-> AUTO_COMMITTING
-> COMMITTED
-> UPDATING_STORY_MEMORY
-> MEMORY_UPDATED
```

Evidence:

- State enum and transitions: `services/api/app/workflow/states.py`
- Execution loop: `services/api/app/workflow/runner.py::NovelLoopRunner`
- Auto decision policy: `services/api/app/services/auto_pipeline.py`

Every step is persisted as RunStep and every model call as ModelCall. Generated text first becomes a
ChapterVersion. These entities are in `services/api/app/models/loop_entities.py`.

## Current scope is no longer only one chapter

Early reports correctly said the product was not a multi-chapter autonomous writer at that time.
Current code now includes `MultiChapterRun` and can process any positive integer chapter count,
creating missing chapters and conservative plans within the requested range.

Evidence:

- Request schema: `services/api/app/schemas/auto.py::MultiChapterRunCreate`
- API: `services/api/app/routers/multi_chapter_runs.py`
- Coordinator: `services/api/app/services/multi_chapter.py`
- Fallback planning: `services/api/app/services/chapter_plan_fallback.py`
- Tests: `services/api/tests/test_mvp3_multi_chapter.py`

It is still not a complete “write an entire industrial novel unattended” system. It lacks reverse
story extraction, full structured memory updates, semantic retrieval, GraphRAG, robust multi-process
queues and complete browser E2E coverage.

## Current product emphasis

The core remains:

- Chapter generation.
- Continuity checking.
- Immutable versions.
- Human approval or bounded automatic approval.
- RunStep and ModelCall audit logs.
- Safe pause and recovery.

The system must never interpret “full autonomous” as permission to delete data, modify model settings,
erase history or bypass logs. Enforcement is split across
`services/api/app/routers/auto_runs.py`,
`services/api/app/routers/multi_chapter_runs.py`,
`services/api/app/services/auto_pipeline.py` and the append-only version model.

## Local model versus mock provider

Most automated tests use a local in-process HTTP mock provider. These tests prove API behavior,
state transitions, persistence and error handling, but not model quality.

Mock evidence:

- `services/api/tests/test_api.py::MockModelHandler`
- `services/api/tests/test_loop_stability.py`
- `services/api/tests/test_mvp3_auto_pipeline.py`
- `services/api/tests/test_mvp3_multi_chapter.py`

Real local model evidence also exists:

- `docs/19_writer_streaming_and_recovery_report.md` records LM Studio streaming and draft recovery
  with `qwen3.6-27b-crack`.
- `docs/29_auto_revision_loop_fix_report.md` and the 2026-06-12 live run verified automatic
  RevisionWriter iterations, recheck and commit.

Do not generalize those runs to every GGUF model, context length or provider implementation.

## Old generation versus new Loop

### Old path

`POST /api/chapters/{chapter_id}/generate`

- Route: `services/api/app/routers/chapters.py::generate_chapter()`
- Queue: `services/api/app/services/task_queue.py`
- Pipeline: `services/api/app/pipelines/chapter_pipeline.py`
- Persistence: WritingTask and GenerationRun in `services/api/app/models/entities.py`
- Behavior: may directly update `Chapter.content`; it is exposed only as Legacy / Advanced in
  `apps/web/src/components/ProjectWorkspaceShell.tsx`.

### New Loop path

Manual:

`POST /api/projects/{project_id}/chapters/{chapter_id}/run`

Automatic:

`POST /api/projects/{project_id}/chapters/{chapter_id}/auto-run`

Multi-chapter:

`POST /api/projects/{project_id}/multi-chapter-runs`

- Routes: `services/api/app/routers/loop_runs.py`,
  `services/api/app/routers/auto_runs.py`,
  `services/api/app/routers/multi_chapter_runs.py`
- Execution: `services/api/app/workflow/runner.py` and
  `services/api/app/services/multi_chapter.py`
- Persistence: ChapterLoopRun, RunStep, ModelCall, ChapterVersion, AutoRunPolicy,
  RevisionPlan and MultiChapterRun.
- Behavior: generated versions are retained; manual content is not overwritten before approval;
  auto-commit requires policy checks and creates a backup first.

These paths must continue to coexist until an explicit migration plan removes the legacy flow.
