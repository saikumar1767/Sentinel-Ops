$ErrorActionPreference = "Stop"

$distro = if ($env:SENTINELOPS_CHROMA_WSL_DISTRO) { $env:SENTINELOPS_CHROMA_WSL_DISTRO } else { "Ubuntu" }
$port = if ($env:SENTINELOPS_CHROMA_PORT) { $env:SENTINELOPS_CHROMA_PORT } else { "8012" }

Write-Host "Stopping Chroma in WSL distro '$distro' on port $port..."
wsl.exe -d $distro -- bash -lc "pkill -f 'chroma run .* --port $port' || true"
Write-Host "Stop signal sent."
