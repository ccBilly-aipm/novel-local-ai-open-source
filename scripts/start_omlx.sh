#!/usr/bin/env bash
# 按需启动 oMLX 服务(含 14B 去审核 Josiefied-Qwen3-14B-abliterated）。
# 用法：要拆解前在终端里运行本脚本；用完按 Ctrl+C 停止（不常驻）。
set -euo pipefail

echo "→ 停掉已有的 8003 oMLX 服务（若有）..."
pkill -f "omlx serve --port 8003" 2>/dev/null || true
sleep 1

echo "→ 启动 oMLX（端口 8003，含 model_dir 里的 14B + HF 缓存模型）"
echo "  用完按 Ctrl+C 停止。"
exec "$HOME/.omlx/bin/omlx" serve \
  --port 8003 \
  --hf-cache \
  --api-key local-novel-key \
  --memory-guard balanced \
  --log-level warning
