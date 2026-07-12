# 数据模型

所有主键使用 UUID 字符串，时间使用 UTC ISO 时间。复杂但尚未形成稳定查询需求的数据先用
JSON 文本保存；后续 migration 可拆表。

| 实体 | 关键字段 | MVP 简化 |
|---|---|---|
| Project | name, description | 单用户，无 owner |
| Novel | project_id, title, synopsis, story_outline, style_guide, forbidden_content | 一个项目可有多本小说 |
| Chapter | novel_id, order_index, title, content, summary, status, version | 树结构仅保留 parent_id，UI 先展示平铺排序 |
| ChapterOutline | chapter_id, goal, outline_content, required_plot_points, character_ids | JSON 保存 ID 列表 |
| SceneOutline | chapter_outline_id, order_index, goal, outline_content | 建表，MVP 不提供完整 UI |
| Character | novel_id, name, role, description, arc, current_state, relationships | state/relationships 为 JSON 文本 |
| Location | novel_id, name, description, current_state | 建表，MVP UI 后置 |
| WorldRule | novel_id, name, description, category, priority | priority 用于上下文选择 |
| TimelineEvent | novel_id, chapter_id, title, story_time, description | 不做自动时间归一化 |
| PlotThread | novel_id, name, description, status, related_chapter_ids | 关联先用 JSON |
| Foreshadowing | novel_id, description, status, planted/resolved chapter | 不做关系图 |
| CanonState | novel_id, character_states, relationships, unresolved_conflicts, key_events, progress_notes | JSON + 人工确认 |
| WritingTask | chapter_id, operation, status, provider_id, progress, pause_requested | 单 worker |
| GenerationRun | task_id, prompt, response, options, tokens, duration, status, error | 完整审计 |
| ReviewResult | chapter_id, score, checks, suggestions, raw_response | 建议不改正文 |
| ModelProvider | type, base_url, model, api_key, default_options, enabled | key 本地明文，后续 Keychain |
| PromptTemplate | key, template_text, output_schema, version, active | 启动时由文件 seed |

前后端类型分别位于 `services/api/app/schemas/entities.py` 与
`apps/web/src/types.ts`。关系数据库定义位于 `services/api/app/models/entities.py`。
