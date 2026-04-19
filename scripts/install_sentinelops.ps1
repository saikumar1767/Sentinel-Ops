$ErrorActionPreference = "Stop"

$packageUrl = "https://github.com/saikumar1767/Sentinel-Ops/archive/refs/heads/main.zip"

function Get-UserBinCandidates {
  $paths = New-Object System.Collections.Generic.List[string]

  if ($HOME) {
    $paths.Add((Join-Path $HOME ".local\bin"))
  }

  if ($env:APPDATA) {
    $pythonRoot = Join-Path $env:APPDATA "Python"
    if (Test-Path $pythonRoot) {
      Get-ChildItem -Path $pythonRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $paths.Add((Join-Path $_.FullName "Scripts"))
      }
    }
  }

  return $paths | Select-Object -Unique
}

function Add-UserBinToPath {
  $pathEntries = $env:Path -split ';'
  foreach ($candidate in Get-UserBinCandidates) {
    if ((Test-Path $candidate) -and -not ($pathEntries -contains $candidate)) {
      $env:Path = "$candidate;$env:Path"
    }
  }
}

function Resolve-Uv {
  Add-UserBinToPath

  $command = Get-Command uv -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  foreach ($candidateDir in Get-UserBinCandidates) {
    $candidate = Join-Path $candidateDir "uv.exe"
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  return $null
}

function Ensure-Uv {
  $uv = Resolve-Uv
  if ($uv) {
    return $uv
  }

  try {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  } catch {
  }

  $uv = Resolve-Uv
  if ($uv) {
    return $uv
  }

  if (Get-Command py -ErrorAction SilentlyContinue) {
    py -m pip install --user uv
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m pip install --user uv
  } else {
    throw "Could not install uv automatically. Install Python 3.11+ or uv first, then rerun the installer."
  }

  $uv = Resolve-Uv
  if ($uv) {
    return $uv
  }

  throw "uv was installed but is still not available on PATH. Restart PowerShell and try again."
}

$uv = Ensure-Uv
& $uv tool install --force --from $packageUrl sentinel-ops
Add-UserBinToPath

Write-Host ""
Write-Host "SentinelOps installed."
Write-Host "Run: sentinelops"
