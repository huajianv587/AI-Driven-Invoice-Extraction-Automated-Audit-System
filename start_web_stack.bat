@echo off
setlocal EnableExtensions
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

set "MODE=%~1"
if "%MODE%"=="" set "MODE=local"
if /I not "%MODE%"=="local" if /I not "%MODE%"=="demo" (
  echo [error] Usage: start_web_stack.bat [local^|demo]
  exit /b 1
)

if not exist .env (
  echo [env] Creating .env from .env.example ...
  copy .env.example .env >nul
)

if not exist .venv\Scripts\python.exe (
  echo [.venv] Creating virtual environment...
  python -m venv .venv || exit /b 1
)

echo [pip] Installing Python dependencies...
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || exit /b 1

echo [env] Validating .env ...
.\.venv\Scripts\python.exe scripts\check_env.py || exit /b 1

echo [docker] Starting MySQL and Mailpit...
docker compose up -d mysql mailpit >nul 2>&1
if errorlevel 1 (
  if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    echo [docker] Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    .\.venv\Scripts\python.exe scripts\wait_for_docker.py || exit /b 1
    docker compose up -d mysql mailpit || exit /b 1
  ) else (
    echo [docker] Docker Desktop is not running and was not found at the default path.
    exit /b 1
  )
)
echo [docker] MySQL and Mailpit are ready.

echo [db] Applying schema...
.\.venv\Scripts\python.exe scripts\apply_schema.py || exit /b 1

if /I "%MODE%"=="demo" (
  echo [demo] Resetting invoice demo state...
  .\.venv\Scripts\python.exe scripts\reset_demo_state.py || exit /b 1
  echo [demo] Seeding deterministic Web UI demo data...
  .\.venv\Scripts\python.exe scripts\seed_web_demo_data.py || exit /b 1
) else (
  echo [local] Keeping existing invoice data.
)

echo [web] Writing frontend runtime env...
.\.venv\Scripts\python.exe scripts\write_frontend_env.py || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_api_port.py') do set "API_PORT=%%i"
if "%API_PORT%"=="" set "API_PORT=8009"
for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_frontend_port.py') do set "FRONTEND_PORT=%%i"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=3000"

.\.venv\Scripts\python.exe scripts\wait_for_ocr.py 3 >nul 2>&1
if errorlevel 1 (
  echo [ocr] Starting OCR service in a new window...
  start "Invoice Audit OCR" cmd /k ".\\.venv\\Scripts\\python.exe ocr_server.py"
) else (
  echo [ocr] OCR service is already running.
)

echo [ocr] Waiting for OCR health check...
.\.venv\Scripts\python.exe scripts\wait_for_ocr.py || exit /b 1

.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%API_PORT%/api/health 3 >nul 2>&1
if errorlevel 1 (
  echo [api] Starting FastAPI business API in a new window...
  start "Invoice Audit API" cmd /k ".\\start_api.bat"
) else (
  echo [api] FastAPI API is already running.
)

echo [api] Waiting for FastAPI health check...
.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%API_PORT%/api/health 120 || exit /b 1

.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%FRONTEND_PORT%/ 3 >nul 2>&1
if errorlevel 1 (
  echo [web] Starting Next.js frontend in a new window...
  start "Invoice Audit Frontend" cmd /k ".\\start_frontend.bat"
) else (
  echo [web] Next.js frontend is already running.
)

echo [web] Waiting for frontend health check...
.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%FRONTEND_PORT%/ 180 || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_feishu_retry_enabled.py') do set "FEISHU_RETRY_ENABLED=%%i"
if "%FEISHU_RETRY_ENABLED%"=="1" (
  echo [feishu] Starting Feishu retry worker in a new window...
  start "Invoice Audit Feishu Retry" cmd /k ".\\start_feishu_retry.bat"
) else (
  echo [feishu] Retry worker is disabled.
)

echo.
echo [ok] Invoice Audit Web stack is ready.
echo [ok] Home:      http://127.0.0.1:%FRONTEND_PORT%/
echo [ok] Workspace: http://127.0.0.1:%FRONTEND_PORT%/app/dashboard
echo [ok] API:       http://127.0.0.1:%API_PORT%/api/health
echo [ok] Mailpit:   http://127.0.0.1:8025
echo.

endlocal & set "API_PORT=%API_PORT%" & set "FRONTEND_PORT=%FRONTEND_PORT%" & exit /b 0
