# Changelog

本项目采用语义化版本号。由于仍是本地优先原型，版本号表示可追溯的仓库基线，不代表商业发布成熟度。

## [1.1.0] - 2026-07-12 · 故事地图可视化 + 云模型接入

### 新增（后端·故事地图）

- **故事地图聚合读接口** `GET /api/novels/{id}/story-map`：一次返回章节 / 人物（含出场章节）/
  时间线事件 / 情节线 / 伏笔 / 归一化人物关系 / 未匹配关系 / 统计（连续性分数、伏笔计数含超期）。
- **时间线事件 / 情节线 / 伏笔手动 CRUD** 独立路由；`TimelineEvent` 新增可空 `story_order`
  （叙事顺序 vs 故事顺序切换）——additive migration `d4e5f6a7b809`。
- **AI 逐章提取管线**：`POST /novels/{id}/story-map/extract` + 轮询；候选写 staging
  （`staged_storymap_*`），复用 story-engineering 的接受/拒绝接口；新路径正确解析人物名→id、
  章节锚点，修复旧接受逻辑丢关联的缺陷（旧行为不动）；无模型服务时优雅失败留 PARTIAL 记录。

### 新增（前端·故事地图页）

- 项目内新增「故事地图」页（`#/projects/{id}/storymap`），四视图 tab + 常驻详情面板 + 全局联动：
  **时间线**（章节主轴 + 伏笔弧线 + 叙事/故事双顺序）、**人物网络**（d3-force 力导向 + 章节滑块回放）、
  **故事线织线图**（泳道网格 + 曲线连结）、**统计仪表盘**（字数/连续性/伏笔/出场热力图）。
- AI 提取对话框（范围/Provider → 进度轮询 → 候选接受/忽略/批量高置信）；手动添加与内联编辑。
- 新增 D3 模块化依赖（selection/zoom/force/scale/shape/array），未引入图表大库；Playwright E2E 冒烟。

### 新增（云模型接入）

- **云端模型预设（DeepSeek / 小米 MiMo / MiniMax / SiliconFlow）**：模型设置页「云端服务」分组内置四个开箱即用预设，选中即填好 Base URL、推荐模型名与参数；一律映射后端合法 `provider_type=cloud_openai_compatible`，不新增分发类型。
- **Adapter 支持 `token_param` 选项**：`OpenAICompatibleAdapter` 支持通过 options/default_options 的 `token_param`（默认 `max_tokens`）改用如 `max_completion_tokens` 的参数名，兼容 MiniMax/MiMo；默认路径行为不变。
- DeepSeek 旧模型名内联停用警告、云端 Key 本地存储安全提示、模型名 datalist 建议。

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
