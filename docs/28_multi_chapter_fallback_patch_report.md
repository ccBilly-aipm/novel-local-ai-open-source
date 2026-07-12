# 多章续写托底补丁报告

## 问题原因

截图中的生产线没有调用模型，而是在前置检查阶段暂停。目标第 3 章存在，但
`ChapterOutline.goal` 与 `outline_content` 均为空，因此旧实现返回
`CHAPTER_PLAN_MISSING`。检查时 LM Studio 的 `127.0.0.1:1234` 也未监听，但它不是这两次
暂停的直接原因。

## 本轮修复

- 生成章数改为任意大于 0 的整数。
- 请求数量超过已有章节时，按顺序创建缺失章节。
- 缺少章节计划时，优先从 `Novel.story_outline` 的“第 N 章”条目提取标题与计划。
- 总纲中没有对应条目时，创建带 `[AUTO_CHAPTER_PLAN]` 标记的保守临时计划。
- 启动子 Loop 前检查 Provider 端口和目标模型是否真实可用。
- LM Studio 不可用时，调用本地 `lms` 启动 server 并加载所选模型。
- Ollama 不可用时尝试启动本地 Ollama 应用。
- 受管 llama.cpp 不可用时尝试重启 LaunchAgent。
- 所选 Provider 恢复失败时，切换到另一个已启用、在线且目标模型可用的本地 Provider。
- 没有任何 Provider 可用时进入 `PROVIDER_UNAVAILABLE` 暂停，不静默失败。
- 生产线卡片展示 Provider 自动恢复和切换记录。

## 安全边界

- 自动创建只发生在用户明确请求的连续章节数量范围内。
- 自动计划不会覆盖已有人工章节目标或大纲。
- 自动计划通过 `style_notes` 保留来源标记。
- 超过 10 章时前端要求二次确认。
- 原有最大模型调用次数、blocker 暂停和版本备份规则继续生效。

## 测试

- 空章节计划可自动补全并完成。
- 请求 4 章但仅存在 1 章时，可自动创建其余 3 章并完成。
- 所选 Provider 离线时可切换到在线本地 Provider。
- 完整后端测试：`36 passed`。
- 前端生产构建：通过。
