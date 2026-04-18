$ErrorActionPreference = "Stop"

$distro = if ($env:SENTINELOPS_CHROMA_WSL_DISTRO) { $env:SENTINELOPS_CHROMA_WSL_DISTRO } else { "Ubuntu" }
$version = "1.5.5"

Write-Host "Installing Chroma $version in WSL distro '$distro'..."

wsl.exe -d $distro -- bash -lc @"
set -euo pipefail
cd ~
if ! python3 -c "import pip" >/dev/null 2>&1; then
  curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
  python3 get-pip.py --user
fi
~/.local/bin/pip3 install --user chromadb==$version
"@

Write-Host "Chroma is installed in WSL."
