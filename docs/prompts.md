# Prompt 模板

运行时模板位于 `services/api/app/prompts/`，首次启动时写入 `PromptTemplate` 表。UI 修改后使用
数据库版本并递增 version。

## chapter_generation

变量：`chapter_title`、`context`。输出为可直接保存的纯章节正文，不使用 JSON。

示例输入：章节目标是“林舟发现密信但不拆穿顾宁”，角色状态表明顾宁不知道密信已丢失。

示例输出：

```text
雨水沿着窗棂落下。林舟把那封没有署名的信压进账册底层，抬头时，顾宁正推门进来……
```

## chapter_summary

变量：`chapter_title`、`chapter_content`。

示例输出：

```json
{
  "summary": "林舟发现密信并暂时隐瞒，顾宁仍不知道密信已丢失。",
  "key_events": ["林舟取得密信"],
  "unresolved_conflicts": ["林舟是否向顾宁坦白"],
  "foreshadowing": ["信封上的蓝色蜡印"]
}
```

## character_state_update

变量：`characters`、`chapter_content`。结果先保存到
`CanonState.pending_character_updates_json`，必须由用户确认。

示例输出：

```json
{
  "updates": [
    {
      "character_id": "char-1",
      "character_name": "林舟",
      "changes": {"位置": "旧书房", "已知信息": ["顾宁藏有密信"]},
      "evidence": "林舟在书房找到并读到信封署名。",
      "confidence": 0.92
    }
  ]
}
```

## chapter_review

变量：`context`、`chapter_content`。

示例输出：

```json
{
  "score": 78,
  "goal_alignment": "完成了发现密信的目标，但隐瞒动机不够清楚。",
  "character_consistency": "无明确冲突。",
  "timeline_consistency": "无明确冲突。",
  "repetition": "开头重复上一章的天气描写。",
  "missing_plot_points": "没有提及蓝色蜡印。",
  "style_issues": "连续三段句式相近。",
  "suggestions": ["补充林舟隐瞒的直接动机", "删减重复天气描写"]
}
```

## continuity_check

变量：`context`、`chapter_content`。

示例输出：

```json
{
  "issues": [
    {
      "type": "knowledge",
      "severity": "high",
      "detail": "顾宁提到了自己尚未得知的密信内容。",
      "evidence": "Canon 中顾宁不知道密信已丢失。"
    }
  ]
}
```

## outline_expand

变量：`context`。

示例输出：

```json
{
  "scenes": [
    {
      "order_index": 1,
      "title": "书房搜索",
      "goal": "让林舟取得密信",
      "outline_content": "林舟借查账进入书房，在夹层发现密信。",
      "character_ids": ["char-1"],
      "location_id": "location-1"
    }
  ]
}
```

本地小模型约束：指令短、字段固定、只要求一次任务；JSON 解析失败时保留 raw response，避免
静默丢失模型输出。
