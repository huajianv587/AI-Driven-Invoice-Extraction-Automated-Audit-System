@echo off
cd /d %~dp0

echo ===== NGROK DIAG =====
where ngrok
echo ----------------------

ngrok version
echo ----------------------

ngrok http 8000
pause
