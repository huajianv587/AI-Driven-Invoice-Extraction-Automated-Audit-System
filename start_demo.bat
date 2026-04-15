@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo [demo] Starting the flagship Web demo stack...
call "%~dp0start_web_stack.bat" demo
if errorlevel 1 (
  echo.
  echo [error] Web demo startup failed. Please check the output above.
  exit /b 1
)

echo [demo] Opening Web app and Mailpit...
start "" "http://127.0.0.1:%FRONTEND_PORT%/"
start "" "http://127.0.0.1:%FRONTEND_PORT%/app/dashboard"
start "" "http://127.0.0.1:8025"

echo.
echo [ok] Demo data has been reset and seeded for the Web workspace.
echo [ok] Bootstrap admin: see AUTH_BOOTSTRAP_ADMIN_EMAIL / AUTH_BOOTSTRAP_ADMIN_PASSWORD in .env
echo [ok] Home:      http://127.0.0.1:%FRONTEND_PORT%/
echo [ok] Workspace: http://127.0.0.1:%FRONTEND_PORT%/app/dashboard
echo [ok] Mailpit:   http://127.0.0.1:8025
