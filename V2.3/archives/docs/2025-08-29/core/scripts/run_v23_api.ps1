# Run V2.3 API locally (PowerShell)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location "$PSScriptRoot/../code"

if (Test-Path './requirements.txt') {
  Write-Host 'Installing/updating Python dependencies...'
  python -m pip install --upgrade pip | Out-Null
  python -m pip install -r requirements.txt
}

Write-Host 'Starting V2.3 API server on http://localhost:8230/'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8230 --reload