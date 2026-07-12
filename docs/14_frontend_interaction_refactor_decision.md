# 前端交互重构判断

## 1. 当前最不符合直觉的 10 个点

1. 打开项目默认进入“创作中心”，老用户却更常需要继续章节或处理待审批版本。
2. Loop MVP 1.1 已可运行、审批和修订，但前端没有入口。
3. 首页不能发现 waiting、running、failed run。
4. 旧 `/generate` 会写正文，新 Loop 先写 ChapterVersion；前端没有解释两者差异。
5. 项目、模型之外的 Runs、Prompts、Settings 没有全局位置。
6. Prompt 是全局配置，却放在项目 tab 中。
7. 章节页同时容纳正文、旧任务、Canon JSON、审稿和原始日志。
8. 刷新后丢失项目、章节和 run，无法恢复人工审批任务。
9. 模型页面先展示 Provider 工程配置，没有先回答 Writer/Checker/Summary 用哪个模型。
10. Provider 测试失败只显示一行文本，无法快速判断地址、模型名或超时问题。

## 2. 问题分类

### 信息架构

- 全局导航只有“内容创作/本地模型”。
- 项目默认页不承担恢复上下文。
- Runs、Prompts、Logs、Versions 没有稳定入口。
- Prompt 位于项目内。
- 创意生成、旧 WritingTask、新 Loop Run 是三套并存概念。

### 页面布局

- 首页创建表单常驻并压缩项目列表。
- Workspace 右栏信息密度过高。
- 模型配置、参数教学和本地模型库存形成超长单页。
- 原始日志出现在写作主视图。

### 操作反馈

- waiting/failed 状态不跨页面可见。
- approve 的写入后果没有确认提示。
- 失败 step 与 error_code 没有产品化展示。
- Provider 测试缺少诊断建议。
- 保存反馈没有统一层级。

### 命名与概念

- “生成章节”没有区分 Legacy Generation 与 Loop Draft。
- “当前实际使用模型”混淆 loaded model 与 Writer Provider。
- Chapter.content、Draft Version、Approved Version 缺少用户语言。
- CreativeRun、GenerationRun、ChapterLoopRun 都被笼统理解为“生成记录”。

## 3. 当前找不到的功能

- 创建和观察 Loop Run。
- 找到项目内 waiting/failed run。
- approve、reject、revise。
- 查看 ChapterVersion。
- 查看 Loop 状态时间线。
- 从失败 step 进入诊断。
- 从刷新后的页面恢复 run。

## 4. 位置放错的功能

- Prompt Manager 应是全局 Advanced，而不是项目 tab。
- 原始 Prompt/Response 应进入 Run Logs，而不是章节右栏。
- Canon JSON 应进入 Advanced，而不是默认 Inspector。
- Provider 参数教学应折叠，不应先于任务角色。
- 删除项目应进入更多菜单。

## 5. 应降级到 Advanced

1. 旧章节生成、摘要、旧审稿和人物状态任务。
2. Canon JSON 编辑。
3. 完整 Prompt/Response。
4. Provider 默认参数 JSON。
5. Prompt Template Manager。
6. 原始 ModelCall payload。

## 6. 应成为主动作

1. 首页：Review waiting draft 或 Continue writing。
2. Project Overview：唯一 Next Action。
3. Chapters：Start Loop Run 或 Open Current Run。
4. Run Detail：Approve / Reject / Request Revision。
5. Models：连接 Writer Provider 并测试。

## 7. 暂时不要动

- 旧 `/api/chapters/{id}/generate` 行为。
- `Workspace.tsx`、CreativeStudio、PromptManager、LocalModelCenter。
- Character 和 WorldRule CRUD。
- Canon 数据结构。
- 多章循环。
- 自动 Canon 更新。
- 移动端。
- 大型 Router、状态管理库和 UI 框架。

## 8. 本轮实现判断

可以安全做最小实现，但需补充只读 Loop 列表 API。原因：

- 单个 Run Detail、approve、reject、revise 已存在。
- 当前缺少项目/章节/全局 run list，前端不能可靠发现 run。
- 只读列表不改变 workflow、不改旧 API，也不修改用户数据。

导航采用轻量 hash 深链，不引入 React Router：

```text
#/projects
#/projects/{project_id}/overview
#/projects/{project_id}/chapters
#/projects/{project_id}/runs
#/projects/{project_id}/runs/{run_id}
#/runs
#/models
#/prompts
#/settings
```

## 9. 核心交互原则

1. 项目先于配置。
2. 章节是写作主线。
3. AI 输出先成为 Version。
4. approve 是唯一发布 AI Version 的动作。
5. waiting 状态必须跨首页、项目和章节可见。
6. Debug 信息可获得但默认折叠。
7. 前端不推断持久状态，以 API 为准。
