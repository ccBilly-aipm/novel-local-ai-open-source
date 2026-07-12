# Changelog

本项目采用语义化版本号。由于仍是本地优先原型，版本号表示可追溯的仓库基线，不代表商业发布成熟度。

## [1.0.0] - 2026-07-12

首个 GitHub 基线版本。公开版在同一代码基线上完成路径脱敏、开源许可、贡献指南和图文 README。

### 已包含

- React/Vite 本地 Web UI 与 FastAPI/SQLite 后端。
- 项目、小说、章节、角色、世界规则、Prompt 和模型 Provider 管理。
- 兼容 LM Studio、llama.cpp、Ollama、KoboldCpp、text-generation-webui 和 OpenAI-compatible API。
- 单章 Loop、不可变 ChapterVersion、连续性检查、人工 approve/reject/revise。
- AI 自动审稿、自动修订、自动提交和多章生产线。
- Reference Pack、最小 Story Memory、章节摘要和 checkpoint。
- 正向故事工程、反向小说拆解/仿写 P0、Markdown 导出。
- RunStep、ModelCall、GenerationRun 等审计记录及基础恢复机制。

### 已知边界

- 还没有浏览器 E2E 自动化测试和版本 Diff UI。
- 任务队列仍在单进程内存中，不适合多 worker 部署。
- Story Memory 尚未覆盖完整关系、时间线、伏笔和物品状态模型。
- API Key 仍保存在本地 SQLite，尚未接入 macOS Keychain。
- 仓库源码与本机 LaunchAgent 部署副本是两个目录，修改后需明确同步。
