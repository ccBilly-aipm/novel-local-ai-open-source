# 深度调研报告可用性审查

审查对象：`deep-research-report (2).md`，共 469 行。

## 可直接采纳的结论

以下内容属于可独立验证的工程原则，不依赖报告中的项目描述：

- 本地优先，并将模型服务隔离在统一 adapter 后面。
- 以章节/场景为生成单位，不追求一次生成整部长篇。
- 用故事总纲、当前目标、角色状态、世界规则、近期摘要、冲突和伏笔构造上下文。
- 生成后保存摘要和状态建议；人工编辑后的正文成为后续事实来源。
- 初版使用 SQLite、Markdown 和串行任务，不引入 Redis、Celery、向量库或图数据库。
- 审稿只输出建议，不自动覆盖作者正文。
- 长篇一致性是主要产品风险，需要显式状态和可追踪 GenerationRun。

## 待验证结论

报告未附可审计的完整引用定义，且若干表格字段互相冲突。下列信息全部标记为“待验证”：

- SillyTavern、KoboldCpp、TheStoryNexus、Storyteller、StoryCraftr、InkOS、
  Autonovel、AI Book Writer、GOAT-Agent、Hermes Agent、OpenClaw/Pi 等具体仓库身份。
- 上述项目的当前 license、最后提交时间、维护状态和商业使用边界。
- 各项目是否原生支持 llama.cpp、Ollama、KoboldCpp、RAG、Web UI、多 Agent 或 macOS。
- “TheStoryNexus 使用 Tauri/React/Dexie”“InkOS 使用 Go/TypeScript/Python”等架构描述。
- 报告中的 2025/2026 活跃度、推荐等级和“可直接复用模块”。
- LangChain、Haystack、GraphRAG 对小说场景的实际收益和成本。

特别风险：报告把 SillyTavern 的许可写为“MIT/AGPL?”，已足以说明许可数据不能直接用于
复用决策。无法确认 license 的项目默认不复制代码。

## Clone 与复用建议

- **可作为独立服务 clone/安装验证**：llama.cpp、Ollama、KoboldCpp。验证目标仅为
  HTTP API 兼容性，不把其源码并入本仓库。
- **验证 license 后再 clone 研究**：TheStoryNexus、InkOS、Storyteller、StoryCraftr、
  Autonovel、GOAT-Agent。
- **只参考架构思想**：章节树工作区、分层摘要、Human-in-the-loop、生成/审稿分离、
  状态回写、运行记录。
- **当前不直接复用代码**：所有报告提及项目。本 MVP 为独立实现。

AGPL 项目仅作架构参考，不复制代码。未来若引入 MIT/Apache 2.0 组件，必须保留原
license、NOTICE（如有）和 attribution，并单独记录来源与版本。

## 当前选择

架构参考概念：

- Storyteller 所代表的“章节/场景分割 + 近期摘要”思路。
- TheStoryNexus 所代表的“三栏小说 IDE”交互思路。
- InkOS 所代表的“生成与审稿分离、人工确认状态”思路。
- llama.cpp/Ollama/KoboldCpp 所代表的独立本地模型服务边界。

未选择：

- LangGraph、AutoGen、Hermes 等 Agent runtime：单章串行流程不需要图编排。
- Chroma/FAISS/LanceDB：MVP 数据规模可由显式结构和近期摘要覆盖。
- NetworkX/Kuzu/Neo4j/GraphRAG：尚无足够查询需求证明图结构的价值。
- Tauri：先验证浏览器 Web UI，避免同时调试 Rust 和桌面打包。
- 自动全文导入分析：准确率、版权、切章和长文本成本均未被 MVP 核心价值要求。

## 与报告完整方案的差异

MVP 只验证“已有总纲和章节大纲时，本地模型能否在有限上下文中逐章写作”。它保留
结构化状态和后续扩展表，但不实现向量检索、知识图谱、多 Agent 自动修订、可视化关系图、
完整导入分析或桌面封装。人物状态由模型生成建议并由用户确认，避免错误状态自动污染 canon。
