$ErrorActionPreference = "Stop"

$repoUrl = "git+https://github.com/saikumar1767/Sentinel-Ops.git"

function Ensure-Uv {
  if (Get-Command uv -ErrorAction SilentlyContinue) {
    return
  }

  if (Get-Command py -ErrorAction SilentlyContinue) {
    py -m pip install --user uv
    return
  }

  if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m pip install --user uv
    return
  }

  throw "Python not found. Install Python 3.11+ first, then run this installer again."
}

Ensure-Uv
uv tool install --force --from $repoUrl sentinel-ops

Write-Host ""
Write-Host "SentinelOps installed."
Write-Host "Run: sentinelops"
