#!/bin/bash
exit $(curl -s https://api.github.com/repos/SchaleDB/SchaleDB/commits/main | jq -r "((now - (.commit.author.date | fromdateiso8601) )  / (60*60*24)  | trunc)")