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

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_ui_port.py') do set UI_PORT=%%i
if "%UI_PORT%"=="" set UI_PORT=8517

echo [ui] Starting Streamlit dashboard on http://127.0.0.1:%UI_PORT% ...
.\.venv\Scripts\python.exe -m streamlit run src\ui\streamlit_app.py --server.port %UI_PORT%
