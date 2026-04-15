@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul

if not exist frontend (
  echo [error] frontend directory not found.
  exit /b 1
)

if not exist .env (
  copy .env.example .env >nul
)

if not exist .venv\Scripts\python.exe (
  echo [.venv] Creating virtual environment...
  python -m venv .venv || exit /b 1
)

echo [web] Syncing frontend env from root .env...
.\.venv\Scripts\python.exe scripts\write_frontend_env.py || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_frontend_port.py') do set FRONTEND_PORT=%%i
if "%FRONTEND_PORT%"=="" set FRONTEND_PORT=3000

pushd frontend
if not exist node_modules (
  echo [npm] Installing frontend dependencies...
  npm install || exit /b 1
)

echo [web] Starting Next.js frontend on http://127.0.0.1:%FRONTEND_PORT% ...
npm run dev -- --hostname 127.0.0.1 --port %FRONTEND_PORT%
popd
