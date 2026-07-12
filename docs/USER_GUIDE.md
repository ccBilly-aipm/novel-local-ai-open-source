# Novel Local AI v1.0 使用手册

## 1. 这是什么

Novel Local AI 是运行在 macOS 本机的 AI 小说写作工作台。你可以管理小说项目、故事总纲、人物、世界规则和章节计划，再调用 LM Studio、llama.cpp、Ollama 等本地模型生成、检查和修订章节。数据默认保存在本机 SQLite，不要求云服务。

`v1.0.0` 是这个开源仓库的首个可追溯版本。它已经可以本地使用，但仍属于开发中的原型，不代表商业发布完成度。

## 2. 使用前准备

需要：

- macOS。
- Python 3.9 或更高版本。
- Node.js 18 或更高版本。
- 如果要生成正文，需要至少一个可访问的本地或 OpenAI-compatible 模型服务。

不启动模型时，项目管理、正文手工编辑、资料维护和 Markdown 导出仍然可以使用。

## 3. 第一次启动

后端：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/services/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

看到服务启动后，可打开 API 文档：

```text
http://127.0.0.1:8000/docs
```

另开一个终端启动前端：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/apps/web
npm install
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173/
```

依赖已安装时，也可以在项目根目录运行：

```bash
./scripts/dev.sh
```

## 4. 配置本地模型

在顶部进入“本地模型/设置”。应用会尝试发现本机模型和已配置 Provider，但“发现模型文件”不等于“模型服务正在运行”。真正生成前，应确认 Provider 的测试请求能成功。

常用地址：

| 服务 | 常用 Base URL | 说明 |
|---|---|---|
| LM Studio | `http://127.0.0.1:1234/v1` | 先在 LM Studio 加载模型并启动 Local Server |
| llama.cpp | `http://127.0.0.1:8080/v1` | 端口以实际 `llama-server` 参数为准 |
| Ollama | `http://127.0.0.1:11434` | 模型名使用 `ollama list` 中的名称 |
| KoboldCpp | 服务实际地址 | API 路径取决于启动版本 |
| text-generation-webui | 通常以 `/v1` 结尾 | 需要启用 OpenAI-compatible 扩展 |

建议先做一次短文本测试，再运行长章节。上下文和最大输出应根据模型真实能力配置；设置更大的数值不会让不支持该长度的模型自动获得更长上下文。

### 云端 API（可选）

Novel Local AI 始终是本地优先的：默认、推荐的写作方式仍是本机模型。云端 API 只是可选加速项，适合审稿、结构提取，或本机配置暂时跑不动大模型时的过渡。

在“运行时类型”下拉的「云端服务」分组里，内置了四个开箱即用的预设。选中后会自动填好 Base URL、推荐模型名和合理参数，你只需填入自己的 API Key：

| 服务 | Base URL | 推荐模型（主力 / 便宜） | 拿 Key 入口 |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com` | `deepseek-v4-pro` / `deepseek-v4-flash` | platform.deepseek.com |
| 小米 MiMo | `https://api.xiaomimimo.com/v1` | `mimo-v2.5-pro` / `mimo-v2.5` | platform.xiaomimimo.com |
| MiniMax | 国内 `https://api.minimaxi.com/v1`；国际 `https://api.minimax.io/v1`（差一个 i） | `MiniMax-M3` / `MiniMax-M2.7` | platform.minimax.io / minimaxi.com |
| SiliconFlow 硅基流动 | `https://api.siliconflow.cn/v1` | 照其模型目录，如 `deepseek-ai/DeepSeek-V4-Flash` | cloud.siliconflow.cn |

几点提醒：

- DeepSeek 旧模型名 `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 停用，请使用 `deepseek-v4-*`。表单会在检测到旧名时给出内联警告。
- MiniMax 已弃用 `max_tokens`，其预设已通过 `token_param: "max_completion_tokens"` 自动改用新参数，无需手动处理。
- SiliconFlow 是聚合平台，一把 Key 可调多家开源模型，但没有 MiMo；模型名以其 `/v1/models` 实时列表为准。
- 填好 Key 后先点“测试真实生成”确认连通，再用于正式章节；连续性检查角色仍建议用推理型模型，勿用去审核模型。
- API Key 仅保存在本机 SQLite 数据库；不要把数据库文件、日志或截图分享给他人。

### 故事地图（1.1.0 新增）

每个项目内、章节页旁多了「故事地图」页，用四个联动视图把小说的结构可视化：

- **时间线**：以章节为主轴排布事件，支持叙事顺序 / 故事顺序切换，并用弧线标出伏笔的埋设与回收。
- **人物网络**：d3-force 力导向图展示人物关系，可用章节滑块回放关系随剧情的演变。
- **故事线织线图**：泳道网格呈现各情节线在章节间的穿插。
- **统计仪表盘**：字数、连续性分数、伏笔计数（含超期）与人物出场热力图。

内容有两种来源：在页面里**手动添加/内联编辑**时间线事件、情节线、伏笔；或用 **AI 逐章提取**——选好范围与 Provider 后逐章扫描，生成候选写入暂存区，再逐条接受 / 忽略（也可一键接受高置信候选）。提取依赖一个可用的模型 Provider（本机或云端均可）；无模型服务时会优雅失败并留下 PARTIAL 记录，不影响已有数据。

## 5. 推荐写作流程

1. 在“项目”创建一本小说。
2. 在“创作中心”输入想法，生成故事框架、人物、世界规则或章节计划候选。
3. 检查候选内容，只接受可信项；候选不会直接写入 Canon。
4. 在“章节”中确认当前章目标和大纲。
5. 选择本次使用的模型、运行模式和引用内容。
6. 启动单章 Loop 或多章生产线。
7. 在“Loop Runs/运行记录”查看草稿版本、连续性报告、修订链和模型日志。
8. 手动模式下 approve 后才写入正式正文；自动模式达到阈值后可自动提交。
9. 提交后系统保存章节摘要和最小 Story Memory，供后续章节使用。
10. 完成后导出 Markdown。

## 6. 运行模式怎么选

| 模式 | AI 会做什么 | 是否自动写入正文 |
|---|---|---|
| Manual Review | 生成并检查，等待人工决定 | 否 |
| AI Review and Suggest | 生成、检查和给建议 | 否 |
| AI Auto Revise | 自动按检查报告修订并复检，最后等待人工 | 否 |
| AI Auto Commit | 自动修订，达到阈值后写入 | 是 |
| Full Autonomous | 在当前项目内连续生成、修订、提交和更新记忆 | 是，遇到暂停条件会停止 |

Full Autonomous 不是电脑系统级权限。它不能删除项目/章节/版本、修改模型配置或绕过日志。第一次建议只跑少量章节并检查结果。

## 7. 引用已有内容

生成前可以引用已有章节或 ChapterVersion。系统会把引用整理为 `ReferencePack`，只提供摘要、必要片段和约束，避免把整本小说全文塞给模型。

引用时最好写清参考目的，例如“只参考战斗节奏”“保持某角色说话方式”“沿用已确认的时间线”，不要只添加引用但不说明用途。

## 8. 版本、审批与回滚

- AI 初稿和每轮修订都保存为独立 `ChapterVersion`。
- 版本不会因为再次生成而被覆盖。
- Manual/AI Auto Revise 模式下，未 approve 的版本不会更新 `Chapter.content`。
- 恢复历史版本前，系统会先备份当前正式正文。
- reject 不会删除版本，只会记录决策。

因此出现质量问题时，优先查看版本链和日志，不要直接修改数据库。

## 9. 常见错误与处理

### 模型服务不可用

先确认 LM Studio/Ollama/llama-server 等服务已启动、端口正确、模型已加载。Provider recovery 会尝试恢复或回退到其他在线本地 Provider，但没有任何可用服务时无法生成正文。

### `CHAPTER_PLAN_MISSING`

当前章节缺少目标或大纲。系统部分流程会生成保守的 fallback 计划，但建议在章节页补充目标和大纲后重新运行，质量更可控。

### `WAIT_HUMAN_APPROVAL`

这不是程序报错，表示当前策略要求人工查看版本并 approve/reject/revise。

### `AUTO_RUN_PAUSED`

通常表示 blocker、major 问题超过修订轮次、模型超时、输出校验失败或上下文不足。打开 Run 详情，查看最后一个 RunStep 和 ModelCall，再选择恢复、追加修订或终止。

### JSON/Schema 校验失败

Checker/Extractor 的结构化输出不符合 Pydantic schema。系统会明确失败或暂停，不会静默当作成功。可换更擅长 JSON 的模型、缩短输入或修正 Prompt 后重跑。

### 正文输出被截断

查看 ModelCall 的 `finish_reason`、最大输出 token 和原始响应。不要把截断文本直接批准为正式正文；提高模型服务允许的上下文/输出上限，或让系统使用更紧凑的上下文后重跑。

## 10. 数据、备份与隐私

开发数据库默认位于：

```text
$HOME/Documents/vibe-coding/novel-local-ai-open-source/data/novel_local_ai.db
```

本机部署副本通常使用：

```text
$HOME/Library/Application Support/NovelLocalAI/data/novel_local_ai.db
```

两份数据库不是自动同步的。备份、迁移或排查前先确认当前后端使用哪一份。数据库、WAL/SHM、日志和 `.env` 已被 Git 排除，不会进入公开仓库。

API Key 当前保存在本地 SQLite，尚未接入 macOS Keychain。不要把带密钥的数据库、终端输出或截图提交到 GitHub。

## 11. 测试

后端：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/services/api
.venv/bin/pytest -q
```

前端：

```bash
cd $HOME/Documents/vibe-coding/novel-local-ai-open-source/apps/web
npm run build
```

当前没有浏览器 E2E 测试。涉及审批、自动提交、恢复或模型配置的修改，除了上述命令，还要进行一次真实页面最小回归。

## 12. 当前边界

- 没有完整 RAG/GraphRAG。
- 没有完整人物关系图、时间线和伏笔工作台。
- 没有 Version Diff 页面和持久化多进程任务队列。
- 没有多用户、云同步、Tauri 正式安装包或 EPUB/PDF 专业排版。
- 本地模型真实效果依赖模型本身、量化、Prompt、上下文和机器负载，发现模型不等于已验证质量。

更完整的工程交接见 `PROJECT_HANDOFF.md`，Agent 规则见 `AGENTS.md`。
