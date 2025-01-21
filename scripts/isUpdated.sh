#!/bin/bash
set -euo pipefail  # 启用严格模式：遇到错误退出，未定义变量报错，管道错误报错

# 从环境变量中获取仓库信息
REPO_OWNER=${REPO_OWNER:-}
REPO_NAME=${REPO_NAME:-}

# 检查必要的环境变量是否设置
if [[ -z "$REPO_OWNER" || -z "$REPO_NAME" ]]; then
  echo "ERROR: REPO_OWNER and REPO_NAME must be set."
  exit 1
fi

# 获取分支最近一次提交的天数
get_days_since_last_commit() {
  local branch=$1
  local commit_date

  # 获取分支的最新提交日期
  commit_date=$(curl -s "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/commits/$branch" | \
    jq -r ".commit.author.date")

  if [[ -z "$commit_date" || "$commit_date" == "null" ]]; then
    echo "ERROR: Failed to fetch commit date for branch $branch."
    exit 1
  fi

  # 计算距离当前时间的天数
  local days
  days=$(echo "scale=0; ( $(date +%s) - $(date -d "$commit_date" +%s) ) / (60*60*24)" | bc)
  echo "$days"
}

# 获取 jp 和 global 分支的天数
days_jp=$(get_days_since_last_commit "jp")
days_global=$(get_days_since_last_commit "global")

# 比较两个分支的天数，取较小者
if (( days_jp < days_global )); then
  exit "$days_jp"
else
  exit "$days_global"
fi