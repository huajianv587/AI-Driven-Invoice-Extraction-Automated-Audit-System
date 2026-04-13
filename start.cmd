@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo [start] Launching invoice audit demo environment...
call "%~dp0start_demo.bat"
if errorlevel 1 (
  echo.
  echo [error] Demo startup failed. Please check the logs above.
  pause
  exit /b 1
)

set UI_PORT=8517
if exist .venv\Scripts\python.exe (
  for /f %%i in ('.\.venv\Scripts\python.exe scripts\get_ui_port.py') do set UI_PORT=%%i
)
if "%UI_PORT%"=="" set UI_PORT=8517

echo.
echo [ok] Demo environment is ready.
echo [ok] Dashboard: http://127.0.0.1:%UI_PORT%
echo [ok] Mailpit:   http://127.0.0.1:8025
echo.
echo [tips] Open the risk email in Mailpit and click the work-order link to complete the full demo loop.

pause
