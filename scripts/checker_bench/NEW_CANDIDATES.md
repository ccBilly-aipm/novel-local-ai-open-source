# 近一个月可用的"检查角色"新模型候选（2026-06-14 联网调研，逐个核验发布时间+Mac适配）

硬约束：Mac ~32GB（oMLX 上限 ~25.6GB，可用磁盘 ~24GB；31B-4bit/23.8GB 已加载失败）。
检查角色要：强推理(thinking)+稳 JSON+中文+**非去审核**。下列均为【非去审核】，可装。

## ★ 第一梯队（最该下来测）

| 模型 | 参数 | 发布 | 体积/格式 | 为何 |
|---|---|---|---|---|
| **rico03/Qwen3.6-27B-Claude-Opus-Reasoning-Distilled** | 27B dense | 2026-04-23 | GGUF Q4_K_M 16.5G（LM Studio）；无现成4bit MLX | **你现用 Opus蒸馏 的 Qwen3.6 下一代**。同样 Claude-4.6-Opus 推理蒸馏、非去审核、带`<think>`。最可能直接超过现役 |
| **zai-org/GLM-4.7-Flash** | 30B-A3B MoE(~3B激活) | 2026-01-19 | MLX 4bit 16.9G（oMLX）；GGUF 也有 | 不同家族(智谱)、MIT、preserved thinking、强 tool-call/JSON、中文母语、**MoE 故快**。"又快又准"的最大希望 |

## ☆ 第二梯队（值得一试）

| 模型 | 参数 | 发布 | 体积 | 备注 |
|---|---|---|---|---|
| google/gemma-4-12B-it | 12B dense | **2026-06-03**(最新) | GGUF 7G / MLX ~10G | 最新最小、官方非去审核、configurable thinking+原生JSON。但 Gemma-26B 检查已 fail，12B 更小是长shot，胜在快+新 |
| Qwen/Qwen3.6-27B（官方） | 27B dense | 2026-04-22 | MLX/GGUF 16G | 官方非去审核、thinking。**坑**：是多模态 VLM，MLX 要 mlx-vlm，oMLX 纯文本管线可能不兼容→建议走 GGUF+LM Studio |
| Qwen3-30B-A3B-Thinking-2507 | 30B-A3B MoE | 2025-07（非近期） | MLX 4bit 17.2G | 成熟保底牌：非去审核 thinking-only、中文强、MoE 快。但不是"近一个月" |

## 不适配 / 排除
- Qwen3.6-35B-A3B 官方：MLX 4bit 21.6G，逼近 25.6G 上限，有风险（已测同代 Opus推理蒸馏35B=50% fail）。
- 一切 abliterated/heretic/uncensored/crack（DavidAU/huihui/HauhauCS/AEON 等）：**只配正文/拆解**，做检查必废（与既有实测一致）。
- gemma-4-26B-A4B-it 官方 = 你已测的那个（33% fail）。

## 判读
- 你现役 Opus蒸馏 Qwen3.5-27B 已是地板；要超过它，最有戏的是**同款的 3.6 代(rico03)** 和 **GLM-4.7-Flash(快)**。
- "更小更快"的真希望在 MoE（GLM-4.7-Flash 30B-A3B、Qwen3-30B-A3B）和 gemma-4-12B；但 MoE 激活小可能像 35B-A3B 那样漏检——必须实测。
