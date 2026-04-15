@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo [local] Starting the Invoice Audit Web stack without resetting data...
call "%~dp0start_web_stack.bat" local
if errorlevel 1 (
  echo.
  echo [error] Local Web startup failed. Please check the output above.
  exit /b 1
)

echo.
echo [ok] Local Web stack is ready.
echo [ok] Home:      http://127.0.0.1:%FRONTEND_PORT%/
echo [ok] Workspace: http://127.0.0.1:%FRONTEND_PORT%/app/dashboard
echo [ok] Mailpit:   http://127.0.0.1:8025
