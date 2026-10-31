#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Termux 一键推送脚本（commit 备注固定）
# 用法（在本项目目录内执行）：
#   首次推送：  bash termux_push.sh https://github.com/你的用户名/仓库名.git
#   增量更新：  bash termux_push.sh
# 推送时：Username 填 GitHub 账号名，Password 粘贴 PAT 令牌
# ============================================================
set -e
MSG="upload from workbuddy android termux"
cd "$(cd "$(dirname "$0")" && pwd)"

if [ -n "$1" ]; then
  # ---------- 首次推送 ----------
  REPO="$1"
  git init
  git branch -M main
  git add .
  git commit -m "$MSG" || echo "无变更可提交"
  git remote remove origin 2>/dev/null || true
  git remote add origin "$REPO"
  git push -u origin main || {
    echo ""
    echo ">>> 首次推送失败：远程仓库可能自带 README/LICENSE 或已有历史提交。"
    echo ">>> 正在尝试合并远程文件后重新推送..."
    git pull origin main --allow-unrelated-histories --no-rebase || true
    git add .
    git commit -m "$MSG" || true
    git push -u origin main || {
      echo ""
      echo ">>> 合并后仍推送失败（本地与远程历史分叉且存在冲突）。"
      echo ">>> 若确认远程没有需要保留的内容，手动执行强制推送："
      echo ">>>   git push -u origin main --force"
      exit 1
    }
  }
else
  # ---------- 增量更新 ----------
  git add .
  git commit -m "$MSG" || echo "无变更可提交"
  git push
fi

echo ""
echo ">>> 完成。最新下载链接见 lists/LINKS.md（由 GitHub Actions 自动生成）"
