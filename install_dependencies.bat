@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

echo ========================================
echo [Yao] Installing Dependencies
echo ========================================

REM Check and create Python virtual environment
echo [Yao] Checking Python environment...
if not exist "YaoScope\venv" (
    echo [Yao] Python virtual environment not found, creating...
    cd YaoScope
    python -m venv venv
    if errorlevel 1 (
        echo [Yao] Error: Failed to create Python virtual environment
        cd ..
        pause
        exit /b 1
    )
    cd ..
    echo [Yao] Python virtual environment created successfully
) else (
    echo [Yao] Python virtual environment already exists
)

REM Install Python dependencies
echo [Yao] Installing Python dependencies...
cd YaoScope
venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [Yao] Error: Python dependencies installation failed
    cd ..
    pause
    exit /b 1
)
echo. > venv\.deps_installed
cd ..
echo [Yao] Python dependencies installed successfully

REM Install Node.js dependencies
echo [Yao] Installing Node.js dependencies...
call npm install --no-audit --no-fund --legacy-peer-deps
if errorlevel 1 (
    echo [Yao] Error: Failed to install Node.js dependencies
    pause
    exit /b 1
)

echo ========================================
echo [Yao] All dependencies installed successfully!
echo ========================================
pause
endlocal

