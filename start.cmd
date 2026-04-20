@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo [start] Launching the Invoice Audit local Web stack...
call "%~dp0start_total.cmd"
if errorlevel 1 (
  echo.
  echo [error] Startup failed. Please check the logs above.
  pause
  exit /b 1
)
exit /b 0
