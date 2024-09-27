#!/bin/bash
exit $(curl -s https://api.github.com/repos/electricgoat/ba-data/commits/jp | jq -r "((now - (.commit.author.date | fromdateiso8601) )  / (60*60*24*3)  | trunc)")