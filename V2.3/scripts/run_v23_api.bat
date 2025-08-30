@echo off
setlocal EnableDelayedExpansion
REM Run V2.3 API locally (Batch)

REM Project root and .env
set "PROJECT_ROOT=%~dp0.."
set "ENV_FILE=%PROJECT_ROOT%\.env"
if exist "%ENV_FILE%" (
  echo Loading environment from %ENV_FILE%
  for /f "usebackq delims=" %%L in ("%ENV_FILE%") do (
    set "line=%%L"
    if not "!line!"=="" (
      echo.!line! | findstr /b /r /c:"#" >nul && (
        REM skip comments
        goto :continue
      )
      for /f "tokens=1,* delims==" %%A in ("!line!") do (
        if not "%%~A"=="" (
          set "name=%%~A"
          set "value=%%~B"
          REM trim surrounding quotes
          if "!value:~0,1!"=="\"" set "value=!value:~1!"
          if "!value:~-1!"=="\"" set "value=!value:~0,-1!"
          if "!value:~0,1!"=="'" set "value=!value:~1!"
          if "!value:~-1!"=="'" set "value=!value:~0,-1!"
          setx !name! "!value!" >nul
          set "!name!=!value!"
        )
      )
    )
    :continue
  )
)

REM Determine port and defaults
if not defined API_PORT set "API_PORT=8230"
if not defined API_BASE_URL set "API_BASE_URL=http://127.0.0.1:%API_PORT%"

cd /d "%~dp0\..\code"

if exist requirements.txt (
  echo Installing/updating Python dependencies...
  python -m pip install --upgrade pip >nul 2>&1
  python -m pip install -r requirements.txt
)

echo Starting V2.3 API server on http://localhost:%API_PORT%/
python -m uvicorn app.main:app --host 0.0.0.0 --port %API_PORT% --reload
endlocal