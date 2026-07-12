# API 设计

所有业务路由使用 `/api` 前缀。

## 项目与小说

- `POST /api/projects`
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `POST /api/novels`
- `GET /api/novels/{novel_id}`
- `PATCH /api/novels/{novel_id}`

## 章节

- `POST /api/chapters`
- `GET /api/novels/{novel_id}/chapters`
- `GET /api/chapters/{chapter_id}`
- `PATCH /api/chapters/{chapter_id}`
- `POST /api/chapters/{chapter_id}/generate`
- `POST /api/chapters/{chapter_id}/summarize`
- `POST /api/chapters/{chapter_id}/review`
- `POST /api/chapters/{chapter_id}/character-state-update`
- `GET /api/chapters/{chapter_id}/context-preview?budget=6000`

模型操作返回 `202 WritingTask`。客户端通过任务接口轮询；章节生成成功后，服务端自动创建一个
`chapter_summary` 任务。

## 角色与世界规则

- `POST /api/characters`
- `GET /api/novels/{novel_id}/characters`
- `PATCH /api/characters/{character_id}`
- `DELETE /api/characters/{character_id}`
- `POST /api/world-rules`
- `GET /api/novels/{novel_id}/world-rules`
- `PATCH /api/world-rules/{rule_id}`
- `DELETE /api/world-rules/{rule_id}`

## 模型与任务

- `POST /api/model-providers`
- `GET /api/model-providers`
- `PATCH /api/model-providers/{provider_id}`
- `POST /api/model-providers/{provider_id}/test`
- `GET /api/writing-tasks?chapter_id=...`
- `GET /api/writing-tasks/{task_id}`
- `POST /api/writing-tasks/{task_id}/pause`
- `POST /api/writing-tasks/{task_id}/retry`

`provider_type` 可为 `llama_cpp`、`ollama`、`koboldcpp`、`text_generation_webui`、
`openai_compatible` 或 `cloud_openai_compatible`。

## 运行、状态与模板

- `GET /api/chapters/{chapter_id}/generation-runs`
- `GET /api/generation-runs/{run_id}`
- `GET /api/chapters/{chapter_id}/reviews`
- `GET /api/novels/{novel_id}/canon-state`
- `PATCH /api/novels/{novel_id}/canon-state`
- `GET /api/prompt-templates`
- `PATCH /api/prompt-templates/{template_id}`

## 导出与健康检查

- `GET /api/novels/{novel_id}/export/markdown`
- `GET /api/health`
