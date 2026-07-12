# Story Memory 设计

## 1. 目标

用结构化、可追溯的长期记忆替代“把全部章节全文塞进上下文”。

## 2. 目标类型

```text
ChapterSummary
StoryArcState
CharacterState
RelationshipState
TimelineEvent
WorldRule
HookRecord
ItemState
LocationState
StyleMemory
CheckpointSnapshot
```

本轮只实现 `chapter_summary` 类型的 `StoryMemoryRecord`。

## 3. 最小记录

```text
id
project_id
novel_id
chapter_id
run_id
source_id          # ChapterVersion
record_type
status
content_json
evidence_json
metadata_json
created_at
updated_at
```

每条记忆必须有来源，不能直接覆盖 Canon。P0 状态为 `active`，内容仅供 Context Builder
按相关性和预算读取。

## 4. 上下文策略

每次生成加载：

- 当前章节目标和大纲。
- 上一章及最近 2 到 3 章摘要。
- 相关角色状态和世界规则。
- 未解决冲突与伏笔。
- 用户显式 Reference Pack。
- 后续 checkpoint 和少量风格样本。

不加载全部正文、ModelCall raw output、全部检查报告或无关角色资料。

## 5. Checkpoint

Phase 3 每 3 或 5 章创建 `CheckpointSnapshot`，包含故事进展、主要冲突、角色状态、
未解决伏笔、世界变化和下一阶段方向。本轮不建 checkpoint 表。

## 6. 摘要 P0

Auto Commit 后创建事实型、长度受限的 extractive summary，保证本地流程无额外失败点。
后续可切换为严格 JSON 的 Summary Agent，并保留 extractive fallback。
