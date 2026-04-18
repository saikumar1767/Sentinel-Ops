$ErrorActionPreference = "Stop"

$distro = if ($env:SENTINELOPS_CHROMA_WSL_DISTRO) { $env:SENTINELOPS_CHROMA_WSL_DISTRO } else { "Ubuntu" }
$port = if ($env:SENTINELOPS_CHROMA_PORT) { $env:SENTINELOPS_CHROMA_PORT } else { "8012" }
$dataDir = if ($env:SENTINELOPS_CHROMA_WSL_DATA_DIR) { $env:SENTINELOPS_CHROMA_WSL_DATA_DIR } else { '$HOME/.sentinelops/chroma-data' }
$binary = if ($env:SENTINELOPS_CHROMA_WSL_BINARY) { $env:SENTINELOPS_CHROMA_WSL_BINARY } else { '$HOME/.local/bin/chroma' }
$chromaHost = if ($env:SENTINELOPS_CHROMA_HOST) { $env:SENTINELOPS_CHROMA_HOST } else { "127.0.0.1" }
$logDir = '$HOME/.sentinelops/logs'
$logFile = "$logDir/chroma.log"
$heartbeatUrl = "http://${chromaHost}:$port/api/v2/heartbeat"
$timeoutSeconds = if ($env:SENTINELOPS_CHROMA_START_TIMEOUT_SECONDS) { [int]$env:SENTINELOPS_CHROMA_START_TIMEOUT_SECONDS } else { 90 }

Write-Host "Starting Chroma in WSL distro '$distro' on port $port..."
Write-Host "Cold WSL startup can take up to $timeoutSeconds seconds on this machine."

try {
  Invoke-RestMethod $heartbeatUrl -TimeoutSec 2 | Out-Null
  Write-Host "Chroma is already responding on $heartbeatUrl"
  exit 0
} catch {
}

$probe = wsl.exe -d $distro -- bash -lc "test -x $binary"
if ($LASTEXITCODE -ne 0) {
  throw "Chroma binary was not found at $binary inside WSL distro '$distro'. Run scripts/setup_chroma_wsl.ps1 first."
}

$bashCommand = @"
mkdir -p $dataDir $logDir
setsid "$binary" run --path "$dataDir" --host 0.0.0.0 --port $port > "$logFile" 2>&1 < /dev/null &
sleep 3
"@

wsl.exe -d $distro -- bash -lc $bashCommand | Out-Null

$deadline = (Get-Date).AddSeconds($timeoutSeconds)
while ((Get-Date) -lt $deadline) {
  try {
    Invoke-RestMethod $heartbeatUrl -TimeoutSec 2 | Out-Null
    Write-Host "Chroma is responding on $heartbeatUrl"
    Write-Host "WSL log file: $logFile"
    exit 0
  } catch {
    Start-Sleep -Seconds 1
  }
}

$logTail = wsl.exe -d $distro -- bash -lc "tail -n 20 $logFile 2>/dev/null || true"
Write-Host "Chroma did not become ready within $timeoutSeconds seconds."
Write-Host "WSL log file: $logFile"
if ($logTail) {
  Write-Host "Recent Chroma log lines:"
  Write-Host $logTail
}
throw "Chroma is not reachable at $heartbeatUrl"
