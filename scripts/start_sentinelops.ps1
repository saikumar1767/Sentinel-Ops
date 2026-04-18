param(
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$appHost = "127.0.0.1"
$appPort = "8000"
$consoleUrl = "http://${appHost}:$appPort/console"
$healthUrl = "http://${appHost}:$appPort/health"
$ollamaHost = if ($env:SENTINELOPS_OLLAMA_HOST) { $env:SENTINELOPS_OLLAMA_HOST } else { "http://127.0.0.1:11434" }

Write-Host "Starting the SentinelOps local stack..."
Write-Host "Project root: $projectRoot"

try {
  Invoke-RestMethod "$ollamaHost/api/tags" -TimeoutSec 2 | Out-Null
  Write-Host "Ollama is reachable at $ollamaHost"
} catch {
  Write-Warning "Ollama did not respond at $ollamaHost. Start 'ollama serve' in another window if the app cannot answer model requests."
}

& (Join-Path $PSScriptRoot "start_chroma_wsl.ps1")

$listener = Get-NetTCPConnection -LocalPort $appPort -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  Write-Host "SentinelOps is already listening on port $appPort."
} else {
  $serveCommand = "Set-Location '$projectRoot'; uv run uvicorn app.main:app --host $appHost --port $appPort"
  Write-Host "Launching FastAPI in a new PowerShell window..."
  Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $serveCommand | Out-Null
}

$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
  try {
    Invoke-RestMethod $healthUrl -TimeoutSec 2 | Out-Null
    Write-Host "SentinelOps is responding at $consoleUrl"
    if (-not $NoBrowser) {
      Start-Process $consoleUrl | Out-Null
    }
    Write-Host "SentinelOps is ready."
    exit 0
  } catch {
    Start-Sleep -Seconds 1
  }
}

throw "SentinelOps did not become ready at $healthUrl within 45 seconds."
