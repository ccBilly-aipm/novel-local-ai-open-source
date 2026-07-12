# 实现报告：故事工程（Forward 前置物料 + 状态推进）2026-06-13

## 背景

用户目标是一条端到端全自动流水线：**给一个想法 →（自动生成故事背景/故事线/人物/世界观/章节计划等前置物料，供人工检查）→ 设定跑 N 章 → 自动循环「生成→审核→通过自动归档继续 / 不通过自动修订（≤3 轮）/ 卡住暂停等人工」**。

审核现状结论（详见 `docs/SESSION_HANDOFF_2026-06-13.md` 与代码）：

- **全自动多章循环后端+前端已具备**：`mode` 默认 `ai_auto_commit`、前端默认 3 轮修订、多章生产线自动推进。用户之前停在人工审批的 Run 是从「普通单章 Loop」入口（无 policy）发起的遗留 Run。
- **真正断裂在最前面**：创作中心（`creative.py`）只把想法生成成自由文本草稿存进 `CreativeRun`，不落库到正式表、不与章节上下文打通。
- **连续跑多章的连续性隐患**：`story_memory.py` 只写章节摘要，从不推进角色状态 → 越往后「开始前状态」越陈旧（第 6 章死循环根因）。

本次实现打通这两段，分阶段交付，全程增量、不破坏旧接口、**不新增数据表、不引入 Alembic 迁移**（复用既有通用暂存表 `StoryMemoryRecord`）。

## 阶段 A：Forward —— 想法 → 结构化前置物料 → 暂存 → 接受落库

把创作中心从「生成文本」升级为「生成结构化候选 + 逐条接受落进正式表」。

新增（全部 additive）：

- `app/schemas/story_engineering.py`：请求与候选 Pydantic schema（framework / characters / world_rules / chapter_plan）。
- `app/prompts/story_engineering/*.md`：四个结构化输出提示词。
- `app/services/story_engineering.py`：`generate_candidates`（调 adapter + `JsonGuard` 校验，拆条写 `StoryMemoryRecord` staged，原始调用记 `CreativeRun` 审计）；`accept_candidate` / `reject_candidate`（接受才落库）。
- `app/routers/story_engineering.py`：`POST /novels/{id}/story-engineering/generate`、`GET …/candidates`、`POST /story-engineering/candidates/{id}/accept|reject`；在 `app/main.py` 注册。
- 前端 `apps/web/src/components/CreativeStudio.tsx`：新增「结构化前置物料（逐条采纳）」区与候选卡片接受/拒绝、落库后引导启动多章生产线。

行为约束：候选 `status=staged`，**绝不直接写 Canon**；framework 接受时只填 `Novel` 的空字段、不覆盖已有内容；character 同名只补空字段；chapter_plan 新建 `Chapter`+`ChapterOutline`（order_index 取 max+1）。

测试 `tests/test_story_engineering_forward.py`：生成→staging→accept 各类型落库→reject 不落库→**断言 CanonState 不被污染**→无效 JSON 显式 422。

## 阶段 B：状态推进 —— 章节提交后结构化 Story Memory（根治连续性）

章节自动/人工提交后，除写摘要外，抽取角色状态变更候选；接受后推进 `CanonState`，让后续章节上下文自动用上最新状态。

- `app/schemas/story_engineering.py`：`CharacterStateChange` / `StateExtractionOutput`。
- `app/prompts/novel_loop/state_extractor.md`：状态抽取提示词。
- `app/agents/checkers.py`：`StateChangeExtractorAgent`（复用 `StructuredAgent`，ModelCall 日志正常记录）。
- `app/services/story_memory.py`：`stage_state_changes`，写 `StoryMemoryRecord(record_type=staged_state_change, status=staged)`。
- `app/workflow/runner.py`：在 `UPDATING_STORY_MEMORY` 状态（自动提交与人工 approve 都汇聚于此）摘要之后调用 `stage_state_changes`；**容错**——抽取失败不影响已提交章节，失败的 ModelCall 仍被记录（非静默吞错）。
- `app/services/story_engineering.py`：`accept_candidate` 扩展 `staged_state_change` 分支 → 推进 `CanonState.character_states_json[character_id]`，并同步 `Character.current_state_json`。
- 读端无需改：`context_builder.character_block` 已优先读 `canon.character_states_json`。
- 自动接受默认**关闭**（保持「卡住暂停等人工」语义，符合安全边界）。

测试 `tests/test_story_memory_state.py`（端到端 auto-run，mock provider）：提交后产生 staged 状态候选；接受前 Canon 为空且 `build_context` 不含新状态；接受后 `CanonState` 推进且 `build_context` 反映；拒绝则 Canon 不变。

## 数据与迁移

- **未新增数据表、未新增 Alembic 迁移**。候选复用 `story_memory_records`（部署版已存在，迁移 `f3a421d91870`）；落库目标 `Novel`/`Character`/`WorldRule`/`Chapter`/`ChapterOutline`/`CanonState` 均为既有表。
- `record_type` 取值新增：`staged_framework` / `staged_character` / `staged_world_rule` / `staged_chapter_plan` / `staged_state_change`；`status` 取值新增 `staged` / `accepted` / `rejected`（均为值，非列）。

## 验证

```
cd services/api && .venv/bin/pytest -q     # 52 passed（原 48 + 阶段A 2 + 阶段B 2）
cd apps/web && npm run build               # tsc + vite build 通过
```

部署生效：同阶段六修复，需 `./scripts/sync_to_deployed.sh --all`（含新文件）同步到部署版并重启 api，新接口才在运行后端生效。

## 未完成 / 后续

- 状态抽取目前覆盖**角色状态**；时间线、关系、伏笔、冲突的结构化抽取与落库（Foreshadowing/PlotThread/TimelineEvent/relationships）留待后续。
- 低风险候选自动接受策略（默认关）尚未实现，留作 policy 开关。
- 前端尚无独立的「状态候选/前置物料」专属页（目前在创作中心列表内采纳）。
- 可选「收敛保护」：一轮修订后 major 数没下降就提前停并给人工说明，而非空烧 3 轮。

## 回滚

全部 additive：新 router 不注册 / 新文件删除即恢复；不碰旧接口、旧表、已有 ChapterVersion；未接受的候选不影响任何正式数据；无迁移、无需 DB 回滚。
