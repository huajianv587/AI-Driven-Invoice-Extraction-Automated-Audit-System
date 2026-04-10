@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

call "%~dp0start_local.bat"
if errorlevel 1 exit /b 1

echo [demo] Running product end-to-end test...
.\.venv\Scripts\python.exe scripts\product_e2e_test.py || exit /b 1

for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_ui_port.py') do set UI_PORT=%%i
if "%UI_PORT%"=="" set UI_PORT=8517

echo [demo] Dashboard: http://127.0.0.1:%UI_PORT%
echo [demo] Mailpit Inbox: http://127.0.0.1:8025
echo [demo] API docs: http://127.0.0.1:8080/docs
