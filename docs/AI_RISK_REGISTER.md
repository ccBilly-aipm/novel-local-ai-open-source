# AI Risk Register

| Risk | Severity | Evidence | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| Single-chapter active-run race | Medium, mitigated | Partial unique index in `services/api/app/models/loop_entities.py`; concurrency test in `test_loop_stability.py` | Duplicate model calls and conflicting versions if guard regresses | Preserve index and 409 mapping; run concurrency test after model/router changes | Backend |
| Multi-chapter active-run race | Medium, mitigated | `uq_multi_chapter_active_novel` in `auto_entities.py` and migration `f3a421d91870` | Two production lines could write the same novel | Preserve index; keep one active parent per novel | Backend |
| Startup `create_all` bypasses migration audit | High | `services/api/app/main.py::lifespan()` calls `create_tables()`; `db.py` uses `Base.metadata.create_all()` | Missing tables can appear without an Alembic revision; changed columns remain stale | Treat Alembic as authoritative; add startup schema/version check before removing `create_all` | Backend/DB |
| Repository DB is behind migration head | High | `data/novel_local_ai.db` at `0f19e48aa920`; head is `f3a421d91870` | New agent may test against wrong schema or corrupt it with a stamp | Back up, inspect and migrate explicitly; prefer disposable DB for development | Maintainer |
| WAIT_HUMAN_APPROVAL could become stuck if decision APIs regress | High | Human gate in `runner.py`; decision APIs in `loop_runs.py` and `loop_approval.py` | Active slot remains occupied and official content cannot advance | Keep approve/reject/revise tests; expose recovery diagnostics | Backend |
| Structured model JSON instability | High | `JsonGuard` and repair path; tests for parse/schema failures | Checker may fail after usable draft generation | Retain raw output, one repair attempt, Pydantic validation and explicit failure | Agent/Backend |
| Real local models differ from mocks | High | Most tests use HTTP mock handlers; real evidence limited to LM Studio reports | Model may ignore output format, reason too long or return empty text | Keep DraftTextGuard, JSON repair, per-provider manual acceptance and conservative defaults | LLM integration |
| Full prompt/response privacy | High | `RunLogger` stores prompt, response and raw payload | Private manuscripts and cloud responses remain indefinitely in SQLite | Design redaction/retention; never log API keys; document local file sensitivity | Security |
| SQLite multi-process writes | High | SQLite plus daemon queues in `main.py`; no external job broker | Lock errors or duplicate execution under multiple uvicorn workers | Run one API process; keep transactions short; do not deploy multiple workers | Operations |
| Browser disconnect/reload recovery | Medium | `RunDetailPage.tsx` polls state; backend worker is independent | User may lose local UI state but run continues | Persist state server-side, use hash deep links, reload run detail by ID | Frontend |
| Backend restart during child run | High | `SerialLoopQueue.recover_pending()` marks running child FAILED; parent recovery differs | Parent and child can require manual reconciliation | Test restart scenarios; display child and parent state; avoid duplicate resume | Workflow |
| New Loop breaks old generate API | Critical | Legacy route in `chapters.py`; regression in `test_api.py` | Existing users may get changed direct-write behavior | Never route legacy API through Loop implicitly; keep `test_api.py` passing | All agents |
| Automatic state update pollutes Canon | Critical | Current `story_memory.py` writes only evidence-backed summary; full Canon update absent | Hallucinated facts become future context | Keep extraction/memory staged; require evidence and explicit acceptance | Product/Backend |
| Auto commit writes unsuitable content | High | Policy in `auto_pipeline.py`; local Checker quality varies | Official content can advance with weak model review | Preserve blocker gate, major threshold, revision limit, backup and restore | Workflow |
| Checker labels `auto_fixable=false` inconsistently | Medium, mitigated | Fixed in `docs/29_auto_revision_loop_fix_report.md` and `auto_pipeline.py` | Auto mode may pause too early or skip revision | Treat non-blocker issues as revisable attempt; retain must_pause semantics | Agent policy |
| Infinite or excessive revision loops | High, mitigated | AutoRunPolicy revision and model-call limits | Cost, heat and long unattended execution | Preserve max revision rounds, max calls and pause behavior | Workflow |
| Provider recovery launches local processes | Medium | `provider_recovery.py` calls LM Studio CLI, `open`, and launchctl | Unexpected model load or resource use | Restrict to recognized local providers; record attempts; expose stop controls | Operations |
| Provider fallback changes model unexpectedly | Medium | `resolve_provider()` can select another enabled local provider | Output quality and context behavior may change silently | Persist requested/resolved provider and show attempts in UI | Product/Backend |
| Deterministic chapter-plan fallback is low quality | Medium | `chapter_plan_fallback.py` creates generic plans | Multi-chapter run may drift from author intent | Mark fallback source, show it in UI, prefer story-outline extraction, add staging later | Product |
| Version immutability is ORM-only | Medium | SQLAlchemy `before_update` event in `loop_entities.py` | Direct SQL can alter historical text | Treat DB file as trusted; add DB trigger only after migration design | DB |
| Version numbering race | Medium | `version_manager.py` reads max then inserts; unique constraint catches conflict | Concurrent restore/revision could raise IntegrityError | Keep one active run per chapter; consider retry around version insert | Backend |
| Run detail payload grows without bound | Medium | `get_run_detail()` eager-loads all steps, calls and versions | Slow API and large browser memory for long runs | Add paginated logs/artifacts endpoints; retain summary endpoints | Backend/Frontend |
| No frontend automated E2E | Medium | `apps/web/package.json` lacks e2e script | UI regressions may pass TypeScript build | Add Playwright with isolated mock backend when prioritized | Frontend |
| Model role settings are browser-only | Medium | `ModelRoleAssignments.tsx` localStorage | Checker/Summary choice is not authoritative or portable | Add backend settings and explicit provider IDs per role | Product/Backend |
| API key stored in SQLite | High | `ModelProvider.api_key` in `entities.py` | Local DB compromise exposes credentials | Add Keychain integration or encrypted local secret store | Security |
| README contains stale boundary text | Low | README says missing plans are not auto-generated, contrary to `chapter_plan_fallback.py` | New agent may design around false assumptions | Update docs in a documentation-only change | Docs |

## Immediate risk priorities

1. Do not migrate or stamp the stale repository database blindly.
2. Keep the API single-process while SQLite and in-memory queues are used.
3. Preserve old generate behavior and all content/version safety tests.
4. Build Reverse Story Engineering as staging-only.
5. Add sensitive-log retention and redaction before wider private manuscript use.
