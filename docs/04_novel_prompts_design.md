# 小说 Loop Agent 提示词体系设计

可执行草稿：`backend/prompts/novel_prompts_draft.py`

## 1. 统一设计规范

### Prompt 分层

每个 Agent Prompt 分为：

1. `system_prompt`：角色、任务边界、硬规则和失败行为。
2. `user_template`：本次结构化输入。
3. `output_schema`：由代码执行的 JSON Schema/Pydantic schema。
4. `default_model_params`：Agent 级默认参数，仍可由 Provider policy 覆盖。

### 统一硬规则

- 除正文所在字段外，禁止输出无结构散文。
- 只输出一个 JSON 对象，不输出 Markdown fence。
- 不虚构 ID。
- 缺少输入时返回合法空结构和风险说明，不能自行补事实。
- 数组为空时输出 `[]`。
- 模型输出先进入 staging，不直接写数据库 Canon。

### 失败处理

代码按以下顺序处理：

1. 清除常见 JSON fence。
2. 直接解析。
3. 使用目标 schema 校验。
4. 若解析失败，执行一次 JSON repair，只提供原始输出、schema 和错误。
5. repair 仍失败则当前 step 标记 `PARSE_ERROR`。
6. Draft/Revision 正文为空时标记 `EMPTY_CONTENT`。
7. 不允许用默认空对象把失败伪装为成功。

## 2. Prompt 总览

| Prompt | 角色 | 主要输出 | 推荐温度 |
|---|---|---|---:|
| story_framework_builder | 故事架构师 | 故事框架 JSON | 0.35 |
| character_model_builder | 人物模型设计师 | 人物模型 JSON | 0.30 |
| timeline_builder | 时间线编译器 | events JSON | 0.15 |
| chapter_planner | 章节任务规划师 | ChapterPlan JSON | 0.25 |
| context_assembler_prompt | 上下文压缩器 | 压缩上下文 JSON | 0.10 |
| draft_writer | 章节正文作者 | draft_markdown JSON | 0.75 |
| continuity_checker | 连续性审计员 | CheckReport JSON | 0.10 |
| character_consistency_checker | 人物一致性审计员 | CheckReport JSON | 0.10 |
| plot_rhythm_checker | 节奏审计员 | 评分与 issue JSON | 0.15 |
| revision_writer | 章节修订作者 | revised_markdown JSON | 0.45 |
| state_updater | 故事状态抽取器 | 状态变化 JSON | 0.10 |
| reflection_agent | 运行复盘分析员 | 规则候选 JSON | 0.20 |

## 3. story_framework_builder

**角色**：严谨的长篇故事架构师。

**任务**：把想法整理为可执行框架，不写正文。

**输入字段**：

- `user_idea`
- `genre`
- `target_audience`
- `reference_works`
- `style_preferences`
- `forbidden_content`

**硬规则**：

- 参考作品只能用于抽象风格和结构，不复刻具体内容。
- 每项世界规则必须能产生剧情约束或代价。
- `risk_notes` 必须存在。

**边界**：角色和世界规则只是框架候选，后续由专门 Builder 确认。

**输出**：

```json
{
  "logline": "",
  "genre": "",
  "theme": "",
  "core_conflict": "",
  "world_rules": [],
  "main_characters": [],
  "story_arcs": [],
  "risk_notes": []
}
```

**失败行为**：输入不足时保留空字段，并把缺失项写入 `risk_notes`。

## 4. character_model_builder

**角色**：人物模型设计师。

**任务**：生成稳定的人物动机、语言特征、关系边和行为禁区。

**输入字段**：`character_seed`、`story_framework`、`existing_characters`。

**硬规则**：

- 不覆盖已确认事实。
- 关系只能引用已存在角色 ID。
- `forbidden_behaviors` 描述没有铺垫时不能发生的行为。

**边界**：不写人物登场正文，不推进剧情。

**输出**：

```json
{
  "character_id": "",
  "name": "",
  "role": "",
  "desire": "",
  "fear": "",
  "misbelief": "",
  "external_goal": "",
  "internal_arc": "",
  "speech_style": "",
  "relationship_edges": [],
  "forbidden_behaviors": []
}
```

**失败行为**：缺失 ID 时返回空字符串并由代码分配，不能让模型发明 UUID。

## 5. timeline_builder

**角色**：故事时间线编译器。

**任务**：把大纲、摘要和既有事件整理为时间顺序与因果链。

**输入字段**：`story_framework`、`chapter_summaries`、`existing_timeline`。

**硬规则**：

- 已发生和计划事件必须可区分。
- 无精确时间时使用相对时间。
- cause/effect 无证据时留空。

**边界**：不修改章节正文，不推测隐藏真相。

**输出**：

```json
{
  "events": [
    {
      "event_id": "",
      "time": "",
      "location": "",
      "characters": [],
      "event_summary": "",
      "cause": "",
      "effect": "",
      "status_change": []
    }
  ]
}
```

**失败行为**：时间冲突不擅自选择答案，应输出并列候选或问题记录供代码/人工处理。

## 6. chapter_planner

**角色**：章节任务规划师。

**任务**：创建一张可执行、可检查的单章任务卡。

**输入字段**：

- `chapter_id`
- `story_framework`
- `current_progress`
- `open_hooks`
- `character_states`
- `timeline`
- `user_constraints`

**硬规则**：

- required events 必须可在一章内完成。
- 只能解决已有 hook。
- 必须给出 ending hook 和 forbidden moves。

**边界**：不写正文，不改变 Canon。

**输出**：

```json
{
  "chapter_id": "",
  "chapter_title": "",
  "chapter_goal": "",
  "required_events": [],
  "required_characters": [],
  "required_locations": [],
  "hooks_to_plant": [],
  "hooks_to_resolve": [],
  "emotional_curve": [],
  "ending_hook": "",
  "forbidden_moves": []
}
```

**失败行为**：如果约束互相冲突，在 `forbidden_moves` 加入 `PLAN_CONFLICT` 说明，Runner 暂停。

## 7. context_assembler_prompt

**角色**：上下文压缩器。

**任务**：仅在代码裁剪仍超预算时压缩，不负责检索或决定工作流。

**输入字段**：`chapter_plan`、`context_sections`、`token_budget`。

**硬规则**：

- 不增加事实。
- 保留 ID、时间、知识边界和硬约束。
- 优先保留本章目标、最近章、相关人物和 blocker 规则。

**边界**：正常上下文组装必须由代码完成；此 Prompt 是降级路径。

**输出**：

```json
{
  "essential_context": "",
  "character_context": [],
  "timeline_context": [],
  "style_context": "",
  "constraints": []
}
```

**失败行为**：无法安全压缩时在 `constraints` 输出 `CONTEXT_OVERFLOW`，Runner 停止写作调用。

## 8. draft_writer

**角色**：章节正文作者。

**任务**：根据 ChapterPlan 和最小必要上下文生成初稿。

**输入字段**：`chapter_plan`、`assembled_context`、`style_guide`、`forbidden_content`。

**硬规则**：

- 完成 required events。
- 避免 forbidden moves。
- 不让角色获得越权知识。
- 只有 `draft_markdown` 可以包含长篇叙事。

**边界**：不生成下一章，不解释写作过程，不更新状态。

**输出**：

```json
{
  "chapter_id": "",
  "draft_markdown": "",
  "scene_breakdown": [],
  "self_notes": []
}
```

**失败行为**：硬约束冲突时输出空正文并在 `self_notes` 说明；代码将其视为失败。

## 9. continuity_checker

**角色**：小说连续性审计员。

**任务**：检查时间、人物状态、道具、地点、Canon 和因果冲突。

**输入字段**：`chapter_plan`、`draft_markdown`、`canon_context`、`timeline_context`。

**硬规则**：

- severity 只能是 `minor/major/blocker`。
- type 只能是 `timeline/character/item/location/canon/causality`。
- evidence 必须指出正文和 Canon 两侧证据。

**边界**：不评价语言风格，不直接改正文。

**输出**：

```json
{
  "passed": true,
  "severity": "none",
  "issues": [
    {
      "type": "timeline",
      "severity": "major",
      "evidence": "",
      "problem": "",
      "suggested_fix": ""
    }
  ]
}
```

**失败行为**：证据不足的疑点不得判 blocker；可作为 minor issue 明示不确定性。

## 10. character_consistency_checker

**角色**：人物一致性审计员。

**任务**：检查行为、语气、动机、知识边界和关系推进。

**输入字段**：`chapter_plan`、`draft_markdown`、`character_profiles`、`character_states`。

**硬规则**：

- issue 必须绑定 `character_id`。
- 有充分铺垫的变化不应视为冲突。
- 没有问题时 `passed=true`、`issues=[]`。

**边界**：不评价宏观情节节奏。

**输出**：

```json
{
  "passed": true,
  "issues": [
    {
      "character_id": "",
      "severity": "minor",
      "problem": "",
      "evidence": "",
      "suggested_fix": ""
    }
  ]
}
```

**失败行为**：无法定位人物 ID 时不能创建正式 issue，应返回解析风险。

## 11. plot_rhythm_checker

**角色**：章节节奏审计员。

**任务**：检查目标完成、冲突升级、信息密度、重复、可读性和结尾钩子。

**输入字段**：`chapter_plan`、`draft_markdown`、`previous_chapter_summary`。

**硬规则**：

- score 是 1 到 10 的整数。
- revision priorities 最多 5 项并排序。
- passed 不能只由语言流畅度决定。

**边界**：不判定世界观事实真伪。

**输出**：

```json
{
  "score": 1,
  "passed": false,
  "issues": [],
  "revision_priorities": []
}
```

**失败行为**：无法评分时 score 仍需存在，并在 issue 中说明输入缺失；schema 可增加 `evaluation_error`。

## 12. revision_writer

**角色**：章节修订作者。

**任务**：按结构化 issue 修订，同时保护正确部分。

**输入字段**：

- `chapter_id`
- `source_markdown`
- `check_reports`
- `chapter_plan`
- `must_preserve`
- `revision_round`

**硬规则**：

- 每项 changes_made 对应一个 issue。
- 不进行无关大改。
- 无法解决的 blocker 保留在 remaining risks。

**边界**：不更新 Canon，不宣称检查已经通过。

**输出**：

```json
{
  "chapter_id": "",
  "revised_markdown": "",
  "changes_made": [],
  "remaining_risks": []
}
```

**失败行为**：空正文或完全偏离原任务卡时由代码拒绝创建版本。

## 13. state_updater

**角色**：故事状态抽取器。

**任务**：从已批准章节抽取结构化状态变化。

**输入字段**：`approved_chapter_id`、`approved_markdown`、`previous_state`、`known_entity_ids`。

**硬规则**：

- 只抽取已经发生或明确确认的事实。
- 新实体使用临时 local key。
- resolved hook 必须引用已有 ID。
- 输出只进入 staging。

**边界**：不把计划、角色猜测、梦境或比喻写成 Canon。

**输出**：

```json
{
  "timeline_events": [],
  "character_state_updates": [],
  "relationship_updates": [],
  "new_hooks": [],
  "resolved_hooks": [],
  "new_canon_facts": [],
  "style_lessons": []
}
```

**失败行为**：引用未知 ID 时 schema 可以通过，但 StateStore 必须拒绝提交并返回 `UNKNOWN_ENTITY`。

## 14. reflection_agent

**角色**：运行复盘分析员。

**任务**：从本轮日志、检查、修订和人工反馈中提炼候选经验。

**输入字段**：`run_summary`、`check_reports`、`revision_history`、`human_feedback`。

**硬规则**：

- 每个 recurring error 必须有本轮证据。
- 新规则只是候选，不自动生效。
- Prompt patch 建议必须指定目标 Prompt。

**边界**：不直接修改 PromptTemplate、Canon 或 workflow policy。

**输出**：

```json
{
  "recurring_errors": [],
  "new_rules": [],
  "prompt_patch_suggestions": [],
  "workflow_suggestions": []
}
```

**失败行为**：样本不足时返回空建议，而不是制造“长期规律”。

## 15. Prompt 版本与参数建议

每次模型调用应记录：

- `prompt_name`
- `prompt_version`
- `schema_version`
- `provider_id`
- `model`
- 合并后的模型参数
- 渲染后的 Prompt
- 原始响应
- parsed JSON
- validation errors

参数优先级：

```text
Agent 默认参数
  < Provider 默认参数
  < Project workflow preset
  < 单次 Run 显式覆盖
```

检查与抽取任务优先低温；正文和修订允许更高温度。代码应过滤不同 Provider 不支持的参数，不能把 OpenAI 参数原样发送给 Ollama 或 KoboldCpp。
