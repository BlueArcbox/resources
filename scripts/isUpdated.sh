#!/bin/bash

# 获取 jp 分支最近一次提交的天数
days_jp=$(curl -s https://api.github.com/repos/electricgoat/ba-data/commits/jp | jq -r "((now - (.commit.author.date | fromdateiso8601)) / (60*60*24) | trunc)")

# 获取 global 分支最近一次提交的天数
days_global=$(curl -s https://api.github.com/repos/electricgoat/ba-data/commits/global | jq -r "((now - (.commit.author.date | fromdateiso8601)) / (60*60*24) | trunc)")

# 比较两个分支的天数，取较小者
if [ "$days_jp" -lt "$days_global" ]; then
  exit $days_jp
else
  exit $days_global
fi