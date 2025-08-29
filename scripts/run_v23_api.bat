@echo off
setlocal
REM Run V2.3 API locally
cd /d "%~dp0\..\code"

if exist requirements.txt (
  echo Installing/updating Python dependencies...
  python -m pip install --upgrade pip >nul 2>&1
  python -m pip install -r requirements.txt
)

echo Starting V2.3 API server on http://localhost:8230/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8230 --reload
endlocal