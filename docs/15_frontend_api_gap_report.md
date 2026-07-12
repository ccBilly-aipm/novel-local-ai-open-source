# 前端 API 缺口报告

## 1. 当前接口核对

| 能力 | 当前状态 | 接口 |
| --- | --- | --- |
| 创建 Loop Run | 已有 | `POST /api/projects/{project_id}/chapters/{chapter_id}/run` |
| 查询 Run Detail | 已有 | `GET /api/projects/{project_id}/runs/{run_id}` |
| Approve | 已有 | `POST /api/projects/{project_id}/runs/{run_id}/approve` |
| Reject | 已有 | `POST /api/projects/{project_id}/runs/{run_id}/reject` |
| Revise | 已有 | `POST /api/projects/{project_id}/runs/{run_id}/revise` |
| 查询 ChapterVersion | 部分 | Run Detail 内嵌 `versions`；无独立版本接口 |
| 项目内 Run 列表 | 本轮已补 | `GET /api/projects/{project_id}/runs` |
| 全局 Run 列表 | 本轮已补 | `GET /api/loop-runs` |
| 章节 active/waiting run | 本轮已补 | `GET /api/chapters/{chapter_id}/loop-runs`，由 `active_slot` 判断 |
| Provider test | 已有 | `POST /api/model-providers/{id}/test` |
| Provider list | 已有 | `GET /api/model-providers` |
| Provider role assignment | 缺失 | 需要 settings API |

## 2. 本轮最小后端补丁

为避免前端遍历项目和章节拼凑 run，本轮增加：

```text
GET /api/loop-runs?status=&project_id=&chapter_id=&limit=
GET /api/projects/{project_id}/runs
GET /api/chapters/{chapter_id}/loop-runs
```

返回轻量 `ChapterLoopRunSummary`：

- run/project/novel/chapter/provider ID。
- project、novel、chapter、provider、model 名称。
- state/status/active_slot/error_code。
- current_version_id/approved_version_id。
- created/updated/started/finished/decided time。

列表不返回完整 prompt、response、assembled_context 或 version 正文，避免首页负载过大。

## 3. 仍保留的缺口

### ChapterVersion 独立查询

当前 Run Detail 足以支持本轮 VersionPreview。完整 Versions 页面仍需：

```text
GET /api/chapters/{chapter_id}/versions
GET /api/chapter-versions/{version_id}
```

### Provider Role Assignment

建议：

```text
GET /api/settings/model-roles
PATCH /api/settings/model-roles

{
  "writer_provider_id": "...",
  "checker_provider_id": "...",
  "summary_provider_id": "..."
}
```

当前 runner 同一 run 使用一个 provider 完成 writer 与 checker，因此真正分离角色还需要 workflow 配置。前端本轮只保存浏览器级 Writer 偏好，并明确标注：

- 不是后端全局配置。
- 当前 Checker 继承本次 Run Provider。
- Summary 仍由旧任务手动选择。

### Provider Test Diagnostics

当前响应：

```json
{
  "ok": false,
  "message": "...",
  "latency_ms": 123,
  "response_preview": ""
}
```

没有结构化 category、target URL、model 或 tested_at。前端本轮结合当前 Provider 表单展示 target/model，并对 message 做保守分类。后端后续建议返回：

```json
{
  "ok": false,
  "category": "MODEL_TIMEOUT",
  "target_url": "...",
  "model": "...",
  "latency_ms": 5000,
  "raw_error": "...",
  "suggested_fixes": []
}
```

### Run Retry / Cancel

当前无 Loop retry/cancel API。本轮 Failed 页面不提供伪造 Retry，只提供：

- View Logs。
- 返回章节。
- 修复 Provider/Prompt 后创建新 Run。

## 4. 不允许的前端替代方案

1. 遍历全部项目和章节推算全局 runs。
2. 用 localStorage 伪造后端 role assignment 真相。
3. continuity passed 后自动调用 approve。
4. 直接 PATCH Chapter 发布 draft。
5. 用按钮 disabled 代替数据库 active-run 约束。
6. 把缺失的独立 Version API 假装成已存在。
