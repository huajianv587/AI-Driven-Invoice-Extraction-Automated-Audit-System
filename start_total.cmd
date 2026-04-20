@echo off
setlocal EnableExtensions
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo ============================================
echo   Invoice Audit Terminal  --  Total Launcher
echo ============================================
echo.
echo [info] Lines starting with [wait] are normal readiness checks while Docker, OCR, API, and Next.js start.
echo [info] A real startup failure is printed with [error] and exits this window with a non-zero code.
echo.

echo [1/4] Starting the complete local Web stack without resetting invoice data...
call "%~dp0start_web_stack.bat" local
if errorlevel 1 (
  echo.
  echo [error] Web stack startup failed. Check the service windows and messages above.
  pause
  exit /b 1
)

echo.
echo [2/4] Reading runtime ports from .env...
for /f %%i in ('"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\get_frontend_port.py"') do set "FRONTEND_PORT=%%i"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=3000"
for /f %%i in ('"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\get_api_port.py"') do set "API_PORT=%%i"
if "%API_PORT%"=="" set "API_PORT=8009"

echo [3/4] Opening Web app and local mail inbox...
start "" "http://127.0.0.1:%FRONTEND_PORT%/"
start "" "http://127.0.0.1:%FRONTEND_PORT%/app/dashboard"
start "" "http://127.0.0.1:8025"

echo.
echo [4/4] Ready.
echo [ok] Home:      http://127.0.0.1:%FRONTEND_PORT%/
echo [ok] Workspace: http://127.0.0.1:%FRONTEND_PORT%/app/dashboard
echo [ok] API:       http://127.0.0.1:%API_PORT%/api/health
echo [ok] Mailpit:   http://127.0.0.1:8025
echo.
echo [tips] Sign in with AUTH_BOOTSTRAP_ADMIN_EMAIL / AUTH_BOOTSTRAP_ADMIN_PASSWORD from .env.
echo [tips] Keep the OCR, API, and Frontend windows open while using the app.
echo.

pause
