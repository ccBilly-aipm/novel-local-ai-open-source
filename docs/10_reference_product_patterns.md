# 同类产品页面设计模式

## 1. 方法与边界

本报告只提炼适合 Novel Local AI 的产品模式，不评价产品优劣，也不建议复制视觉外观。

资料优先使用英文官方文档。部分产品功能会持续变化，因此这里只把资料中可确认的交互模式作为参考，不把未验证细节写成事实。

## 2. AI 小说写作工具

### 2.1 Sudowrite

**核心结构**

- Project 内有文档列表和持续可见的 Story Bible。
- Story Bible 由 Synopsis、Characters、Worldbuilding、Outline、Scenes/Draft 等内容组成。
- Canvas 提供可自由排列的二维卡片空间。

**主路径**

```text
Braindump/Synopsis
-> Characters/Worldbuilding
-> Outline
-> Scene/Draft
-> 人工编辑
```

**状态反馈**

- 生成内容被视为可编辑建议，不是自动成为真相。
- Story Bible 作为作者和 AI 共同参考的来源。

**配置入口**

- 写作设定靠近项目和 Story Bible，而不是散落在每次生成表单中。

**可借鉴**

1. Story Bible 持续存在，但不抢占正文主区域。
2. 从想法到大纲是渐进路径，而不是要求先填完所有结构。
3. AI 生成后强调人工修改。

**不适合照搬**

1. 不在 MVP 2 引入 Canvas；自由白板成本高且不验证 Loop 核心价值。
2. 不自动导入任意小说并声称完整抽取 Story Bible。

来源：

- [What is Story Bible](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC)
- [Outline](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/outline/3owKyHXUm1bCdp41b2Npjk)
- [Canvas](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/canvas/pQGLNzeYo1kLhGo14rdBy6)

### 2.2 Novelcrafter

当前审计未获得足够稳定的官方页面内容来逐项核实其最新 UI，因此不写具体菜单事实。

可以参考的通用模式是：

- 小说项目与 Codex/Story Bible 分层。
- 场景/章节编辑与 AI 操作靠近。
- 模型连接与写作项目分离。

需要二次验证：

- 当前版本的确切导航名称。
- Codex、Chat、Planning 与模型配置的最新位置。

### 2.3 Scrivener

**核心结构**

- Binder：层级文档树。
- Editor：正文。
- Inspector：当前文档的 synopsis、notes、metadata、snapshots。
- Corkboard/Outliner：同一结构的不同组织视图。

**主路径**

```text
Binder 选择章节/场景
-> Editor 写作
-> Inspector 查看局部元数据
-> Corkboard/Outliner 调整结构
```

**状态反馈**

- 标签、状态、图标在 Binder、Corkboard、Outliner、Inspector 多处一致显示。

**可借鉴**

1. 左侧结构、中间内容、右侧 inspector 是成熟长文写作布局。
2. 同一章节状态应在项目列表、章节树和详情页一致可见。
3. 右侧只显示“当前选择项”的相关信息，不应塞全局日志。

**不适合照搬**

1. MVP 2 不需要 Corkboard、Outliner、Binder 三套同构视图。
2. 不引入复杂自定义 metadata 系统。

来源：

- [Integrating Binder, Corkboard, and Outliner](https://www.literatureandlatte.com/blog/integrating-scriveners-binder-corkboard-and-outliner)
- [Get to Know the Scrivener Inspector](https://www.literatureandlatte.com/blog/get-to-know-the-scrivener-inspector)
- [Three Ways to Mark Status](https://www.literatureandlatte.com/blog/three-ways-to-mark-the-status-of-items-in-your-scrivener-project)

### 2.4 Ulysses、Obsidian、Notion

**共同模式**

- 左侧集合/文件树，中间编辑器，右侧属性或辅助上下文。
- 内容块/页面可自由组织，但状态和属性与正文分离。
- 快速搜索、最近内容、反向链接或数据库视图帮助恢复工作上下文。

**可借鉴**

1. 最近打开项目和最近章节。
2. 轻量命令入口与搜索可晚于 Router 加入。
3. 把人物、世界规则和章节看成可链接实体。

**不适合照搬**

1. 不把小说产品变成通用知识库。
2. 不要求用户自己搭建数据库模板。
3. MVP 2 不做双向链接图谱或块编辑器。

## 3. 本地模型工具

### 3.1 LM Studio

**核心结构**

- 已下载模型、已加载模型、Developer/API server 是不同概念。
- 模型可设置 context length、GPU offload、TTL、identifier。
- 日志工具可分别查看模型输入、输出和 server 日志。

**主路径**

```text
找到本地模型
-> 估算/加载到内存
-> 启动 API server
-> 使用 identifier 调用
-> 查看模型/服务器日志
```

**状态反馈**

- 模型是否 loaded 与 API server 是否 running 是独立状态。
- 日志可按 input/output/server 筛选。

**可借鉴**

1. Novel Local AI 必须区分“本地模型文件”“运行时已加载模型”“Provider 配置”“任务角色”。
2. 测试失败应显示连接、HTTP、模型名、超时等分类。
3. 原始模型 IO 应在 Logs 页面按需展开。

**不适合照搬**

1. 不复制完整模型下载器与硬件调优 UI。
2. 不把 GPU offload 等运行时参数暴露给所有 Provider。

来源：

- [LM Studio API server](https://lmstudio.ai/docs/developer/core/server)
- [lms load](https://lmstudio.ai/docs/cli/local-models/load)
- [lms log stream](https://lmstudio.ai/docs/cli/serve/log-stream)

### 3.2 Ollama WebUI / text-generation-webui

**常见模式**

- 模型管理、会话/生成和高级参数分离。
- 默认参数对普通用户隐藏，高级采样参数可展开。
- 当前模型在生成区域持续可见。

**可借鉴**

- 工作区只展示当前 Writer/Checker 模型摘要。
- 完整 Provider 参数放 Models 页面。
- 高级 JSON 参数默认折叠。

**不适合照搬**

- 不把小说工作区变成通用聊天界面。
- 不把全部采样参数放在每次章节生成旁边。

### 3.3 AnythingLLM

**核心结构**

- System LLM 是默认值。
- Workspace 可覆盖 provider/model。
- Agent 可再使用 workspace/system 默认值。
- Agent session 在聊天中显示开始与完成日志。

**可借鉴**

1. 建立“全局默认 -> 项目覆盖 -> 本次 run 覆盖”层级。
2. Models 页负责默认角色，Project Settings 只做覆盖。
3. 运行开始和结束必须有可见事件。

**不适合照搬**

- 不引入通用 Agent skills 商店。
- 不让模型自动决定小说工作流工具。

来源：

- [LLM configuration overview](https://docs.anythingllm.com/setup/llm-configuration/overview)
- [Agent setup](https://docs.anythingllm.com/agent/setup)
- [Agent usage](https://docs.anythingllm.com/agent/usage/overview)

## 4. Agent 与 Workflow 工具

### 4.1 n8n

**核心结构**

- Workflow Editor 与 Executions 是两个视图。
- Execution list 可按 Running、Success、Failed、Waiting 和时间筛选。
- 失败执行可载入旧输入进行调试和重新运行。

**主路径**

```text
编辑 workflow
-> 执行
-> Executions 查看状态
-> 打开失败节点
-> 修复
-> 使用旧数据重跑
```

**可借鉴**

1. Chapter editor 与 Run execution 必须分离。
2. Runs 页面提供状态筛选。
3. Run Detail 聚焦 step 时间线；Logs 再展示原始 IO。
4. 失败 run 应保留输入并提供“修复后重新运行”入口。

**不适合照搬**

1. 小说 Loop 是固定状态机，不需要节点画布。
2. 不允许用户任意连接节点改变安全写入顺序。

来源：

- [Executions](https://docs.n8n.io/workflows/executions/)
- [Workflow-level executions](https://docs.n8n.io/workflows/executions/single-workflow-executions/)
- [Debug and re-run executions](https://docs.n8n.io/workflows/executions/debug/)

### 4.2 LangGraph Studio / Dify / Flowise

**常见模式**

- 图或流程定义与具体 run/thread 分开。
- 每个 run 可查看节点顺序、输入、输出、错误和中断。
- Human-in-the-loop 是显式暂停状态。

**可借鉴**

- WAIT_HUMAN_APPROVAL 必须在项目 Overview、章节树和 Run Detail 同时显眼。
- 审批按钮只在合法状态出现。
- 当前 step、已经完成的 step、失败 step 使用不同视觉状态。

**不适合照搬**

- 不展示可编辑图。
- 不把每次模型调用包装成复杂节点配置器。
- 不在 MVP 2 开放任意 workflow 编排。

### 4.3 Coding Agent 产品

**常见模式**

- 任务目标持续可见。
- 工具调用/步骤日志按时间排列。
- 结果与变更可 diff。
- 人工确认是明确动作，不把模型输出自动当成最终文件。

**可借鉴**

1. 把 ChapterVersion 类比为 patch/working draft。
2. approve 前显示“尚未写入正式章节”。
3. approve 后显示写入版本和时间。
4. revise 要求反馈，并生成新版本而非覆盖。

**不适合照搬**

- 不展示模型“思维过程”。
- 不把小说写作变成终端式对话。

## 5. 适合本项目的组合模式

```text
Scrivener：章节树 + 编辑器 + Inspector
Sudowrite：Story Bible 持久上下文 + 人工编辑 AI 输出
AnythingLLM：全局默认模型 + 项目覆盖
n8n：Runs/Executions 独立页面 + 失败诊断
LM Studio：模型文件/加载/API/日志分层
Coding Agent：版本 diff + 明确审批
```

## 6. 设计原则

1. 写作页面保持安静，运行页面负责可观察性。
2. “生成”不等于“发布正文”。
3. 全局配置与项目内容分离。
4. 状态必须跨页面一致。
5. 日志可获得，但默认不打扰写作者。
6. 高级参数渐进披露。
7. 固定、安全的 Loop 状态机优于可视化编排。
