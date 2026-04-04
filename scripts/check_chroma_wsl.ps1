$ErrorActionPreference = "Stop"

$chromaHost = if ($env:SENTINELOPS_CHROMA_HOST) { $env:SENTINELOPS_CHROMA_HOST } else { "127.0.0.1" }
$port = if ($env:SENTINELOPS_CHROMA_PORT) { $env:SENTINELOPS_CHROMA_PORT } else { "8012" }
$url = "http://${chromaHost}:$port/api/v2/heartbeat"

Write-Host "Checking Chroma heartbeat at $url..."
$response = Invoke-RestMethod $url -TimeoutSec 2
$response | ConvertTo-Json -Depth 5
