#!/usr/bin/env bash
set -euo pipefail

REPO_URL="git+https://github.com/saikumar1767/Sentinel-Ops.git"

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -m pip install --user uv
    return
  fi

  if command -v python >/dev/null 2>&1; then
    python -m pip install --user uv
    return
  fi

  echo "Python 3.11+ not found. Install Python first, then rerun installer." >&2
  exit 1
}

ensure_uv
uv tool install --force --from "$REPO_URL" sentinel-ops

echo
echo "SentinelOps installed."
echo "Run: sentinelops"
