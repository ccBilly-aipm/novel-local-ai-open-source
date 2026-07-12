# MVP 1.1 Stability Patch Report

## 1. Scope

本补丁只处理进入 MVP 2 前的稳定性门槛：

- 人工 approve/reject/revise 闭环。
- SQLite 数据库级 active-run 并发保护。
- Alembic baseline 与 MVP 1.1 migration。
- 空正文、schema 错误、模型超时、审批、修订和并发 E2E。

未实现多章循环、自动 Canon 更新、复杂前端或多 Provider fallback。

## 2. Implemented API

### Approve

```http
POST /api/projects/{project_id}/runs/{run_id}/approve
```

请求体：

```json
{"feedback": "人工确认通过"}
```

行为：

- 只接受 `WAIT_HUMAN_APPROVAL / waiting` run。
- 校验 `current_version_id` 属于当前 run 和 chapter。
- 在同一事务中把 ChapterVersion 写入 `Chapter.content`。
- Chapter 状态变为 `approved`。
- run 变为 `APPROVED / approved`，释放 active slot。
- 写入 `APPROVED` RunStep。

实现：`app/routers/loop_runs.py::approve_loop_run()` 和
`app/services/loop_approval.py::approve_run()`。

### Reject

```http
POST /api/projects/{project_id}/runs/{run_id}/reject
```

请求体：

```json
{"feedback": "剧情节奏不符合要求"}
```

行为：

- run 变为 `REJECTED / rejected`。
- 释放 active slot。
- 写入 `REJECTED` RunStep。
- 不修改 `Chapter.content`。

实现：`app/routers/loop_runs.py::reject_loop_run()` 和
`app/services/loop_approval.py::reject_run()`。

### Revise

```http
POST /api/projects/{project_id}/runs/{run_id}/revise
```

请求体：

```json
{"feedback": "补充锁死期间的纸质记录细节"}
```

行为：

- 保存人工反馈和父版本 ID。
- 状态进入 `REVISE_DRAFT / pending`。
- `RevisionWriterAgent` 生成完整修订正文。
- 追加 `kind=revision` 的新 ChapterVersion。
- 新版本通过 `parent_version_id` 指向旧版本。
- 重新执行 continuity checker，再回到 `WAIT_HUMAN_APPROVAL`。
- 不修改旧 ChapterVersion，也不修改 `Chapter.content`。

实现：

- `app/routers/loop_runs.py::revise_loop_run()`
- `app/services/loop_approval.py::request_revision()`
- `app/agents/writer.py::RevisionWriterAgent`
- `app/workflow/runner.py::NovelLoopRunner._execute_state()`

## 3. Approval Data Model

`ChapterLoopRun` 新增：

| 字段 | 用途 |
| --- | --- |
| `active_slot` | 活动 run 使用 1，终态使用 NULL |
| `revision_parent_version_id` | 本轮修订的父版本 |
| `revision_feedback` | 用户修订反馈 |
| `approved_version_id` | 最终批准版本 |
| `decision_feedback` | approve/reject 反馈 |
| `decided_at` | 人工决策时间 |

新增状态：

```text
REVISE_DRAFT
APPROVED
REJECTED
```

## 4. Chapter Content Safety

测试确认：

- 初次 draft 后正文不更新。
- revise 后正文不更新。
- reject 后正文不更新。
- 只有 approve 后正文更新为批准版本。
- approve 同时增加 `Chapter.version` 并将状态设为 `approved`。
- 未写入 CanonState 或任何自动 Canon 变更。

## 5. Immutable Revisions

`ChapterVersionManager` 现在支持：

- `append_draft()`
- `append_revision()`
- `append_version()`

修订使用 append-only 策略。测试生成：

- 9 条 draft version。
- 1 条 revision version。

旧版本内容和 hash 保持不变，现有
`app/models/loop_entities.py::reject_chapter_version_update()` 继续阻止 UPDATE。

## 6. SQLite Active-Run Guard

采用 partial unique index：

```sql
CREATE UNIQUE INDEX uq_chapter_loop_active_slot
ON chapter_loop_runs (chapter_id)
WHERE active_slot = 1;
```

活动范围：

- pending
- running
- waiting
- revising

释放范围：

- approved
- rejected
- failed

`create_loop_run()` 直接依赖数据库唯一约束，并把 `IntegrityError` 转换为 HTTP 409：

```json
{"detail": "Chapter already has an active Loop run"}
```

并发测试使用两个独立 SQLAlchemy Session 同时提交同一 chapter 的 active run，结果严格为：

```text
created: 1
conflict: 1
```

这消除了原先“先查询、后插入”的竞态窗口。

## 7. Error Classification

`app/agents/base.py::StructuredAgent.call()` 新增稳定错误映射：

| 错误 | error_code |
| --- | --- |
| HTTP timeout | `MODEL_TIMEOUT` |
| Provider HTTP error | `PROVIDER_ERROR` |
| 非法 JSON | `JSON_PARSE_ERROR` |
| Pydantic schema 错误 | `SCHEMA_VALIDATION_ERROR` |
| 空 draft 正文 | `EMPTY_CONTENT` |

所有错误继续写入 ModelCall、RunStep 和 ChapterLoopRun，不静默吞错。

## 8. Alembic Baseline

迁移链：

```text
<base>
-> 8cd023ae54b4  pre MVP 1.1 schema baseline
-> 0f19e48aa920  MVP 1.1 stability fields and active-run guard
```

文件：

- `services/api/migrations/versions/8cd023ae54b4_pre_mvp_1_1_schema_baseline.py`
- `services/api/migrations/versions/0f19e48aa920_mvp_1_1_stability_fields_and_active_run_.py`

测试已从空 SQLite 数据库执行 `upgrade head`，完整创建 baseline 和补丁字段、索引。

MVP 1.1 migration 在创建唯一索引前检查重复 active run。发现同一 chapter 有多条
pending/running/waiting run 时会中止，不删除或猜测用户数据。

## 9. Development Database Migration

实际迁移数据库：

```text
data/novel_local_ai.db
```

执行前：

- `PRAGMA integrity_check`：`ok`
- Loop run 总数：2
- active run：1
- 没有重复 active chapter

备份：

```text
data/novel_local_ai.pre_mvp_1_1_20260612.db
```

执行：

```bash
alembic stamp 8cd023ae54b4
alembic upgrade head
```

执行后：

- Alembic current：`0f19e48aa920 (head)`
- `PRAGMA integrity_check`：`ok`
- partial unique index 已存在
- active run 数据已回填

## 10. Migration Procedure

补丁前 create_all 数据库：

```bash
cp data/novel_local_ai.db data/novel_local_ai.backup.db
sqlite3 data/novel_local_ai.db "PRAGMA integrity_check;"
sqlite3 data/novel_local_ai.db "
SELECT chapter_id, COUNT(*)
FROM chapter_loop_runs
WHERE status IN ('pending','running','waiting')
GROUP BY chapter_id
HAVING COUNT(*) > 1;"

cd services/api
NOVEL_AI_DB_URL=sqlite:////absolute/path/to/data/novel_local_ai.db \
  alembic stamp 8cd023ae54b4
NOVEL_AI_DB_URL=sqlite:////absolute/path/to/data/novel_local_ai.db \
  alembic upgrade head
```

不要对结构不明的旧数据库直接 stamp。先备份并确认它确实对应 baseline。

## 11. Rollback

最保守回滚：

1. 停止后端。
2. 保留故障数据库供审计。
3. 用迁移前副本替换 `data/novel_local_ai.db`。
4. 启动补丁前代码。

```bash
cp data/novel_local_ai.db data/novel_local_ai.failed_mvp_1_1.db
cp data/novel_local_ai.pre_mvp_1_1_20260612.db data/novel_local_ai.db
```

对于没有产生审批数据的新测试库，也可执行：

```bash
cd services/api
alembic downgrade 8cd023ae54b4
```

生产数据优先使用备份恢复，因为 downgrade 会删除审批与修订元数据字段。

## 12. E2E Coverage

新增 `services/api/tests/test_loop_stability.py`：

| 场景 | 实际结果 |
| --- | --- |
| approve | 通过；正文只在批准后更新 |
| reject | 通过；正文保持原值 |
| revise | 通过；追加 revision，父版本不变 |
| EMPTY_CONTENT | 通过；FAILED，无 ChapterVersion |
| SCHEMA_VALIDATION_ERROR | 通过；step/call/run 均记录 |
| MODEL_TIMEOUT | 通过；step/call/run 均为 MODEL_TIMEOUT |
| concurrent active run | 通过；数据库只允许一条 |
| Alembic upgrade head | 通过；字段和索引存在 |

测试数据库中的最终错误记录：

```text
EMPTY_CONTENT: 1
JSON_PARSE_ERROR: 2
MODEL_TIMEOUT: 1
SCHEMA_VALIDATION_ERROR: 1
```

## 13. Test Results

### Backend

命令：

```bash
cd services/api
.venv/bin/pytest -q
```

结果：

```text
................. [100%]
17 passed
```

### Frontend

命令：

```bash
cd apps/web
npm run build
```

结果：

```text
tsc --noEmit && vite build
25 modules transformed
build completed in 364ms
```

前端无功能改动；构建用于确认 API 补丁没有破坏现有 TypeScript 项目。

## 14. Curl Examples

变量：

```bash
BASE=http://127.0.0.1:8000
PROJECT_ID=<project-id>
CHAPTER_ID=<chapter-id>
PROVIDER_ID=<provider-id>
RUN_ID=<run-id>
```

创建 Loop run：

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/chapters/$CHAPTER_ID/run" \
  -H 'Content-Type: application/json' \
  -d "{\"provider_id\":\"$PROVIDER_ID\",\"context_budget\":2400,\"options\":{}}"
```

查询：

```bash
curl -sS "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID"
```

批准：

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID/approve" \
  -H 'Content-Type: application/json' \
  -d '{"feedback":"人工确认通过"}'
```

拒绝：

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID/reject" \
  -H 'Content-Type: application/json' \
  -d '{"feedback":"剧情节奏需要重做"}'
```

请求修订：

```bash
curl -sS -X POST \
  "$BASE/api/projects/$PROJECT_ID/runs/$RUN_ID/revise" \
  -H 'Content-Type: application/json' \
  -d '{"feedback":"补充锁死期间的纸质记录细节"}'
```

预期：

- approve：`state=APPROVED`、`status=approved`、正文更新。
- reject：`state=REJECTED`、`status=rejected`、正文不变。
- revise：HTTP 202，完成后再次进入 `WAIT_HUMAN_APPROVAL`，versions 增加一条。
- 对 active chapter 再次创建 run：HTTP 409。

## 15. Compatibility

- 未修改 `POST /api/chapters/{id}/generate`。
- 未删除或替换 WritingTask、GenerationRun、`chapter_pipeline.py`。
- 旧 API 回归测试继续通过。
- 未实现自动 UPDATE_STATE。
- 未写入 Canon。
- 未增加多章循环。
- 未进行前端大改。

## 16. Remaining Risks

1. 进程内串行队列仍不是持久化任务队列，进程重启只能把 running run 标为失败。
2. prompt 和原始模型响应仍完整保存在本地数据库，需要后续增加脱敏与清理策略。
3. 独立 CheckReport 表仍未实现，continuity report 继续保存在 run/step/call JSON 中。
4. 当前 revision 每次只执行一次模型调用，没有自动 retry 或 revision 次数上限。
5. SQLite partial index 方案针对当前本地单机产品；迁移到其他数据库时需提供对应方言索引。

# 最终结论

MVP 1.1 状态：通过

是否建议进入 MVP 2：是

原因：
1. 人工 approve/reject/revise 闭环已完成并通过 E2E。
2. active-run 约束已下沉到 SQLite 数据库并通过并发测试。
3. Alembic baseline、增量 migration、开发库实际迁移和回滚副本均已验证。
4. 空正文、schema 错误和模型超时均明确失败并保留日志。
5. 后端 17 项测试和前端 build 全部通过。

进入 MVP 2 时仍应保持：
1. Canon 更新必须继续经过人工确认。
2. 不引入多章自主循环，直到单章审批 UI 和运行恢复能力稳定。
3. 优先实现 Loop run、版本对比和审批的轻量前端，不扩大 Agent 数量。
