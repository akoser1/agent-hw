#!/usr/bin/env bash
# Rebuilds ./test_repo — the shared testbed for both agents.
#   1. copies testbed/baseline into test_repo/ and commits it with git ("baseline")
#   2. copies testbed/change over it, leaving those edits UNCOMMITTED
# DiffTest tests the uncommitted change (git diff HEAD); Summarizer summarizes every .py file.
#   bash reset_testbed.sh             baseline commit + pending change (default)
#   bash reset_testbed.sh --no-change baseline commit only
set -euo pipefail
cd "$(dirname "$0")"
rm -rf test_repo
cp -r testbed/baseline test_repo
cd test_repo
git init -q
git -c user.email=testbed@example.com -c user.name=testbed add -A
git -c user.email=testbed@example.com -c user.name=testbed commit -qm "baseline"
if [[ "${1:-}" != "--no-change" ]]; then
  cp -r ../testbed/change/. .
  echo "test_repo ready: baseline committed, pending change in: $(git diff --name-only | tr '\n' ' ')"
else
  echo "test_repo ready: baseline only (no pending change)"
fi
