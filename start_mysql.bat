@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

if not exist .venv\Scripts\python.exe (
  echo [.venv] Creating virtual environment...
  python -m venv .venv || exit /b 1
)

echo [pip] Installing runtime dependencies...
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || exit /b 1

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

echo [db] Applying schema...
.\.venv\Scripts\python.exe scripts\apply_schema.py || exit /b 1

echo [ok] MySQL is ready.
echo [mailpit] Inbox UI: http://127.0.0.1:8025
