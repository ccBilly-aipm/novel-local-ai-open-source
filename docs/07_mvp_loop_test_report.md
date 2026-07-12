# Loop Agent MVP 双轮测试报告

## 1. 测试日期

- 执行日期：2026-06-12
- 时区：Asia/Shanghai
- 最新证据生成时间：2026-06-12 10:30:38 +08:00
- 结构化证据文件：`/tmp/novel_loop_mvp_evidence.json`

## 2. Git 与工作区状态

- 分支：`main`
- 当前仓库无法解析 `HEAD`，没有可引用的 commit hash。
- `git status --short` 显示 `.gitignore`、`README.md`、`apps/`、`backend/`、`data/`、`docs/`、`scripts/`、`services/` 均为未跟踪内容。
- 结论：本报告对应未提交、非干净工作区，不能仅凭 commit 复现。

## 3. 测试环境

| 项目 | 实际值 |
| --- | --- |
| 操作系统 | macOS 26.5.1 (25F80), arm64 |
| Python | 3.9.6 |
| Node.js | v25.9.0 |
| npm | 11.12.1 |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | React + TypeScript + Vite 8.0.16 |
| 测试客户端 | FastAPI `TestClient` |

## 4. 后端启动方式

生产开发启动方式来自 `README.md`：

```bash
cd services/api
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

本次自动化测试通过 FastAPI `TestClient` 启动应用 lifespan、串行 Loop 队列和真实 ASGI 路由，没有绕过 `create_loop_run()` 或 `NovelLoopRunner.execute()`。

## 5. 前端启动方式

```bash
cd apps/web
npm run dev
```

本次以 API 工作流为主，没有启动交互式前端；已执行生产构建。

## 6. Provider 情况

- 自动化 Provider：测试内真实 HTTP mock OpenAI-compatible 服务。
- 最新测试监听端口：`127.0.0.1:55739`，API base URL 为 `http://127.0.0.1:55739/v1`。
- 模型名：`tidal-city-mock`。
- Draft Writer 和 Continuity Checker 都经过正式 provider adapter 发出 HTTP 请求。
- 本轮不依赖 LM Studio 或其他真实本地模型；真实模型测试属于 optional manual test，未计入通过结论。

## 7. 数据库位置

- 测试数据库：`services/api/tests/test_novel.db`
- 测试环境变量：`NOVEL_AI_DB_URL=sqlite:///services/api/tests/test_novel.db`
- 默认开发数据库：`data/novel_local_ai.db`
- 双轮测试使用隔离测试数据库，没有写入默认开发数据库。

## 8. Round 1 Normal Path

### 输入数据

- 项目：`Loop Agent MVP Test Novel Round 1`
- 小说：`潮汐城午夜异常 Round 1`
- 角色：林澈、许岚
- 世界规则：
  - 电子门在 00:00 到 00:07 锁死。
  - 林澈没有上层行政区权限。
  - 许岚不能提前知道林澈的发现。
  - 潮汐心脏是城市核心能源。
- 章节：`第一章 午夜锁死`
- 初始正文：`人工占位正文：Loop 初稿不得覆盖这里。`
- 章节目标：林澈留在下层记录锁死异常，不遇见许岚，章末发现上层加密指令。

### 实际执行命令

```bash
cd services/api
/usr/bin/trash /tmp/novel_loop_mvp_evidence.json 2>/dev/null || true
.venv/bin/pytest tests/test_api.py tests/test_loop_mvp_e2e.py -q -s
```

测试通过 `TestClient` 实际调用：

```http
POST /api/projects/{project_id}/chapters/{chapter_id}/run
Content-Type: application/json

{
  "provider_id": "<mock-provider-id>",
  "context_budget": 2400,
  "options": {}
}
```

随后轮询：

```http
GET /api/projects/{project_id}/runs/{run_id}
```

### 创建结果

- HTTP：`202 Accepted`
- run_id：`9f58d05b-e370-437e-a6b9-badc88c63ad2`
- 初始状态：`LOAD_PROJECT / pending`
- 最终状态：`WAIT_HUMAN_APPROVAL / waiting`
- 最终 version_id：`4b514c86-5b09-4e7c-80de-0717a7b97eca`
- 运行开始：`2026-06-12T02:30:38.558011` UTC
- 运行结束：`2026-06-12T02:30:38.609854` UTC

### 状态变化

| 顺序 | 状态 | 开始时间 UTC | 结束时间 UTC | 结果 | 产物 |
| --- | --- | --- | --- | --- | --- |
| 1 | LOAD_PROJECT | 02:30:38.561244 | 02:30:38.564324 | completed | 项目、小说、章节、Provider 信息 |
| 2 | ASSEMBLE_CONTEXT | 02:30:38.566391 | 02:30:38.571068 | completed | 654 字符上下文，估算 486 tokens |
| 3 | WRITE_DRAFT | 02:30:38.572426 | 02:30:38.590845 | completed | ChapterVersion v1 |
| 4 | CHECK_CONTINUITY | 02:30:38.592235 | 02:30:38.607583 | completed | 结构化 continuity report |
| 5 | WAIT_HUMAN_APPROVAL | 02:30:38.608869 | 02:30:38.609423 | completed | `requires_human_approval=true` |

实际状态链：

```text
LOAD_PROJECT
-> ASSEMBLE_CONTEXT
-> WRITE_DRAFT
-> CHECK_CONTINUITY
-> WAIT_HUMAN_APPROVAL
```

### 模型调用

| Agent / Prompt | Provider | 耗时 | JSON 校验 | 重试 |
| --- | --- | ---: | --- | --- |
| `draft_writer` / `draft_writer.md` | tidal-city-mock | 12 ms | 成功 | 0；当前未实现自动重试 |
| `continuity_checker` / `continuity_checker.md` | tidal-city-mock | 11 ms | 成功 | 0；当前未实现自动重试 |

### 生成结果

- ChapterVersion：`4b514c86-5b09-4e7c-80de-0717a7b97eca`
- version_number：`1`
- kind：`draft`
- 字符数：`138`
- SHA-256：`776dc3c551411c6c75c9039f95a7132ce308c20b5990967fa7f1dd312986b947`
- 内容满足样本约束：林澈留在下层；00:00 锁死、00:07 恢复；未遇见许岚；章末发现上层加密指令。

### 检查结果

```json
{
  "passed": true,
  "severity": "none",
  "issues": []
}
```

- Continuity Checker：通过
- issue 数量：0
- severity：`none`

### 数据库验证

| 表/实体 | 本轮记录数 |
| --- | ---: |
| ChapterLoopRun | 1 |
| RunStep | 5 |
| ModelCall | 2 |
| ChapterVersion | 1 |

- `Chapter.content` 测试前后均为人工占位正文。
- 初稿只写入不可变 ChapterVersion，没有覆盖正式正文。

### Round 1 结论

**通过。** 正常路径完成五个状态，生成可审查版本，保存模型与步骤日志，并停在人工确认状态。

## 9. Round 2 Error And Boundary Path

### 场景 A：重复 active run

测试方法：mock Draft Writer 延迟约 0.8 秒，在第一个 run 仍处于 active 状态时，对同一章节再次调用 run API。

预期：

- 第二次请求返回 409。
- 不创建第二个 active run。

实际：

- 第一次请求：`202 Accepted`
- 第一次 run_id：`6655253c-3793-4c54-ad7a-4ea84bfb1801`
- 第二次请求：`409 Conflict`
- 返回：

```json
{
  "detail": "Chapter already has an active Loop run"
}
```

- 数据库中该章节 run 数量：1
- 第一个 run 最终正常进入 `WAIT_HUMAN_APPROVAL`。

结论：**通过。**

### 场景 B：Continuity Checker 返回非法 JSON

测试输入：

```text
{"passed": true, "severity": "none", "issues": [
```

预期：

- JsonGuard 报 JSON_PARSE_ERROR。
- CHECK_CONTINUITY step 失败。
- ModelCall 失败并保留原始输出。
- run 进入 FAILED，不能静默成功。
- 不生成伪造的空检查报告。

实际：

- 创建请求：`202 Accepted`
- run_id：`48d25ce5-723d-46c9-9099-93944d931df1`
- 最终 state/status：`FAILED / failed`
- error_code：`JSON_PARSE_ERROR`
- 错误：

```text
Model output is not valid JSON: Expecting value: line 1 column 49 (char 48)
```

- `CHECK_CONTINUITY` RunStep：`failed / JSON_PARSE_ERROR`
- `continuity_checker` ModelCall：`failed`
- `parsed_json_valid`：false
- 原始非法响应保存在 `ModelCall.response`
- `continuity_report_json` 没有被写入伪造结果
- Draft ChapterVersion 仍保留，便于人工诊断
- `Chapter.content` 未变化

数据库记录：

| 表/实体 | 本场景记录数 |
| --- | ---: |
| ChapterLoopRun | 1 |
| RunStep | 4 |
| ModelCall | 2 |
| ChapterVersion | 1 |

结论：**通过。**

### 场景 D：旧接口回归

- 全量 pytest 包含 `tests/test_api.py` 中旧 `/api/chapters/{id}/generate` 流程。
- 旧接口测试通过。
- 新 Loop 路由未替换旧 `generate_chapter()` 和 `chapter_pipeline.py`。

结论：**通过。**

### 未执行的可选场景

- 场景 C“模型返回空正文”：本轮未增加独立 E2E 场景。
- `ChapterVersionManager.append_draft()` 已拒绝空内容，但尚未由本次双轮 E2E 单独验证错误码和全链路日志。

### Round 2 结论

**通过。** 必测 A、B 均符合预期，D 由全量回归覆盖；可选 C 未执行。

## 10. Pytest 输出摘要

实际命令：

```bash
cd services/api
.venv/bin/pytest -q
```

实际结果：

```text
......... [100%]
```

- 退出码：0
- 通过：9
- 失败：0

## 11. 前端 Build 输出摘要

实际命令：

```bash
cd apps/web
npm run build
```

实际结果：

```text
> tsc --noEmit && vite build
✓ 25 modules transformed.
dist/index.html                  0.45 kB
dist/assets/index-D_12xmMA.css 17.86 kB
dist/assets/index-DlG_KzP0.js 206.65 kB
✓ built in 290ms
```

- 退出码：0
- TypeScript 检查：通过，已包含在 build 中。
- 独立 `npm run typecheck`：不存在该命令。
- `npm run lint`：不存在该命令。

## 12. 新旧接口兼容性

- 新接口：`POST /api/projects/{project_id}/chapters/{chapter_id}/run`
- 查询接口：`GET /api/projects/{project_id}/runs/{run_id}`
- 旧接口：`POST /api/chapters/{chapter_id}/generate`
- 旧实现 `app/routers/chapters.py::generate_chapter()` 保留。
- 旧 `WritingTask`、`GenerationRun`、`app/pipelines/chapter_pipeline.py` 保留。
- 全量回归通过，未观察到新 Loop 对旧生成行为的回归。

## 13. 数据库写入验证

正常路径实际写入：

- 1 条 ChapterLoopRun。
- 5 条 RunStep。
- 2 条 ModelCall。
- 1 条不可变 ChapterVersion。
- 结构化 continuity report 写入 `chapter_loop_runs.continuity_report_json`。

JSON 失败路径实际写入：

- 失败状态、错误码和错误信息写入 ChapterLoopRun。
- 失败状态和错误码写入 CHECK_CONTINUITY RunStep。
- 原始响应、耗时、错误码写入 continuity_checker ModelCall。
- 不写入伪造 continuity report。

## 14. Chapter.content 验证

正常路径与 JSON 失败路径均验证：

```text
before = 人工占位正文：Loop 初稿不得覆盖这里。
after  = 人工占位正文：Loop 初稿不得覆盖这里。
```

结论：**没有误覆盖。**

## 15. ChapterVersion 验证

- 正常路径生成 1 条 `kind=draft` 的 ChapterVersion。
- JSON 检查失败发生在初稿生成之后，因此仍保留 1 条可诊断的 Draft ChapterVersion。
- `app/models/loop_entities.py::reject_chapter_version_update()` 阻止更新已存在版本。
- `app/services/version_manager.py::ChapterVersionManager.append_draft()` 采用 append-only 版本号。

结论：**已生成且具备应用层不可变保护。**

## 16. CheckReport 验证

- 结构化检查结果已生成并保存。
- 当前**未实现独立 CheckReport 表、模型或查询 API**。
- 当前存储位置：
  - `chapter_loop_runs.continuity_report_json`
  - `run_steps.output_json`
  - `model_calls.parsed_json`

结论：语义上的检查报告存在；独立、可版本化的 CheckReport 实体未实现。

## 17. RunLogger 完整性

`app/services/run_logger.py::RunLogger` 实际记录：

- RunStep：run_id、sequence、state、status、input_json、output_json、error_code、error、开始/结束时间。
- ModelCall：run_id、step_id、provider_id、agent_name、prompt、options_json、response、parsed_json、raw_response_json、token 数、duration_ms、status、error_code、error、开始/结束时间。

正常路径 5 个 step 全部存在；失败路径保留 4 个 step，失败发生后没有伪造 WAIT_HUMAN_APPROVAL step。

结论：**本轮所需日志完整。**

## 18. JsonGuard 验证

`app/services/json_guard.py::JsonGuard.parse_and_validate()`：

- 空响应抛出 `EMPTY_MODEL_OUTPUT`。
- `json.loads()` 失败抛出 `JSON_PARSE_ERROR`。
- Pydantic 校验失败抛出 `SCHEMA_VALIDATION_ERROR`。

本轮用损坏 JSON 实际触发 `JSON_PARSE_ERROR`，错误向 RunStep、ModelCall 和 ChapterLoopRun 传播，run 最终为 FAILED。

结论：**已生效，没有静默吞错。**

## 19. 当前通过项

1. 创建完整的潮汐城最小测试数据。
2. 新 Loop API 返回 run_id 并可查询详情。
3. 五状态正常推进。
4. 上下文包含故事、章节目标、角色状态和世界规则。
5. Draft Writer 生成 Pydantic 校验后的结构化结果。
6. 初稿写入 ChapterVersion。
7. Continuity Checker 输出通过 Pydantic 校验。
8. RunStep 与 ModelCall 日志完整。
9. 正常路径进入 WAIT_HUMAN_APPROVAL。
10. `Chapter.content` 未被覆盖。
11. 同章节重复 active run 返回 409。
12. 非法 JSON 导致明确 FAILED 和 JSON_PARSE_ERROR。
13. 旧 generate API 回归通过。
14. 全量 pytest 与前端 build 通过。

## 20. 当前失败项

- 本次已执行的断言没有失败。
- 产品能力层面的缺口见“未实现项”，不应误写为测试通过。

## 21. 未实现项

1. 独立 CheckReport 数据模型和查询 API。
2. 人工 approve/reject/revise API；当前只能停在 WAIT_HUMAN_APPROVAL。
3. 自动 UPDATE_STATE 和 Canon 提交。
4. 空正文场景的全链路 E2E 覆盖。
5. 多 Provider fallback。
6. ModelCall 自动重试和 retry_count。
7. 多进程/多实例下的原子 active-run 约束。
8. Alembic 数据库迁移。
9. 前端 Loop Run、日志和审批界面。
10. 真实 LM Studio 模型的手工验收记录。

## 22. 风险清单

1. **并发竞态高风险**：`create_loop_run()` 先查询再插入，缺少数据库唯一约束；多进程请求可能同时通过检查。
2. **数据库升级高风险**：当前依赖 `create_all`，缺少 Alembic migration，已有用户数据库升级不可审计。
3. **审批闭环高风险**：WAIT_HUMAN_APPROVAL 已落状态，但没有 approve/reject/revise 端点，版本不能正式晋升。
4. **日志敏感信息风险**：完整 prompt、response、raw response 持久化，未来接入云模型或导入私人小说时需脱敏和清理策略。
5. **队列可靠性风险**：当前为进程内串行队列；进程退出、热重载和多 worker 部署下的恢复语义有限。
6. **报告可查询性风险**：continuity report 嵌在 JSON 字段中，不利于独立版本、筛选、审计和多 checker 扩展。

## 23. 下一轮修复建议

1. 为 active run 增加数据库级原子约束或事务锁，并补多连接竞态测试。
2. 建立 Alembic baseline 和 Loop 表迁移。
3. 实现 approve/reject/revise API；只有 approve 才允许更新正式章节或 Canon。
4. 增加空正文、schema mismatch、provider timeout 三条 E2E。
5. 将 continuity 结果升级为独立 CheckReport 或明确的 append-only checker result。
6. 为 ModelCall 增加 attempt/retry_count、超时分类和敏感信息清理策略。
7. 在完成以上门槛后再接前端 Loop 控制台。

## 24. 是否建议进入 MVP 2

当前不建议直接进入大范围 MVP 2 功能开发。可以先做一轮小型稳定性补丁，优先补数据库迁移、原子 active-run 约束和人工审批接口，再进入前端 Loop 工作台与更多 checker。

# 最终结论

MVP 1 状态：部分通过

是否建议进入 MVP 2：否

原因：
1. 正常路径、异常 JSON、重复 active run、日志、版本隔离和旧接口回归均实际通过。
2. 独立 CheckReport、人工审批闭环和数据库迁移仍未实现。
3. active-run 防重目前不是数据库原子约束，多进程环境仍存在竞态风险。

必须先修的问题：
1. 增加数据库级 active-run 并发保护。
2. 建立 Alembic migration baseline。
3. 实现 approve/reject/revise 的最小人工确认闭环。

可以延后的事项：
1. 多 Provider fallback。
2. 自动 Canon/人物状态更新。
3. 多章循环、复杂 Agent 和 GraphRAG。
