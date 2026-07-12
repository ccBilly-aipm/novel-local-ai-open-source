#!/usr/bin/env bash
set -euo pipefail

HF="${HF:-$(command -v hf || true)}"
LMS="${LMS:-$(command -v lms || true)}"

[[ -n "$HF" ]] || { echo "找不到 hf CLI，请先安装并登录 Hugging Face CLI。"; exit 1; }
[[ -n "$LMS" ]] || { echo "找不到 lms CLI，请先安装 LM Studio CLI。"; exit 1; }

echo "[$(date +%H:%M:%S)] 开始并行下载 3 个模型"
"$HF" download mlx-community/GLM-4.7-Flash-4bit       > glm_dl.log   2>&1 &
P1=$!
"$HF" download mlx-community/gemma-4-12B-it-4bit      > gemma_dl.log 2>&1 &
P2=$!
"$LMS" get "rico03/Qwen3.6-27B-Claude-Opus-Reasoning-Distilled-GGUF@Q4_K_M" -y --gguf > rico_dl.log 2>&1 &
P3=$!
wait $P1; echo "[$(date +%H:%M:%S)] GLM 完成 rc=$?"
wait $P2; echo "[$(date +%H:%M:%S)] gemma 完成 rc=$?"
wait $P3; echo "[$(date +%H:%M:%S)] rico(GGUF) 完成 rc=$?"
echo "[$(date +%H:%M:%S)] === 全部下载结束 ==="
