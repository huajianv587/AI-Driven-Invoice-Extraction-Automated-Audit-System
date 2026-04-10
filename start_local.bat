@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

if not exist .env (
  copy .env.example .env >nul
)

if not exist .venv\Scripts\python.exe (
  echo [.venv] Creating virtual environment...
  python -m venv .venv || exit /b 1
)

echo [pip] Installing runtime dependencies...
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_ui_port.py') do set UI_PORT=%%i
if "%UI_PORT%"=="" set UI_PORT=8517

docker info >nul 2>&1
if errorlevel 1 (
  if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    echo [docker] Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    .\.venv\Scripts\python.exe scripts\wait_for_docker.py || exit /b 1
  ) else (
    echo [docker] Docker Desktop is not running and was not found at the default path.
    exit /b 1
  )
)

echo [docker] Starting MySQL and Mailpit...
docker compose up -d mysql mailpit || exit /b 1

echo [db] Applying product migrations...
.\.venv\Scripts\python.exe scripts\apply_schema.py || exit /b 1

.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:8000/docs 3 >nul 2>&1
if errorlevel 1 (
  echo [ocr] Starting OCR service in a new window...
  start "Invoice Audit OCR" cmd /k ".\\.venv\\Scripts\\python.exe ocr_server.py"
) else (
  echo [ocr] OCR service is already running.
)

.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:8080/healthz 3 >nul 2>&1
if errorlevel 1 (
  echo [api] Starting product API in a new window...
  start "Invoice Audit API" cmd /k ".\\.venv\\Scripts\\python.exe -m apps.api.main"
) else (
  echo [api] Product API is already running.
)

timeout /t 2 >nul
tasklist /v | findstr /i "Invoice Audit Worker" >nul 2>&1
if errorlevel 1 (
  echo [worker] Starting worker in a new window...
  start "Invoice Audit Worker" cmd /k ".\\.venv\\Scripts\\python.exe -m apps.worker.main"
) else (
  echo [worker] Worker window already exists.
)

.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%UI_PORT% 3 >nul 2>&1
if errorlevel 1 (
  echo [ui] Starting Streamlit UI in a new window...
  start "Invoice Audit UI" cmd /k ".\\.venv\\Scripts\\python.exe -m streamlit run apps\\ui\\streamlit_app.py --server.port %UI_PORT%"
) else (
  echo [ui] Streamlit UI is already running.
)

echo [ocr] Waiting for OCR health check...
.\.venv\Scripts\python.exe scripts\wait_for_ocr.py || exit /b 1

echo [api] Waiting for API health check...
.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:8080/healthz 120 || exit /b 1

echo [ui] Waiting for UI health check...
.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%UI_PORT% 120 || exit /b 1

echo [mailpit] Inbox UI: http://127.0.0.1:8025
echo [api] API docs: http://127.0.0.1:8080/docs
echo [ui] Dashboard: http://127.0.0.1:%UI_PORT%
