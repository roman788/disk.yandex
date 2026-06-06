@echo off
setlocal

cd /d "%~dp0"

echo Starting Local Yandex.Disk Uploader...
echo.

set "APP_URL=http://127.0.0.1:8765/"
set "APP_PORT=8765"

python --version >nul 2>&1
if errorlevel 1 (
  echo Python is not found. Install Python 3.12 or newer and try again.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Failed to install dependencies.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$conn = Get-NetTCPConnection -LocalPort %APP_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $conn) { exit 0 }; $pidValue = $conn.OwningProcess; $proc = Get-CimInstance Win32_Process -Filter \"ProcessId = $pidValue\"; if ($proc.CommandLine -like '*python* -m app.main*') { Stop-Process -Id $pidValue -Force; exit 0 }; Write-Host \"Port %APP_PORT% is busy by another process:\"; Write-Host $proc.CommandLine; exit 2"
if errorlevel 2 (
  echo.
  echo Cannot start: port %APP_PORT% is used by another application.
  pause
  exit /b 1
)

echo.
echo Opening %APP_URL%
echo Press Ctrl+C to stop the server.
echo.

powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%APP_URL%'" >nul 2>&1
python -m app.main

echo.
echo Application stopped.
pause
