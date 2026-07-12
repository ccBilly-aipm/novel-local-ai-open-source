# AI Run and Test Guide

## Prerequisites

- macOS
- Python 3.9+
- Node.js 18+
- Optional local model server for real generation

Dependency declarations:

- Backend: `services/api/pyproject.toml`
- Frontend: `apps/web/package.json`

## Backend setup

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health:

```bash
curl -sS http://127.0.0.1:8000/api/health
```

Expected:

```json
{"status":"ok"}
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Frontend setup

```bash
cd apps/web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173/
```

Vite proxies `/api` to `127.0.0.1:8000`; see `apps/web/vite.config.ts`.

## Combined development launcher

After dependencies exist:

```bash
./scripts/dev.sh
```

The script starts uvicorn and Vite and terminates both when the script exits.

## Existing deployed app

The current machine also has a deployed copy:

```text
~/Library/Application Support/NovelLocalAI/
```

LaunchAgents:

```text
~/Library/LaunchAgents/com.novel-local-ai.api.plist
~/Library/LaunchAgents/com.novel-local-ai.web.plist
~/Library/LaunchAgents/com.novel-local-ai.llama.plist
```

Logs:

```bash
tail -f "$HOME/Library/Logs/NovelLocalAI/api.log"
tail -f "$HOME/Library/Logs/NovelLocalAI/api.err"
tail -f "$HOME/Library/Logs/NovelLocalAI/web.log"
tail -f "$HOME/Library/Logs/NovelLocalAI/web.err"
tail -f "$HOME/Library/Logs/NovelLocalAI/llama.log"
tail -f "$HOME/Library/Logs/NovelLocalAI/llama.err"
```

Do not edit the deployed copy and repository copy independently without an explicit sync plan.

## Backend tests

Required full suite:

```bash
cd services/api
.venv/bin/pytest -q
```

Verified 2026-06-12:

```text
38 passed
```

Focused suites:

```bash
.venv/bin/pytest tests/test_api.py -q
.venv/bin/pytest tests/test_loop_runner.py -q
.venv/bin/pytest tests/test_loop_mvp_e2e.py -q
.venv/bin/pytest tests/test_loop_stability.py -q
.venv/bin/pytest tests/test_mvp3_auto_pipeline.py -q
.venv/bin/pytest tests/test_mvp3_multi_chapter.py -q
```

## Frontend build

```bash
cd apps/web
npm run build
```

This runs `tsc --noEmit && vite build`.

Verified 2026-06-12:

```text
42 modules transformed
build passed
```

There is no `npm run e2e` or `npm run lint` script in `apps/web/package.json`.

## Test database behavior

`services/api/tests/conftest.py` sets:

```text
NOVEL_AI_DB_URL=sqlite:///services/api/tests/test_novel.db
```

It deletes the previous test database before importing the application. The test suite therefore does
not write the repository database or deployed database.

For manual isolated API work:

```bash
TMP_DIR="$(mktemp -d /tmp/novel-local-ai-handoff.XXXXXX)"
TMP_DB="$TMP_DIR/novel-local-ai-handoff.db"
cd services/api
NOVEL_AI_DB_URL="sqlite:///$TMP_DB" .venv/bin/alembic upgrade head
NOVEL_AI_DB_URL="sqlite:///$TMP_DB" \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## Migration checks

Show head:

```bash
cd services/api
.venv/bin/alembic heads
```

Expected head:

```text
f3a421d91870
```

Check a specific database:

```bash
NOVEL_AI_DB_URL="sqlite:////absolute/path/to/novel_local_ai.db" \
  .venv/bin/alembic current
```

Before migrating an existing database:

```bash
cp /path/to/novel_local_ai.db /path/to/novel_local_ai.backup-$(date +%Y%m%d-%H%M%S).db
sqlite3 /path/to/novel_local_ai.db "PRAGMA integrity_check;"
sqlite3 /path/to/novel_local_ai.db ".tables"
sqlite3 /path/to/novel_local_ai.db "SELECT version_num FROM alembic_version;"
```

Do not run `alembic stamp` unless the existing schema has been inspected and matches the target
baseline. `create_tables()` in `services/api/app/db.py` is not a migration substitute.

## Configure a Provider

List:

```bash
curl -sS http://127.0.0.1:8000/api/model-providers
```

Create LM Studio:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/model-providers \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "LM Studio local",
    "provider_type": "lm_studio",
    "base_url": "http://127.0.0.1:1234/v1",
    "model": "your-loaded-model-id",
    "timeout_seconds": 600,
    "default_options": {
      "temperature": 0.7,
      "max_tokens": 4200
    }
  }'
```

Test:

```bash
curl -sS -X POST \
  http://127.0.0.1:8000/api/model-providers/PROVIDER_ID/test
```

Never put a real API key in handoff documents or command history. Provider keys are stored in local
SQLite by `services/api/app/models/entities.py::ModelProvider`; Keychain integration is not implemented.

## Create a manual Loop Run

Set IDs:

```bash
BASE=http://127.0.0.1:8000
PROJECT_ID=<project-id>
CHAPTER_ID=<chapter-id>
PROVIDER_ID=<provider-id>
```

Create:

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/chapters/$CHAPTER_ID/run" \
  -H 'Content-Type: application/json' \
  -d "{
    \"provider_id\":\"$PROVIDER_ID\",
    \"context_budget\":6000,
    \"options\":{\"temperature\":0.75,\"max_tokens\":4200}
  }"
```

Save the returned `id`:

```bash
RUN_ID=<run-id>
```

Query:

```bash
curl -sS "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID"
```

Expected manual terminal review state:

```text
state=WAIT_HUMAN_APPROVAL
status=waiting
```

## Approve, reject and revise

Approve:

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID/approve" \
  -H 'Content-Type: application/json' \
  -d '{"feedback":"人工确认通过"}'
```

Reject:

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID/reject" \
  -H 'Content-Type: application/json' \
  -d '{"feedback":"本版本不采用"}'
```

Revise:

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID/revise" \
  -H 'Content-Type: application/json' \
  -d '{"feedback":"修复连续性问题并保留原有结尾"}'
```

## Create an automatic single-chapter run

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/chapters/$CHAPTER_ID/auto-run" \
  -H 'Content-Type: application/json' \
  -d "{
    \"provider_id\":\"$PROVIDER_ID\",
    \"mode\":\"ai_auto_commit\",
    \"context_budget\":6000,
    \"max_revision_rounds_per_chapter\":3,
    \"stop_on_major_after_rounds\":3,
    \"update_story_memory\":true,
    \"permission_confirmed\":false,
    \"references\":[]
  }"
```

Use `permission_confirmed=true` only for `full_autonomous`.

## Create a multi-chapter run

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/multi-chapter-runs" \
  -H 'Content-Type: application/json' \
  -d "{
    \"provider_id\":\"$PROVIDER_ID\",
    \"start_chapter_id\":\"$CHAPTER_ID\",
    \"chapter_count\":3,
    \"mode\":\"ai_auto_commit\",
    \"context_budget\":6000,
    \"max_revision_rounds_per_chapter\":3,
    \"stop_on_major_after_rounds\":3,
    \"checkpoint_every\":3,
    \"update_story_memory\":true,
    \"references\":[]
  }"
```

The schema accepts any integer greater than zero. The UI requires an additional confirmation above
10 chapters.

## Verify Chapter.content was not overwritten

Before starting:

```bash
curl -sS "$BASE/api/chapters/$CHAPTER_ID" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["version"]); print(d["content"])'
```

After the run reaches `WAIT_HUMAN_APPROVAL`, run the same command. The content and chapter version must
remain unchanged.

After approve, the content must match the approved ChapterVersion and chapter version should increase
when content changed.

## Verify ChapterVersion

List versions:

```bash
curl -sS "$BASE/api/chapters/$CHAPTER_ID/versions"
```

Check:

- `version_number` increases.
- generated version has `kind=draft` or `kind=revision`.
- `content_hash` is populated.
- old versions remain present.

Implementation: `services/api/app/services/version_manager.py`.

## Verify JSON_PARSE_ERROR

Use the existing automated test:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_runner.py::test_invalid_continuity_json_fails_run_and_keeps_model_log -q
```

Expected:

- run status `failed`;
- error code `JSON_PARSE_ERROR`;
- failed CHECK_CONTINUITY RunStep;
- failed continuity_checker ModelCall with raw response;
- draft ChapterVersion remains;
- `Chapter.content` remains unchanged.

## Verify SCHEMA_VALIDATION_ERROR

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_schema_validation_error_fails_run_and_model_call -q
```

## Verify EMPTY_CONTENT

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_empty_draft_fails_without_chapter_version -q
```

## Verify model timeout

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_model_timeout_is_logged_and_fails_run -q
```

## Verify duplicate active run returns conflict

Automated database test:

```bash
cd services/api
.venv/bin/pytest tests/test_loop_stability.py::test_database_unique_active_slot_blocks_concurrent_runs -q
```

Manual API:

1. Start one Loop for a chapter.
2. Before it reaches a terminal state, repeat the same create request.
3. Expected HTTP status: `409`.
4. Expected detail: `Chapter already has an active Loop run`.

Database guard:

```text
uq_chapter_loop_active_slot
```

defined in `services/api/app/models/loop_entities.py`.

## Common failures

### `PROVIDER_UNAVAILABLE`

Inspect:

- `services/api/app/services/provider_recovery.py`
- `AutoRunPolicy.metadata_json` or `MultiChapterRun.policy_json` provider attempts
- `~/Library/Logs/NovelLocalAI/api.err`
- provider endpoint `/models` or Ollama `/api/tags`

### `JSON_PARSE_ERROR` or `SCHEMA_VALIDATION_ERROR`

Inspect:

- `ModelCall.response`
- `ModelCall.raw_response_json`
- `ModelCall.parsed_json`
- `services/api/app/services/json_guard.py`
- `services/api/app/prompts/novel_loop/continuity_checker.md`

Do not turn these errors into an empty “passed” report.

### `EMPTY_CONTENT`, `TOO_SHORT`, `MODEL_REFUSAL`, `PROMPT_LEAK`

Inspect:

- `ChapterLoopRun.draft_attempts_json`
- writer ModelCall responses
- `services/api/app/services/draft_text_guard.py`
- model token budget and thinking settings

### `AUTO_RUN_PAUSED`

Inspect:

- `ChapterLoopRun.continuity_report_json`
- `AutoRunPolicy.revision_rounds`
- `AutoRunPolicy.max_revision_rounds_per_chapter`
- `services/api/app/services/auto_pipeline.py::next_state_after_check()`

Resume can add one or more revision rounds through
`ResumeRunRequest.additional_revision_rounds`.

### `CHAPTER_PLAN_MISSING`

This can exist on historical runs. Current multi-chapter creation uses
`services/api/app/services/chapter_plan_fallback.py` to extract or create a plan.
Historical error text is intentionally retained for audit.

### Backend restart

`services/api/app/workflow/runner.py::SerialLoopQueue.recover_pending()` marks interrupted running
single-chapter runs as failed with `BACKEND_RESTARTED`, then requeues pending runs.

`services/api/app/services/multi_chapter.py::MultiChapterQueue.recover_pending()` resets pending/running
parent runs to pending and requeues them.

Inspect both parent and child state after a restart.

### SQLite locked

The product uses several daemon threads and SQLite. Check for long transactions, duplicate processes
and multiple uvicorn workers. Current deployment should remain single-process. Do not solve this by
disabling foreign keys or removing unique indexes.

## 故事地图前端 E2E（Playwright）

故事地图页有一份 Playwright 冒烟测试：`apps/web/e2e/storymap.spec.ts`
（造数 → 打开 `/#/projects/{id}/storymap` → 断言四视图可切换、SVG 有节点、hover/click 联动、提取对话框可打开）。

前置：先安装浏览器 `cd apps/web && npx playwright install chromium`。

**重要（避开部署副本）**：本机 LaunchAgent 部署副本常年占用 `:5173`（前端）与 `:8000`（后端）。
直接跑会命中旧的部署副本、测到错误的代码。务必用**独立端口**起自己的开发栈再测：

```bash
# 1) 后端起在独立端口 + 一次性 DB（不碰用户库）
cd services/api
E2EDB=$(mktemp).db
NOVEL_AI_DB_URL="sqlite:///$E2EDB" .venv/bin/alembic upgrade head
NOVEL_AI_DB_URL="sqlite:///$E2EDB" .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8099 &

# 2) 前端起在独立端口，代理指向上面的后端（VITE_API_TARGET 覆盖默认 :8000）
cd ../../apps/web
VITE_API_TARGET="http://127.0.0.1:8099" npx vite --host 127.0.0.1 --port 5199 --strictPort &

# 3) 跑 E2E（E2E_BASE/E2E_API 指向独立端口）
E2E_BASE="http://127.0.0.1:5199" E2E_API="http://127.0.0.1:8099" npm run e2e
```

若默认端口没有被部署副本占用，也可以直接 `npm run dev`（前端 :5173 代理到后端 :8000）后 `npm run e2e`。

### 故事地图页人工回归清单（E2E 未跑或环境受限时的兜底）

时间线：① 切「叙事顺序/故事顺序」排列变化；② 悬停事件点出光晕 + 右侧预览；③ 顶部伏笔弧线（未回收虚线/超期变红）。
人物网络：① 悬停节点一跳邻居高亮、其余淡出；② 主角有六边形环、半径随出场章数；③ 底部滑块回放只显示该章前已出场人物。
故事线：① 每条 thread 在其章节列打结点连线；② resolved 线回收后变淡；③ 悬停章节列头淡金背景 + 联动高亮。
仪表盘：① 字数柱+移动平均线；② 连续性分数趋势（无数据显示空态）；③ 伏笔计数环（超期>0 变红）；④ 热力图点格跳人物网络。
