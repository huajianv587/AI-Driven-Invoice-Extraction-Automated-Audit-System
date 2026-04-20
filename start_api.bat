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

echo [pip] Installing Python dependencies...
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || exit /b 1

echo [env] Validating .env ...
.\.venv\Scripts\python.exe scripts\check_env.py || exit /b 1

echo [db] Applying schema...
.\.venv\Scripts\python.exe scripts\apply_schema.py || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_api_port.py') do set API_PORT=%%i
if "%API_PORT%"=="" set API_PORT=8009

echo [api] Starting FastAPI business API on http://127.0.0.1:%API_PORT% ...
.\.venv\Scripts\python.exe api_server.py
