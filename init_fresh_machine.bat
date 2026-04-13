@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

where python >nul 2>&1
if errorlevel 1 (
  echo [error] Python 3.10+ is required before running init_fresh_machine.bat
  exit /b 1
)

python scripts\init_fresh_machine.py %*
