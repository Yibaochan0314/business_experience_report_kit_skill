#!/usr/bin/env bash
# 版本快照：把当前 skill 完整复制一份到快照目录，用于日后 diff 与回滚。
#
# 用法：
#   ./snapshot.sh                     # 默认输出到 <skill 上两级>/skill-snapshots/
#   ./snapshot.sh /path/to/outdir     # 指定输出目录
#
# 维护约定（改完 skill 后按序做这三步）：
#   1. 在 CHANGELOG.md 顶部追加一条新版本说明
#   2. 更新 SKILL.md frontmatter 的 version 字段
#   3. 跑本脚本留快照，然后重新打包
#
# 注意：快照必须留在 skill 目录**之外**，否则会被 package_skill 打包进 zip、污染分发包。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_NAME="$(basename "$SKILL_DIR")"

# 默认输出目录：skill 的上两级 + /skill-snapshots（用户级 skill 即 ~/.workbuddy/skill-snapshots/）
# 刻意放在 skills/ 之外，避免被 skill 扫描器误识别成一个技能包
DEFAULT_OUT="$(cd "$SKILL_DIR/../.." && pwd)/skill-snapshots"
OUT_ROOT="${1:-$DEFAULT_OUT}"

# 读 version。注意：set -e + pipefail 下 grep 找不到匹配会直接终止脚本，
# 于是下面「找不到 version」的报错分支永远执行不到、用户只看到静默退出。
# 所以先 || true 兜住，把判空交给下面。
RAW_VERSION="$(grep -m1 '^version:' "$SKILL_DIR/SKILL.md" || true)"
VERSION="$(printf '%s' "$RAW_VERSION" | cut -d: -f2 | sed 's/[^0-9A-Za-z._-]//g')"

if [ -z "$VERSION" ]; then
  echo "错误：未在 $SKILL_NAME/SKILL.md 的 frontmatter 里找到 version 字段。" >&2
  echo "请先补上 version（例如 version: 1.2.0）再跑快照。" >&2
  exit 1
fi

DATE="$(date +%Y-%m-%d)"
DEST="$OUT_ROOT/${SKILL_NAME}-v${VERSION}-${DATE}"

if [ -e "$DEST" ]; then
  echo "快照已存在：$DEST"
  echo "同一天同一版本只留一份。如果是修正后想再留快照，请先升 version。"
  exit 0
fi

mkdir -p "$OUT_ROOT"
cp -R "$SKILL_DIR" "$DEST"

# 清掉不该进快照的东西
rm -rf "$DEST/.git" "$DEST/dist" "$DEST/__pycache__" 2>/dev/null || true
find "$DEST" -name '.DS_Store' -delete 2>/dev/null || true

echo "快照完成：$DEST"
echo "  版本 v$VERSION ｜ 日期 $DATE ｜ 文件 $(find "$DEST" -type f | wc -l | tr -d ' ') 个"
echo
echo "还没做的话，补上："
echo "  1) CHANGELOG.md 追加 v$VERSION 的变更说明"
echo "  2) 重新打包；已装旧版的接收方需要覆盖安装"
