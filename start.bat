@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d %~dp0

REM Trace file for CI/tooling diagnostics (not for git)
if not exist ".cursor" mkdir ".cursor" >nul 2>&1
set "TRACE_FILE=.cursor\start_trace.log"
echo [%date% %time%] start.bat: begin>> "%TRACE_FILE%"

REM ============================================
REM Bootstrap dependencies (source-only friendly)
REM ============================================

REM 1) Python venv + deps (YaoScope)
if not exist "YaoScope\venv\Scripts\python.exe" (
    echo [%date% %time%] creating venv>> "%TRACE_FILE%"
    echo [Yao] Python venv not found. Creating: YaoScope\venv
    cd YaoScope
    python -m venv venv
    if errorlevel 1 (
        echo [%date% %time%] ERROR: venv create failed>> "%TRACE_FILE%"
        echo [Yao] Error: Failed to create Python venv
        cd ..
        exit /b 1
    )
    cd ..
)

if not exist "YaoScope\venv\.deps_installed" (
    echo [%date% %time%] installing python deps>> "%TRACE_FILE%"
    echo [Yao] Installing Python deps from YaoScope/requirements.txt...
    REM Ensure pip reads requirements in UTF-8 on Windows
    set "PYTHONUTF8=1"
    set "PYTHONIOENCODING=utf-8"
    YaoScope\venv\Scripts\pip.exe install -r YaoScope\requirements.txt
    if errorlevel 1 (
        echo [%date% %time%] ERROR: python deps install failed>> "%TRACE_FILE%"
        echo [Yao] Error: Python dependencies installation failed
        exit /b 1
    )
    echo. > YaoScope\venv\.deps_installed
    echo [Yao] Python dependencies installed successfully
)

REM 2) Node deps
if not exist "node_modules" (
    echo [%date% %time%] installing node deps>> "%TRACE_FILE%"
    echo [Yao] node_modules not found. Installing Node.js deps...
    npm ci
    if errorlevel 1 (
        echo [%date% %time%] ERROR: node deps install failed>> "%TRACE_FILE%"
        echo [Yao] Error: Node.js dependencies installation failed
        exit /b 1
    )
)

echo [Yao] Starting Tauri dev...
echo [%date% %time%] starting yaoscope>> "%TRACE_FILE%"
set "ROOT_DIR=%CD%"
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set NO_PROXY=*
set http_proxy=
set https_proxy=
set all_proxy=
set no_proxy=*

REM Start YaoScope Python HTTP service on port 8765
echo [Yao] Starting YaoScope HTTP service on port 8765...
REM Detach service process (do not share console); redirect logs for debugging
powershell -NoProfile -Command ^
  "Start-Process -WindowStyle Hidden -FilePath '%ROOT_DIR%\\YaoScope\\venv\\Scripts\\python.exe' -ArgumentList 'main.py' -WorkingDirectory '%ROOT_DIR%\\YaoScope\\service' -RedirectStandardOutput '%ROOT_DIR%\\YaoScope\\service_output.log' -RedirectStandardError '%ROOT_DIR%\\YaoScope\\service_stderr.log'" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: failed to spawn yaoscope>> "%TRACE_FILE%"
    echo [Yao] Error: Failed to start YaoScope process
    exit /b 1
)

echo [Yao] Waiting for YaoScope service to start...
set "HEALTH_OK=0"
for /l %%I in (1,1,30) do (
    curl -s http://127.0.0.1:8765/health >nul 2>&1
    if !errorlevel! equ 0 (
        set "HEALTH_OK=1"
        goto :health_done
    )
    timeout /t 1 /nobreak >nul
)
:health_done
if "%HEALTH_OK%"=="1" (
    echo [%date% %time%] yaoscope health ok>> "%TRACE_FILE%"
    echo [Yao] YaoScope HTTP service started successfully on port 8765
    echo === START SUCCESS ===
) else (
    echo [%date% %time%] ERROR: yaoscope health failed after retries>> "%TRACE_FILE%"
    echo [Yao] Error: YaoScope HTTP service failed to start. Check logs.
    exit /b 1
)

echo [Yao] Launching application...
echo [%date% %time%] launching tauri dev>> "%TRACE_FILE%"
REM Detach Tauri dev (do not share console) to avoid stdin redirection issues
powershell -NoProfile -Command ^
  "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','npx tauri dev' -WorkingDirectory '%ROOT_DIR%'" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: failed to start tauri dev>> "%TRACE_FILE%"
    echo [Yao] Error: Failed to start Tauri dev
    exit /b 1
)

echo [%date% %time%] start.bat: exit 0>> "%TRACE_FILE%"
exit /b 0