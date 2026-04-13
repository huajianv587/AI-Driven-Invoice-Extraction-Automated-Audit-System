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

echo [env] Validating .env ...
.\.venv\Scripts\python.exe scripts\check_env.py || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_ui_port.py') do set UI_PORT=%%i
if "%UI_PORT%"=="" set UI_PORT=8517

echo [docker] Starting MySQL and Mailpit...
docker compose up -d mysql mailpit >nul 2>&1
if errorlevel 1 (
  if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    echo [docker] Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    .\.venv\Scripts\python.exe scripts\wait_for_docker.py || exit /b 1
    echo [docker] Starting MySQL and Mailpit...
    docker compose up -d mysql mailpit || exit /b 1
  ) else (
    echo [docker] Docker Desktop is not running and was not found at the default path.
    exit /b 1
  )
)
echo [docker] MySQL and Mailpit are ready.

echo [db] Applying schema...
.\.venv\Scripts\python.exe scripts\apply_schema.py || exit /b 1

echo [demo] Resetting previous demo data...
.\.venv\Scripts\python.exe scripts\reset_demo_state.py || exit /b 1

.\.venv\Scripts\python.exe scripts\wait_for_ocr.py 3 >nul 2>&1
if errorlevel 1 (
  echo [ocr] Starting OCR service in a new window...
  start "Invoice Audit OCR" cmd /k ".\\.venv\\Scripts\\python.exe ocr_server.py"
  .\.venv\Scripts\python.exe scripts\wait_for_ocr.py || exit /b 1
) else (
  echo [ocr] OCR service is already running.
)

.\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%UI_PORT%/?view=dashboard 3 >nul 2>&1
if errorlevel 1 (
  echo [ui] Starting Streamlit dashboard in a new window...
  start "Invoice Audit UI" cmd /k ".\\.venv\\Scripts\\python.exe -m streamlit run src\\ui\\streamlit_app.py --server.port %UI_PORT%"
  .\.venv\Scripts\python.exe scripts\wait_for_http.py http://127.0.0.1:%UI_PORT%/?view=dashboard 120 || exit /b 1
) else (
  echo [ui] Streamlit dashboard is already running.
)

echo [ui] Opening dashboard and Mailpit...
start "" "http://127.0.0.1:%UI_PORT%/?view=dashboard"
start "" "http://127.0.0.1:8025"

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_feishu_retry_enabled.py') do set FEISHU_RETRY_ENABLED=%%i
if "%FEISHU_RETRY_ENABLED%"=="1" (
  echo [feishu] Starting Feishu retry worker in a new window...
  start "Invoice Audit Feishu Retry" cmd /k ".\\start_feishu_retry.bat"
) else (
  echo [feishu] Retry worker is disabled.
)

echo [demo] Running single-invoice demo ingestion...
.\.venv\Scripts\python.exe scripts\run_demo_ingest.py invoice.jpg || exit /b 1

echo [demo] Dashboard: http://127.0.0.1:%UI_PORT%
echo [demo] Mailpit Inbox: http://127.0.0.1:8025
echo [demo] Open the email and click the work-order link to finish the manual review.
