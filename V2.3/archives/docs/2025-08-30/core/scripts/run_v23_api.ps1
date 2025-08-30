# Run V2.3 API locally (PowerShell)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve project root and load .env if present
$ProjectRoot = (Resolve-Path "$PSScriptRoot/..")
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
  Write-Host "Loading environment from $EnvFile"
  Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not [string]::IsNullOrWhiteSpace($line) -and -not $line.StartsWith('#')) {
      $kv = $line -split '=', 2
      if ($kv.Length -ge 2) {
        $name = $kv[0].Trim()
        $value = $kv[1].Trim().Trim('"').Trim("'")
        if ($name) { Set-Item -Path Env:$name -Value $value }
      }
    }
  }
}

# Determine port and defaults
$port = if ($env:API_PORT) { [int]$env:API_PORT } else { 8230 }
if (-not $env:API_BASE_URL) { $env:API_BASE_URL = "http://127.0.0.1:$port" }

# Move to code directory and install deps
Set-Location "$PSScriptRoot/../code"

if (Test-Path './requirements.txt') {
  Write-Host 'Installing/updating Python dependencies...'
  python -m pip install --upgrade pip | Out-Null
  python -m pip install -r requirements.txt
}

Write-Host "Starting V2.3 API server on http://localhost:$port/"
python -m uvicorn app.main:app --host 0.0.0.0 --port $port --reload