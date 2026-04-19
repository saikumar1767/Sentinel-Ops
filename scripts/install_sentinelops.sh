#!/usr/bin/env bash
set -euo pipefail

PACKAGE_URL="https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip"

ensure_user_bin_on_path() {
  local user_base=""

  if command -v python3 >/dev/null 2>&1; then
    user_base="$(python3 - <<'PY'
import site
print(site.USER_BASE)
PY
)"
  elif command -v python >/dev/null 2>&1; then
    user_base="$(python - <<'PY'
import site
print(site.USER_BASE)
PY
)"
  else
    user_base="$HOME/.local"
  fi

  export PATH="${user_base}/bin:$PATH"
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi

  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ensure_user_bin_on_path
    if command -v uv >/dev/null 2>&1; then
      return
    fi
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -m pip install --user uv
    ensure_user_bin_on_path
    if command -v uv >/dev/null 2>&1; then
      return
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    python -m pip install --user uv
    ensure_user_bin_on_path
    if command -v uv >/dev/null 2>&1; then
      return
    fi
  fi

  echo "Could not install uv automatically. Install uv or Python 3.11+ first, then rerun the installer." >&2
  exit 1
}

ensure_user_bin_on_path
ensure_uv
uv tool install --force --from "$PACKAGE_URL" sentinel-ops

echo
echo "SentinelOps installed."
echo "Run: sentinelops"
