# Auto Review、Revise 与 Commit 设计

## 1. Checker 输出

```json
{
  "passed": false,
  "severity": "major",
  "issues": [{
    "issue_id": "stable-id",
    "type": "character",
    "severity": "major",
    "evidence": "证据",
    "problem": "问题",
    "suggested_fix": "修复建议",
    "auto_fixable": true,
    "affected_sections": [],
    "must_pause": false
  }]
}
```

旧 Checker 输出缺少新增字段时使用安全默认值，保持已有测试和历史记录可读。

## 2. RevisionPlan

P0 由已通过 Pydantic 的 CheckReport 确定性生成，不额外调用模型：

```json
{
  "target_version_id": "v1",
  "goals": ["修复连续性问题"],
  "fixes": [{
    "issue_id": "...",
    "instruction": "...",
    "preserve": ["未被问题指出的事实"],
    "change": ["受影响段落"],
    "avoid": ["引入新的 Canon 事实"]
  }],
  "risk_notes": []
}
```

Revision Writer 接收计划文本，生成新的不可变版本，再次运行 Checker。

## 3. 判定策略

- blocker 或 `must_pause=true`：立即暂停。
- major：仅当全部 auto-fixable 且未超过轮次时自动修订。
- minor：可按 `allow_minor` 阈值直接通过，或自动修订。
- 无问题：Manual/Auto Revise 等人工；Auto Commit 自动写入。
- 到达最大修订轮次仍有 major：暂停。

## 4. Auto Commit 前置条件

1. 当前 `ChapterVersion` 存在且属于当前 Run/Chapter。
2. Writer 已通过 `DraftTextGuard`。
3. 无 blocker。
4. major 数量符合阈值，P0 默认必须为 0。
5. 修订轮次未超限。
6. Run 有完整 Writer、Checker ModelCall 和步骤日志。
7. 旧 `Chapter.content` 非空时先创建 `pre_auto_commit_backup` ChapterVersion。
8. 写入动作与结果写 RunStep audit log。

Auto Commit 不删除版本。用户可从任意 ChapterVersion 再次写回，完整回滚 API 后续补充。

## 5. 写入后

- 更新 `Chapter.content`、`version`、`status` 和 `approved_version_id`。
- 生成事实型章节摘要。
- 创建带来源 chapter/version/run 的 `StoryMemoryRecord`。
- 不自动更新角色、时间线、伏笔或世界规则 Canon；这些属于后续 staging。
