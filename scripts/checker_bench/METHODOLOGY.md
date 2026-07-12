# Checker 选型基准 · 方法与素材

目标：为「连续性检查」角色（continuity_checker / state_extractor）选模型——**在保证效果的前提下用尽量小的模型**。
做法：固定一套不可变设定 + 一批埋了已知矛盾的长章节，逐级递增地考各候选模型的「真矛盾召回 / 不误报 / JSON 可用 / 是否真推理 / 耗时」。

## 文件

- `candidates.py` —— 候选模型清单（8B→40B，覆盖去审核/改版/官方版，跨 oMLX 与 LM Studio）。
- `cases.json` —— 对抗审查产出的分级测试用例（含共享设定 `context` 与 `cases[]`）。
  - 由 workflow `checker-testsuite-design` 生成：5 梯队并行设计 → 逐梯队对抗审查（防关键词作弊/防误报/验证难度确实递增）。
- `run_bench.py` —— 运行器：按轮次跑、增量把结果写进前端 `apps/web/src/data/checkerBench.json`、明细存 `results.json`。
- `results.json` —— 每次调用的逐条明细（可追溯）。

## 逐级递增的轮次（难度从低到高）

| 轮 | 名称 | 考点 | 判定 |
|---|---|---|---|
| R1 | 基础·本章内显式违规 | 不依赖记忆，对照规则即可发现（夜闯已锁档案馆=违规B、单人启动删除仪=违规C） | 召回 |
| R2 | 跨章记忆 | 必须记得往章+应用不可变规则（死者复活、已删记忆复活=违规A） | 召回 |
| R3 | 细微·角色属性冲突 | 与角色卡静态属性冲突且写得不显眼（眼睛颜色/旧疤/身份） | 召回 |
| R4 | 困难·多规则交织+干扰 | 真违规埋在大量合法相似信息里，需多规则/多状态交织定位 | 召回 |
| clean | 合法对照 | 看似可疑实则完全合法（白天查档/合法回忆/新决定） | 不误报 |

## 统一参数

- 思考(`chat_template_kwargs.enable_thinking`) = **ON**（实测：关掉则全员 0 召回，橡皮图章）。
- `temperature` = 0.1，`max_tokens` = 6000（给足推理预算，避免推理链未完即被截断、无 JSON 产出）。
- 每个用例跑 2 次取均值。耗时 > 8s 视为真触发了思考。

## 判定口径

- 每轮分数 = 该轮 error 用例的「真矛盾召回率」：模型 `passed=false` 且 issues 文本命中该用例全部关键词组（每组任一词命中即该组命中）才算「抓到」。
- 误报率 = clean 用例里被判 `passed=false` 或出 major/blocker 的比例（越低越好，理想 0）。
- verdict：`r1<80% 或 误报>25%` → ✗不可用；`r1≥80% 且 r2≥80% 且 r3≥60% 且误报低` → ✓可用；中间 → △勉强。

## 运行方式（串行，本机单卡，分轮增量）

```bash
cd services/api
# 先跑最简单一轮、只测 oMLX 候选（最快），跑完更新页面
ROUND=r1 SERVICE=oMLX .venv/bin/python ../../scripts/checker_bench/run_bench.py
# 再逐级加难
ROUND=r2 SERVICE=oMLX .venv/bin/python ../../scripts/checker_bench/run_bench.py
# LM Studio 候选（需先在 LM Studio 里可加载对应模型）
ROUND=r1 SERVICE="LM Studio" .venv/bin/python ../../scripts/checker_bench/run_bench.py
```

每轮跑完，重建并部署前端即可在「设置 → 本地模型 → 模型测试」看到更新。
注意：本机 oMLX/LM Studio 单卡，模型只能串行加载（并行会 507 OOM），故 run_bench 串行执行。
