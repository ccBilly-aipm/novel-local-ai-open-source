#!/usr/bin/env bash
#
# sync_to_deployed.sh
# 把开发版仓库的后端代码同步到“部署版”（LaunchAgent 实际运行的那一份），并重启 api。
#
# 背景：本机有两份独立副本——
#   - 开发版仓库：本仓库（你在这里改代码）
#   - 部署版：~/Library/Application Support/NovelLocalAI/...，由 com.novel-local-ai.api.plist 启动，
#             端口 8000，app 界面真正在用的就是这一份。
# 提示词按“正在运行的那份代码”的相对路径加载（app/agents/base.py 的 PROMPT_ROOT），
# 所以只改仓库、不同步到部署版，运行的后端是看不到的。
#
# 用法：
#   ./scripts/sync_to_deployed.sh                # 默认：只同步下面 FILES 列表中的文件
#   ./scripts/sync_to_deployed.sh --all          # 同步整个 app/ 源码目录（rsync，排除缓存/数据库）
#   ./scripts/sync_to_deployed.sh --dry-run      # 只显示将要做什么，不实际改动
#   ./scripts/sync_to_deployed.sh --no-restart   # 同步但不重启 api
#   APP=/绝对路径/到/部署版/services/api ./scripts/sync_to_deployed.sh   # 手动指定部署版路径
#
# 安全保证：
#   - 同步前会把部署版被覆盖的文件备份到部署版目录下的 _deployed_backup_<时间戳>/
#   - 只动代码，绝不碰部署版数据库（~/Library/Application Support/NovelLocalAI/data/ 不在 app/ 下）
#   - 默认会要求你确认一次

set -euo pipefail

# ---- 需要同步的文件（相对 services/api 的路径）。要加文件就往这里加。----
FILES=(
  "app/prompts/novel_loop/continuity_checker.md"
  "app/prompts/novel_loop/revision_writer.md"
  "app/services/context_builder.py"
)

LABEL="com.novel-local-ai.api"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

DRY_RUN=0
SYNC_ALL=0
DO_RESTART=1
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=1 ;;
    --all)        SYNC_ALL=1 ;;
    --no-restart) DO_RESTART=0 ;;
    -h|--help)    grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$arg（用 --help 查看用法）"; exit 2 ;;
  esac
done

# ---- 定位开发版仓库的 services/api ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)/services/api"
[[ -f "$REPO/app/main.py" ]] || { echo "❌ 找不到开发版后端：$REPO/app/main.py"; exit 1; }

# ---- 定位部署版的 services/api ----
if [[ -z "${APP:-}" ]]; then
  if [[ -f "$PLIST" ]]; then
    APP="$(/usr/libexec/PlistBuddy -c 'Print :WorkingDirectory' "$PLIST" 2>/dev/null || true)"
  fi
fi
if [[ -z "${APP:-}" || ! -f "$APP/app/main.py" ]]; then
  echo "❌ 没能自动确定部署版路径。"
  echo "   请先看一下 LaunchAgent 配置里的 WorkingDirectory："
  echo "     cat \"$PLIST\""
  echo "   然后用环境变量指定后重跑，例如："
  echo "     APP=/部署版/services/api ./scripts/sync_to_deployed.sh"
  exit 1
fi

echo "开发版仓库 : $REPO"
echo "部署版目标 : $APP"
echo "重启 api   : $([[ $DO_RESTART -eq 1 ]] && echo 是 || echo 否)"
echo "模式       : $([[ $SYNC_ALL -eq 1 ]] && echo '整个 app/ 目录' || echo '指定文件列表')"
[[ $DRY_RUN -eq 1 ]] && echo "（DRY-RUN：只演示，不改动）"
echo

if [[ "$REPO" == "$APP" ]]; then
  echo "✅ 开发版与部署版指向同一目录，无需同步。"
  exit 0
fi

# ---- 备份 ----
TS="$(date +%Y%m%d-%H%M%S)"
BK="$APP/_deployed_backup_$TS"

if [[ $SYNC_ALL -eq 1 ]]; then
  command -v rsync >/dev/null || { echo "❌ 需要 rsync"; exit 1; }
  echo "将把部署版 app/ 备份到：$BK/app/"
  echo "然后用仓库 app/ 覆盖（排除 __pycache__、*.pyc）。"
  if [[ $DRY_RUN -eq 0 ]]; then
    read -r -p "确认继续？输入 yes： " ans; [[ "$ans" == "yes" ]] || { echo "已取消。"; exit 0; }
    mkdir -p "$BK"
    rsync -a "$APP/app/" "$BK/app/"
    rsync -a --exclude='__pycache__' --exclude='*.pyc' "$REPO/app/" "$APP/app/"
    echo "✅ 已同步整个 app/。备份在 $BK/app/"
  else
    rsync -a --itemize-changes --dry-run --exclude='__pycache__' --exclude='*.pyc' "$REPO/app/" "$APP/app/"
  fi
else
  echo "将同步以下文件（同名旧文件会先备份到 $BK/）："
  for f in "${FILES[@]}"; do echo "  - $f"; done
  echo
  if [[ $DRY_RUN -eq 0 ]]; then
    read -r -p "确认继续？输入 yes： " ans; [[ "$ans" == "yes" ]] || { echo "已取消。"; exit 0; }
  fi
  for f in "${FILES[@]}"; do
    src="$REPO/$f"; dst="$APP/$f"
    [[ -f "$src" ]] || { echo "⚠️  仓库缺少 $f，跳过"; continue; }
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "  会复制：$f"
      continue
    fi
    mkdir -p "$(dirname "$BK/$f")" "$(dirname "$dst")"
    [[ -f "$dst" ]] && cp "$dst" "$BK/$f"
    cp "$src" "$dst"
    echo "  ✅ $f"
  done
  [[ $DRY_RUN -eq 0 ]] && echo "备份在 $BK/"
fi

# ---- 重启 api（context_builder.py 是 Python 代码，必须重启才生效）----
if [[ $DO_RESTART -eq 1 && $DRY_RUN -eq 0 ]]; then
  echo
  echo "重启 $LABEL ..."
  launchctl kickstart -k "gui/$(id -u)/$LABEL" \
    && echo "✅ 已重启。注意：正在运行的 Run 会被标记为 BACKEND_RESTARTED，暂停/历史的 Run 不受影响。" \
    || echo "⚠️  重启失败，请手动执行：launchctl kickstart -k gui/\$(id -u)/$LABEL"
fi

echo
echo "完成。下一步：在 app 里对目标章节发起【全新 Run】（不要点“追加修订”去续旧 Run），新约束才会完整生效。"
echo "想确认是否真的生效：打开该 Run 的“高级日志”→ 最新一次 continuity_checker 调用 → prompt 里应能看到“判断基准 / 本章开始前状态”。"
