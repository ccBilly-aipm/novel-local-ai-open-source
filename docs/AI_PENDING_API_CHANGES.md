# 待办：需要改后端 / API 的事项（任务在跑时先记录、不改）

> 约定：本文件记录“需要动后端（services/api）才能完成、但当前因有任务在跑而暂缓”的改动。
> 等本地长任务（拆解 / 多章生产线）跑完、可安全重启 api 时再实施。全部按增量（additive）执行，遵守 CLAUDE.md 铁律。

## 1. oMLX 设为“内置默认”运行时（前端卡片已先行落地）

**用户诉求（2026-06-13）**：拆解人物这类“频繁读小说、频繁加载/切换模型”的任务，oMLX 比 LM Studio 更合适；
把 oMLX“默认内置”，并在「本地模型」页加上去。

**已完成（纯前端，无需动 API）**：
- 「本地模型」页（`LocalModelCenter.tsx` 顶部）新增 oMLX vs LM Studio 对比 + 接入建议卡片（常驻显示）。
- `ModelSettings.tsx` 的运行时类型预设里本就内置 `omlx`（base `127.0.0.1:8000/v1`），可直接选用。

**待办（需动 API，暂缓）**：
1. **自动探测**：`local-inventory` 扫描器（`app/routers/model_providers.py` / 对应 service）增加 oMLX 探测——
   检测 oMLX 服务是否在跑、列出其已加载/可用模型，像 LM Studio 一样进 `inventory.models`，
   让「本地模型中心」列表里真正“出现 oMLX 的模型”，而不仅是静态卡片。
2. **自动内置 Provider**：`POST /model-providers/sync-local` 在检测到 oMLX 安装/运行时，
   自动 upsert 一条 oMLX Provider（type=`omlx`，base `127.0.0.1:8000/v1`，幂等、按 base_url+type 去重），
   即“默认内置”。注意不要与用户手建的重复。
3. **（可选）角色默认**：拆解 / Checker 角色在存在 oMLX provider 时默认指向它（仅默认值，可被覆盖）。

**约束**：增量、无迁移、幂等；不得在有任务运行时重启 api；改完按 CLAUDE.md 跑
`cd services/api && .venv/bin/pytest -q` 全绿后再 `sync_to_deployed.sh` + 重启 api。

**接入端口备注**：会话中曾用 `omlx serve --port 8003 --api-key local-novel-key` 起服务；
而前端预设写的是 `:8000`。落地探测/内置时需统一端口与可选 api-key（来自 provider 配置，勿硬编码凭据）。

## 2.（占位）网页搜索/子代理模型配置

与本仓库无关，属用户 `~/.claude/settings.json` 的模型路由问题（haiku 档被指向不存在的 `deepseek-v4-flash`）。
已在会话中向用户说明，待用户确认 provider 取向后修复并重启 Claude Code。不涉及本项目代码。

## 3. 拆解性能优化（7 万字跑 3 小时 → 目标 5~15 分钟）

**根因（量化）**：`deconstruction.py` 里 `MAX_CHUNK_TOKENS=2000` → 7 万字≈35 块；
`for dimension(10) → for chunk(35)` 全串行 = **~350 次模型调用、单 provider、可能开了 thinking**。
350 × ~30s ≈ 2.9h，与实测吻合。

**✅ 已落地 2026-06-13（"稳妥提速"，用户选定）**：大分块默认 2000→6000(可 `options.chunk_tokens` 覆盖) + 增量逐块 upsert 落库 + 幂等续跑(processed_units 重置) + 启动孤儿清理。62 测试全绿、已部署重启 api。
**仍未做（"最大提速"档，用户本次未选 / 需 oMLX）**：① 合并维度(10→1~3) ② 线程池并发。小模型抽取属配置项（用户启动拆解时选小 provider 即可，无需改码）。

**按 ROI 排序的改法（均需动 services/api，等任务跑完/可重启 api 时做，全部增量）**：
1. **合并维度**：每块从 10 次抽取 → 1~3 次（一个 prompt 一次性抽多维度，或按 叙事/结构/文风 分 3 组）。≈3~10× ↓ 调用数。改 `_map_chunk` 循环 + 新的多维 prompt + 解析多字段。
2. **增大分块**：`MAX_CHUNK_TOKENS` 2000 → 6000~10000（配 32k+ ctx 模型）。≈3~5× ↓ 块数。注意过长会漏检，6~10k 为甜区。
3. **小模型抽取**：Map 阶段用 Qwen3-4B/8B(MLX 4bit) 等小模型（抽取≠创作），创作仍用大模型。复用已有 writer/checker 角色：把 checker/extractor 指到小模型。≈3~5×/call + 省内存。
4. **并行**：用线程池并发跑 N 块/维度（2~4 并发），后端 provider 换成支持批处理的 oMLX / mlx-lm（LM Studio 默认串行）。≈2~4×。
5. **关 thinking + 限 max_tokens**：抽取设 `enable_thinking:false`，避免推理烧 token。
6. **（可选）投机解码**：runtime 级，小 draft 模型 1.5~3.3×。

**约束**：增量、无迁移、不在有任务运行时重启 api；改完 `pytest -q` 全绿再同步部署。
**临时缓解（无需改后端，用户可立刻做）**：拆解时选小模型 provider + 该 provider 选项里 thinking 关、max_tokens 调小 + 少选几个维度。

### 3.1 候选可见性 / 续跑健壮性（同源问题，2026-06-13 排查发现）

**现象**：运行记录里 `decon_worldbuilding` 已成功多条，但"候选待采纳"无世界观。
**根因**：`DeconstructionRunner.execute` 对每个维度**先跑完全部分块、再在维度末尾一次性 `_write_candidates`**（deconstruction.py:256-262）。
所以某维度未跑完时，它的逐块抽取结果只在内存 `payloads` 里，DB 无候选；该维度抽取 JSON 其实都在 `creative_runs.response`，未丢。
**要修（增量、需动后端）**：
- **每块增量落库**：`_map_chunk` 后即按该块 payload reduce/upsert 写候选（按 dimension+key 去重 upsert），候选逐步可见，且中途中断不丢、不必重跑整维。
- **幂等续跑**：`execute` 续跑时跳过已完成的 (dimension, chunk)（按已写候选/已 completed 的 CreativeRun 判定），不要从维度循环头重跑、不要重复 `processed_units +=1`。
- **孤儿清理**：启动 `recover_pending` 时把残留 `running` 的 CreativeRun 标记为 `failed`（已发现 1 个从 20:18 挂起的孤儿）。
**当前状态**：run `6b8079f8` 已 completed（972 候选）。

## 4. 合并维度 + 并发（"最大提速"档，已落地 2026-06-13）

用户确认后实现并部署：
- **合并抽取**：`combined_map.md` + `CombinedDecon` schema + `_map_chunk_combined`，每块一次调用抽全部维度；`merge_dimensions` 选项开启（默认关，保持逐维度质量）。
- **并发**：`_run_combined` 线程池（`max_parallel`，默认 1），模型调用并发、**仅主线程写库**避免竞争；每 worker 独立 SessionLocal。
- **选项隔离**：`_model_options` 剔除 `merge_dimensions/max_parallel/chunk_tokens`，不污染模型请求体。

**实测（oMLX `Qwen3-8B-4bit`，真实小说 2 块切片）**：
- A 逐维度基线 232s / 20 调用｜ B 合并串行 106s（2.2×）｜ C 合并并发×3 65s（**3.6×**）。

**对抗式审查（10 agent，逐条反驳验证）确认 4 个问题，已全部修复**：
1. 合并截断 = 整块全丢 → 加 `COMBINED_MIN_OUTPUT_TOKENS=4096` 下限 + 解析失败**回退逐维度**(`_extract_chunk_combined`)。实测 8B 确会截断，回退可救回候选。
2. 无名键(loose)互相覆盖丢数据 → `_dedup_key` 对空键用内容哈希。
3. 每块重跑整段 reduce O(n²) → `_fold_into_index` 改为增量线性折叠。
4. 子集+合并仍要全 10 维 → 合并提示词按 `{{requested_dimensions}}` 动态标注。

测试 64 passed（含合并 + 回退回归）。

**三次 oMLX Qwen3-8B 实测结论（重要）**：
| 跑法 | 无下限 | 4096 | 8000 |
|---|---|---|---|
| A 逐维度基线 | 232s/57 | 190s/59 | 185s/49 |
| B 合并串行 | 106s/26(丢) | 103s/47(1.8×) | 201s/47(0.9×) |
| C 合并并发 | 65s/36(丢) | 158s/47 | 191s/52 |

- **合并全 10 维在 8B 上不可靠**：一次性大 JSON 容易写出语法错（不是长度问题），越给预算越长越易坏 → 触发回退、反而慢。8000 实测更差，已撤回到 **4096**。
- **回退机制有效**：候选不再丢（26→47，接近基线），但失败那块不再快。
- **可靠的提速结论**：靠 **逐维度(默认) + 小模型(8B 而非 27B) + 大分块**，70k 从 ~3h → **~20-30min 且稳定**。`merge_dimensions` 保留为**可选实验项（默认关）**，仅在 JSON 可靠的模型或将来"分组(2~3 次/块)"下才值得开。
### 4.1 分组合并（已实现 + 实测，2026-06-13）

把 `_run_combined` 改为"维度分组"（`group_size` 默认 4 → 10 维分 3 组，工作单元 = 块×组，可并发）；
前端加「快速模式」开关。**但 oMLX Qwen3-8B 实测分组反而更慢**：
| 跑法 | 耗时 | 调用 | 候选 |
|---|---|---|---|
| A 逐维度基线 | 194s | 20 | 60 |
| B 分组串行 | 349s(0.6×) | 14 | 47 |
| C 分组并发x3 | 222s(0.9×) | 12 | 49 |

- 原因：分组本应 6 次调用，实际 12~14 次 → **有的组仍写坏 JSON 触发逐维度回退**（坏组 = 1 次大调用浪费 + N 次补调用），加上 8B 输出啰嗦，净更慢。
- **四轮基准结论**：合并/分组在 8B 上**从未真正赢过逐维度**（不是丢候选就是更慢），根因是 8B 不擅长一次性结构化 JSON。
- **决定**：前端「快速模式」**默认关**（`useState(false)`），保留为可选项（换 JSON 更稳的模型时再开）。**默认走逐维度——既最稳、也不更慢。** 后端分组代码与测试保留。
- **8B 上真正可靠的提速 = 小模型 + 大分块 + 逐维度增量**（≈3h→20-30min，稳定）。

### 4.2 已知小问题（建议后续修）
- `theme` 维度每轮都因 `motifs` 被模型返回成**数组**而 Pydantic 校验失败丢该维度（`DeconTheme.motifs: str`）。建议把 motifs 改为可接受 list 或在 JsonGuard 前做"list→字符串"宽松强制。属数据质量小修，不影响其它维度。
