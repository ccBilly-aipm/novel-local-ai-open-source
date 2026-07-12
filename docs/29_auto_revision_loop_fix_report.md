# AI 自动修订闭环修复报告

## 现象

用户选择 Full Autonomous 后，Continuity Checker 在右侧报告 major 问题，但 Run 直接进入
PAUSED。点击“修复后继续”后出现第二个版本，却仍显示为 draft，自动修订轮次保持 0。

## 根因

- 旧策略要求所有问题都满足 `auto_fixable=true` 才进入 RevisionPlan。
- Checker 将有明确修复建议的 item/causality major 标记为 `auto_fixable=false`，策略因此
  在第一次检查后直接暂停。
- 暂停恢复固定回到 `ASSEMBLE_CONTEXT`，随后调用 `draft_writer` 重新生成初稿，而不是从
  当前版本和检查报告进入 `BUILD_REVISION_PLAN → REVISE_DRAFT`。
- 第二个版本因此是另一篇 draft，不是针对右侧问题的 revision。

## 修复

- AI Auto Revise、AI Auto Commit、Full Autonomous 模式下，所有非 blocker、非
  `must_pause` 问题都进入自动修订尝试。
- RevisionPlan 收录全部非 blocker issue，并保留 Checker 的 `auto_fixable` 原始判断。
- RevisionWriter Prompt 要求逐项落实所有 issue，不能只修复标为 auto-fixable 的问题。
- 暂停恢复会检查当前版本、Continuity Report、策略和剩余轮次：
  - 可继续修订：从 `BUILD_REVISION_PLAN` 恢复。
  - Provider/上下文等故障：从 `ASSEMBLE_CONTEXT` 恢复。
- 启动面板可设置每章最大自动修订轮次，默认 3，范围 1 到 10。
- 修订轮次耗尽后，“继续”会明确追加 1 轮修订预算，不会重新生成初稿。
- 前端明确显示自动迭代是否开启、当前轮次，以及“不建议自动修复但仍会尝试”的状态。

## 安全边界

- blocker 或 `must_pause=true` 仍立即暂停。
- 达到最大修订轮次后仍有 major 时暂停，不无限循环。
- 每次修订生成新的不可变 ChapterVersion，旧版本不覆盖。
- 每轮修订后必须重新运行 Continuity Checker。
- Auto Commit 仍禁止在 major/blocker 超过阈值时写入正式正文。

## 图二说明

`CHAPTER_PLAN_MISSING` 来自补丁部署前创建的历史父 Run。当时第 3 章没有 goal/outline。
新版本恢复该 Run 时会从故事总纲提取章节计划，提取不到才创建带来源标记的临时计划；
历史错误文字保留用于审计，不会静默删除。

## 测试结果

- Checker 返回 `auto_fixable=false` 的 major：自动生成 RevisionPlan 和 revision version。
- 暂停 Run 恢复：仅调用一次初稿 Writer，恢复后调用 RevisionWriter。
- 完整后端测试：`38 passed`。
- 前端生产构建：通过。
