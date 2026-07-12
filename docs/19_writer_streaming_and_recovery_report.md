# Writer 流式生成与恢复报告

## 1. 问题复现

真实本地模型 Run：

```text
run_id: 31982f1b-926a-4be7-b306-5038daddac0d
provider: LM Studio · qwen3.6-27b-crack
failed_step: WRITE_DRAFT
error_code: JSON_PARSE_ERROR
```

模型实际返回了 1371 字符，其中 `draft_markdown` 是完整可读正文，但输出在
`scene_breakdown` 数组处截断，导致整个 JSON envelope 无法被 `json.loads` 解析。

旧实现因此丢弃可用正文并把 Run 标记为失败。

## 2. 根因分析

`DraftWriterAgent` 和 `RevisionWriterAgent` 原本继承 `StructuredAgent`：

```text
模型输出 -> JsonGuard -> Pydantic DraftWriterOutput -> ChapterVersion
```

小说正文长、引号和换行多，本地模型还可能受 token 截断、thinking 模式和采样影响。
要求正文与元数据共同形成严格 JSON，会把“正文生成质量”和“JSON 序列化稳定性”绑定在一起。

正文不是结构化抽取任务。Draft Writer 应输出文本，代码负责补充 chapter/run/version 等元数据。

## 3. 输出模式拆分

新增：

```text
AgentOutputMode.TEXT_STREAM
AgentOutputMode.TEXT_FINAL
AgentOutputMode.JSON_SCHEMA
```

以及：

- `AgentSpec`
- `PromptSpec`
- `call_agent()`
- `TextAgent`
- `DraftTextGuard`

当前分配：

| Agent | 输出模式 |
| --- | --- |
| draft_writer | TEXT_STREAM，Provider 不支持时降级 TEXT_FINAL |
| revision_writer | TEXT_STREAM，Provider 不支持时降级 TEXT_FINAL |
| continuity_checker | JSON_SCHEMA |

后续 character/state/timeline 等结构化 Agent 应继续使用 JSON_SCHEMA。

## 4. Draft Writer 改造

`draft_writer.md` 与 `revision_writer.md` 现在要求：

- 只输出章节正文 Markdown。
- 不输出 JSON。
- 不输出代码块、解释、分析过程或检查报告。
- 正文直接开始。

兼容顺序：

1. 如果是合法旧 JSON，提取 `draft_markdown`。
2. 如果 JSON 损坏但可提取 `draft_markdown`，使用文本兜底。
3. 如果不是 JSON，完整输出作为 Markdown。
4. 使用 `DraftTextGuard` 校验。
5. 通过后创建不可变 ChapterVersion。

文本兜底写入 warning：

```text
DRAFT_JSON_FALLBACK_USED
```

## 5. DraftTextGuard

校验：

- 非空。
- 最低字符数。
- 模型拒绝。
- 明显 Provider/错误信息。
- Prompt/System 指令泄露。
- 代码块或无法安全提取的 JSON wrapper。

错误码：

```text
EMPTY_CONTENT
TOO_SHORT
MODEL_REFUSAL
PROMPT_LEAK
INVALID_DRAFT_TEXT
```

Writer 不再产生新的 `JSON_PARSE_ERROR`。该错误只来自 JSON_SCHEMA Agent。

## 6. 自动兜底

### 文本兜底

旧 JSON 或损坏 JSON 中的正文可直接生成 ChapterVersion，并记录 guard warning。

### 自动重试

空、过短、拒写或无效文本会自动重试一次。每次尝试都是独立 ModelCall，记录：

- attempt。
- error_code。
- response。
- characters。
- guard warning。

### JSON repair

JSON_SCHEMA Agent 的处理顺序：

1. 去除 Markdown fence。
2. 从前后解释中提取第一个 JSON object。
3. `json.loads`。
4. Pydantic 校验。
5. 失败后调用一次 `*_json_repair` ModelCall。
6. 再失败则保留首次根因错误码。

Draft Writer 不使用 JSON repair。

## 7. 流式实现

本轮实现真实 Provider streaming，同时采用 Run detail polling 推送到前端，没有新增 SSE。

支持流式：

- OpenAI-compatible chat completions。
- LM Studio chat/completions。
- LM Studio `force_no_think` text completions。
- Ollama chat。

其他 Adapter 自动降级 `TEXT_FINAL`。

增量持续写入：

- `ChapterLoopRun.draft_preview`
- `draft_preview_updated_at`
- `draft_chars`
- `is_streaming`
- `stream_supported`
- 当前 `ModelCall.response`

前端每秒轮询 Run detail，因此浏览器断开不会中断后端生成。

## 8. 真实流式验证

使用已加载的：

```text
LM Studio · qwen3.6-27b-crack
```

创建临时验证项目并运行 text-first Writer，观察到：

```text
WRITE_DRAFT: 245 -> 257 -> ... -> 544 -> 570 chars
is_streaming: true
stream_supported: true
Writer duration: 35379 ms
Writer attempts: 1
draft_warning: empty
final state: WAIT_HUMAN_APPROVAL
```

生成了 570 字符纯 Markdown ChapterVersion。连续性检查耗时 5367 ms 并成功。

验证前：

```text
Chapter.content length: 0
Chapter.status: outlined
Chapter.version: 1
```

说明生成和检查没有覆盖正式正文。临时验证项目随后已删除。

## 9. 真实旧 Run 恢复

对原失败 Run 调用：

```text
POST /api/projects/44335563-2d46-4301-bc11-ebcdaeafd2fd/
runs/31982f1b-926a-4be7-b306-5038daddac0d/recover-draft
```

结果：

- 从 1371 字符 raw output 提取 840 字符正文。
- 新建 ChapterVersion v1。
- 写入 `RECOVER_DRAFT` RunStep。
- `chapter_content_updated=false`。
- 进入 CHECK_CONTINUITY。
- LM Studio Checker 实际运行成功。
- 最终进入 `WAIT_HUMAN_APPROVAL`。

旧失败 `WRITE_DRAFT/JSON_PARSE_ERROR` 日志仍保留，没有静默改写历史。

## 10. 新增 API

```text
GET  /api/projects/{project_id}/runs/{run_id}/artifacts/raw-output
POST /api/projects/{project_id}/runs/{run_id}/recover-draft
POST /api/projects/{project_id}/runs/{run_id}/rerun
```

Run detail 新增：

- `current_step`
- `draft_preview`
- `draft_preview_updated_at`
- `draft_chars`
- `is_streaming`
- `stream_supported`
- `draft_attempts_json`
- `draft_warning`
- `raw_output_available`
- `recoverable_raw_output`
- `partial_output_available`
- `failed_step`
- `user_facing_error`
- `technical_error`
- `recovery_actions`

## 11. 前端改造

Run Detail 在 WRITE_DRAFT 期间显示：

- 当前模型。
- 已生成字符数。
- 运行耗时。
- 最后更新时间。
- 实时正文预览。
- 可关闭的自动滚动。
- Provider 不支持 streaming 时的明确降级提示。

失败恢复区按后端能力显示：

- 查看原始输出。
- 保存原始输出为候选草稿。
- 重新生成。
- 检查模型配置。
- 复制诊断信息。

Raw output 默认不展开全文。Recover 前显示前 1000 字并要求确认。

Advanced Logs 新增 parsed/guard、Provider raw payload、tokens、chars、延迟和草稿重试记录。

## 12. 新增文件

- `services/api/app/services/draft_text_guard.py`
- `services/api/migrations/versions/6f75c1ad2931_writer_draft_buffer_and_stream_status.py`
- `docs/19_writer_streaming_and_recovery_report.md`

## 13. 主要修改文件

- `services/api/app/agents/base.py`
- `services/api/app/agents/writer.py`
- `services/api/app/agents/checkers.py`
- `services/api/app/providers/base.py`
- `services/api/app/providers/adapters.py`
- `services/api/app/services/json_guard.py`
- `services/api/app/services/run_logger.py`
- `services/api/app/models/loop_entities.py`
- `services/api/app/schemas/loop.py`
- `services/api/app/routers/loop_runs.py`
- `services/api/app/workflow/runner.py`
- `services/api/app/prompts/novel_loop/draft_writer.md`
- `services/api/app/prompts/novel_loop/revision_writer.md`
- `services/api/tests/test_loop_stability.py`
- `services/api/tests/test_loop_runner.py`
- `services/api/tests/test_loop_mvp_e2e.py`
- `apps/web/src/types.ts`
- `apps/web/src/features/runs/RunDetailPage.tsx`
- `apps/web/src/components/ProjectWorkspaceShell.tsx`

## 14. 测试结果

后端：

```text
22 passed in 16.20s
```

新增覆盖：

- 纯 Markdown Draft 成功。
- 损坏 JSON 中正文 fallback 成功。
- 空文本返回 EMPTY_CONTENT。
- 错误文本返回 INVALID_DRAFT_TEXT。
- Writer 不产生 JSON_PARSE_ERROR。
- Checker 非法 JSON 触发 repair，失败后保留 JSON_PARSE_ERROR。
- recover-draft 创建 ChapterVersion。
- recover-draft 不覆盖 Chapter.content。
- Run detail 返回用户错误与恢复动作。

前端：

```text
npm run build
41 modules transformed
build passed
```

项目没有 Playwright/e2e script，本轮未声称运行前端自动化测试。

浏览器冒烟：

- 恢复后的真实 Run 页面可打开。
- `RECOVER_DRAFT` 时间线可见。
- ChapterVersion、Continuity Report 和审批区可见。
- 控制台错误为 0。

## 15. 部署与备份

Migration：

```text
6f75c1ad2931
```

部署前备份：

```text
~/Library/Application Support/NovelLocalAI/data/
novel_local_ai.before-writer-recovery-20260612-115717.db
```

应用运行于：

```text
http://127.0.0.1:5173/
```

## 16. 当前风险

1. 前端采用 polling，不是 SSE；1 秒粒度足够 MVP，但请求次数更高。
2. Streaming 写 SQLite 做了字符/时间批处理，超高并发不是当前目标。
3. JSON repair 仍依赖同一 Provider；未来可为 Checker 单独指定稳定模型。
4. 损坏 JSON 的文本提取是保守兼容层，无法安全识别时仍会失败。
5. Run detail 仍内嵌完整 ModelCall，超长日志未来应拆分页接口。

## 17. 下一轮建议

1. 为 Checker 增加独立 Provider role，并优先使用低温度结构化模型。
2. 增加 SSE events，降低 polling 请求并传递 step/delta/check 事件。
3. 增加前端 Playwright E2E，使用 mock streaming Provider 覆盖实时预览和 recover。
4. 增加独立 RunArtifact 表，支持多种诊断产物和分页。
5. 增加 Version Diff，帮助用户比较原稿、修订稿与正式正文。
