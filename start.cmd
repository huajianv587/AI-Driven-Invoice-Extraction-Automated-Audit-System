@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo [start] Launching the Invoice Audit flagship Web demo...
call "%~dp0start_demo.bat"
if errorlevel 1 (
  echo.
  echo [error] Demo startup failed. Please check the logs above.
  pause
  exit /b 1
)

echo.
echo [ok] Web demo environment is ready.
echo [ok] Home:      http://127.0.0.1:%FRONTEND_PORT%/
echo [ok] Workspace: http://127.0.0.1:%FRONTEND_PORT%/app/dashboard
echo [ok] Mailpit:   http://127.0.0.1:8025
echo.
echo [tips] Sign in with the bootstrap admin configured in .env.

pause
