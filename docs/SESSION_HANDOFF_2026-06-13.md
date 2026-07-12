# 会话交接：第六章连续性死循环修复（2026-06-13）

> 本文件用于把这次会话的上下文交接给 Claude Code 或下一个 AI。Claude Code 在本目录启动时会自动读取
> `CLAUDE.md`；本文件可被 `@docs/SESSION_HANDOFF_2026-06-13.md` 引用进上下文。

## 背景问题

`未来退信` 项目第 6 章《灯塔的地下室》在 `ai_auto_commit` 模式下反复失败：连续性检查反复报
MAJOR（timeline / item / causality），自动修订 3 轮也清不掉，最终暂停
“Major issues remain after allowed revision rounds”。用户换过模型仍然失败。

## 诊断结论（根因，已确认）

不是模型能力问题，是**约束 / 设计**问题：

1. `services/api/app/services/context_builder.py::character_block()` 把每个角色的冻结
   `当前状态`（如“位置=邮局”）当成权威事实塞进上下文；物品状态同理。
2. `services/api/app/workflow/runner.py`：上下文只在 `ASSEMBLE_CONTEXT` 装配**一次**并存到
   `run.assembled_context`，修订循环 REVISE→CHECK→PLAN 全程复用，**不会重新装配**。
3. 第 6 章按大纲推进到灯塔 → 检查器拿正文（灯塔）和上下文（邮局）比对 → 判 MAJOR。
4. `revision_writer` 被要求“每个 issue 都修复”且“不得与上下文冲突”——大纲要灯塔、上下文要邮局，
   无解：保留灯塔则问题还在，改回邮局则违反大纲。每轮用同一份冻结上下文复检 → 同样 MAJOR →
   烧完 3 轮暂停。任何模型都满足不了自相矛盾的约束。
5. `services/api/app/services/story_memory.py` 只写 `chapter.summary`，**从不推进**
   `character.current_state_json` / canon `character_states_json`，所以角色状态永远停在故事早期，
   任何向前推进的章节都被永久判错。

## 已做的修复（在开发版仓库内，纯约束层，未动 schema/DB/迁移）

- `services/api/app/prompts/novel_loop/continuity_checker.md`：新增“判断基准”——上下文里的角色/物品
  状态是“本章开始前快照”，与本章目标/大纲一致的推进不算冲突、不得报 major、不得要求正文回退；
  陈旧快照最多报一条 minor 提示。
- `services/api/app/prompts/novel_loop/revision_writer.md`：加“逃生阀”——若某 issue 只能靠回退到旧
  状态或违背大纲才能修复，则不回退，保持正确推进并保证本章内部自洽。
- `services/api/app/services/context_builder.py`：把角色状态标签由“当前状态”改为
  “本章开始前状态（随本章推进可能改变，非本章必须维持）”。

原文件备份在 `_ai_fix_backup/2026-06-13_ch6_continuity/`，可随时回滚。

## 关键坑：开发版 ≠ 部署版（这是“改了没反应”的真正原因）

本机有两份独立副本：
- 开发版仓库：本仓库（改代码的地方）。
- 部署版：`~/Library/Application Support/NovelLocalAI/...`，由 `com.novel-local-ai.api.plist`
  这个 LaunchAgent 启动，端口 8000，**app 界面实际运行的就是这一份**。

`app/agents/base.py` 的 `PROMPT_ROOT` 按“正在运行的那份代码”相对路径加载提示词，所以**只改仓库、
不同步到部署版，运行的后端看不到**。这就是用户“追加修订还是失败”的原因。

此外，“追加修订”是**续跑旧 Run**，会复用 Run 上冻结的旧 `assembled_context`（续跑直接进
BUILD_REVISION_PLAN，跳过重新装配），所以即使同一副本，`context_builder.py` 的标签改动对续跑也不生效。

## 让修复生效的正确操作

1. 同步到部署版并重启：`./scripts/sync_to_deployed.sh`（本次会话新建，自动备份+重启 api；
   自动找不到部署版路径时用 `APP=/部署版/services/api ./scripts/sync_to_deployed.sh`）。
2. 在 app 里对第 6 章发起**全新 Run（不要点“追加修订”续旧的）**——全新 Run 才会重新装配上下文。
3. 验证：该 Run 高级日志 → 最新一次 `continuity_checker` 调用 → prompt 里应出现
   “判断基准 / 本章开始前状态”。

## 收尾进度（2026-06-13 续会话更新）

- ✅ 本机验证已通过：
  ```bash
  cd services/api && .venv/bin/pytest -q      # 实测 48 passed（交接包后新增了 Creative/LocalModel 测试，
                                              # 故比文档预期的 38 多 10 条，全绿）
  cd ../../apps/web && npm run build          # 通过，43 modules transformed
  ```
- ✅ 已执行 `./scripts/sync_to_deployed.sh`（输入 yes 确认）：3 个修复文件已同步到部署版
  `~/Library/Application Support/NovelLocalAI/services/api/`，旧文件备份在该目录下
  `_deployed_backup_20260613-010225/`；api LaunchAgent 已 `launchctl kickstart -k` 重启（新 PID，
  `/openapi.json` 返回 200）。同步前部署版 3 个文件均与仓库不一致（仍是旧版），同步后已逐一比对
  `diff -q` 全部一致，部署版 `continuity_checker.md` 已含“判断基准”。**未碰数据库。**
- ⏳ 仍待用户操作：在 app 里对第 6 章发起**全新 Run**（不要点“追加修订”续旧 Run），再到该 Run
  “高级日志”→ 最新一次 `continuity_checker` 调用 → 确认 prompt 出现“判断基准 / 本章开始前状态”，
  并观察连续性是否不再误判 MAJOR。修复真实效果以此为准。

## 可选的后续改进（需用户拍板）

- **收敛保护**：一轮修订后 major 数量没下降就提前停并给人工清晰说明，而不是空烧 3 轮。
  涉及 `auto_pipeline.py` / `runner.py` + 加测试。
- **结构化 Story Memory / 状态推进**（真正的根治）：让系统能推进角色/物品状态，对应文档里未实现的
  Reverse Story Engineering / 结构化 Story Memory。
- **新功能缺文档/迁移/测试**：`CreativeStudio.tsx` + `routers/creative.py` + `CreativeRun`（创作中心）、
  `LocalModelCenter` + `local_model_inventory.py`（本地模型中心）是交接包之后新增的，
  交接文档未记录；且 `creative_runs` 表**没有 Alembic 迁移**，仅靠启动时 `create_tables()` 建表，
  与“迁移要可审计”的原则不一致。

## 给 Claude Code 的提示

遵循 `CLAUDE.md` 的铁律（尤其：改代码前先确认方案、不破坏旧接口、不动已有 ChapterVersion、
迁移前先备份 SQLite、区分仓库 DB 与部署 DB）。先读 `CLAUDE.md` 与 `docs/AI_HANDOFF_INDEX.md`，
再读本文件了解最近一次改动。
