"""Checker 基准的候选模型清单（去重后的真实 provider）。

按"在保证效果前提下用更小模型"的目标，覆盖 8B → 40B 的同量级横向对比。
service 决定 base_url 与 api_key：oMLX(:8003) / LM Studio(:1234)。

每项：label(展示名) · service · model(真实模型id) · param_b(参数B) · category(去审核/改版/官方版) · note
"""

OMLX = {"base_url": "http://127.0.0.1:8003/v1", "api_key": "local-novel-key"}
LMS = {"base_url": "http://127.0.0.1:1234/v1", "api_key": "lm-studio"}


def _c(label, svc, model, param_b, category, note=""):
    runtime = OMLX if svc == "oMLX" else LMS
    return {
        "label": label, "service": svc, "model": model,
        "param_b": param_b, "category": category, "note": note,
        "base_url": runtime["base_url"], "api_key": runtime["api_key"],
    }


# 顺序：先小后大、同量级聚拢。小的优先（目标是找到"够用的最小模型"）。
CANDIDATES = [
    # —— 小档（基线对照）——
    _c("官方版 · Qwen3 8B", "oMLX", "mlx-community--Qwen3-8B-4bit", 8, "官方版", "小快基线"),
    _c("去审核 · Qwen3 14B", "oMLX", "Josiefied-Qwen3-14B-abliterated-v3-4bit", 14, "去审核", "去审核基线(预期差)"),
    # —— 26-27B 档（横向对比的主战场）——
    _c("官方版 · Gemma 26B-A4B", "oMLX", "gemma-4-26b-a4b-it-4bit", 26, "官方版", "Gemma MoE 官方"),
    # _c("官方版 · Qwen3.5 27B", "oMLX", "Qwen3.5-27B-4bit", ...) —— 已于 2026-06-14 删除(检查JSON坏，与蒸馏版重复)
    _c("Opus蒸馏 · Qwen3.5 27B", "oMLX", "Qwen3.5-27B-Claude-4.6-Opus-Distilled-MLX-4bit", 27, "改版", "当前推荐·Opus蒸馏"),
    # _c("qwopus合并 · Qwen3.6 27B", "LM Studio", "qwopus3.6-27b-v1-preview@q6_k", ...) —— 已删除(检查误报38%、正文偏长)
    _c("去审核 · Qwen3.6 27B crack", "LM Studio", "qwen3.6-27b-crack", 27, "去审核", "去审核 27B"),
    # —— 31-40B 档（大模型上限）——
    # _c("去审核 · Gemma 31B", "LM Studio", "gemma-4-31b-jang_4m-crack", ...) —— 已删除(JANG_4M-CRACK 模型本身坏，两个MLX运行时都加载不了)
    _c("Opus推理蒸馏 · Qwen3.6 35B", "LM Studio", "qwen3.6-35b-a3b-claude-4.6-opus-reasoning-distilled", 35, "改版", "Opus 推理蒸馏 35B MoE"),
    _c("去审核 · Qwen3.6 40B Opus", "LM Studio", "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-neo-code-di-imatrix-max", 40, "去审核", "去审核 40B Opus 上限"),

    # —— 2026-06 调研下载的新候选（非去审核、近期、Mac 可跑）——
    _c("Opus蒸馏 · Qwen3.6 27B(新)", "LM Studio", "qwen3.6-27b-claude-opus-reasoning-distilled", 27, "改版", "现役Opus蒸馏的3.6代升级版(GGUF)"),
    _c("GLM-4.7-Flash 30B-A3B", "oMLX", "mlx-community--GLM-4.7-Flash-4bit", 30, "官方", "智谱·MoE激活3B·快·非去审核"),
    _c("官方 · Gemma-4 12B", "oMLX", "mlx-community--gemma-4-12B-it-4bit", 12, "官方", "6月3日最新·最小最快·非去审核"),
]
