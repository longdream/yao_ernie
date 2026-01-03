@echo off
echo Stopping processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM yao.exe 2>nul
timeout /t 2 /nobreak >nul


