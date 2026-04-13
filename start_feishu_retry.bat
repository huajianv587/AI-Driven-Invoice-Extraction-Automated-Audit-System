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

echo [env] Validating .env ...
.\.venv\Scripts\python.exe scripts\check_env.py || exit /b 1

echo [feishu] Starting retry worker...
.\.venv\Scripts\python.exe scripts\run_feishu_retry_daemon.py
