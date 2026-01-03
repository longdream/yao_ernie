@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d %~dp0

echo ====================================
echo   Yao Package Script (No Build)
echo ====================================
echo.

REM Check tools
echo [Check] Checking required tools...
python --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python not installed
    pause
    exit /b 1
)
echo [Success] Tools check passed
echo.

REM 1. Create release directory
echo ====================================
echo [1/6] Creating release directory...
echo ====================================
echo [Info] If YaoScope is running, please stop it first
timeout /t 1 /nobreak >nul
if exist publish\Yao-Release (
    echo [Clean] Removing old release...
    rmdir /S /Q publish\Yao-Release 2>nul
)
if not exist publish\Yao-Release mkdir publish\Yao-Release
if not exist publish\Yao-Release\config mkdir publish\Yao-Release\config
if not exist publish\Yao-Release\data mkdir publish\Yao-Release\data
if not exist publish\Yao-Release\icons mkdir publish\Yao-Release\icons
if not exist publish\Yao-Release\models mkdir publish\Yao-Release\models
if not exist publish\Yao-Release\logs mkdir publish\Yao-Release\logs
echo [Success] Directory created
echo.

REM 2. Copy exe and static files
echo ====================================
echo [2/6] Copying main program...
echo ====================================
if not exist src-tauri\target\release\yao.exe (
    echo [Error] Release binary not found at: src-tauri\target\release\yao.exe
    echo [Info] Please run 'npm run tauri:build' first to generate the release binary.
    pause
    exit /b 1
)

echo [Copy] Copying yao.exe...
copy /Y src-tauri\target\release\yao.exe publish\Yao-Release\yao.exe >nul
if errorlevel 1 (
    echo [Error] Failed to copy exe
    pause
    exit /b 1
)

echo [Copy] Copying icons...
if exist src-tauri\icons xcopy /Y /I /Q src-tauri\icons\*.* publish\Yao-Release\icons\ >nul 2>&1

echo [Success] Main program copied
echo.

REM 3. Copy YaoScope service
echo ====================================
echo [3/6] Copying YaoScope service...
echo ====================================
echo [Copy] Copying service code...
xcopy /E /I /Y /Q YaoScope\service publish\Yao-Release\YaoScope\service >nul
xcopy /E /I /Y /Q YaoScope\planscope publish\Yao-Release\YaoScope\planscope >nul
copy /Y YaoScope\requirements.txt publish\Yao-Release\YaoScope\ >nul
echo [Success] YaoScope service copied
echo.

REM 4. Create Python venv
echo ====================================
echo [4/6] Creating Python venv...
echo ====================================
if not exist YaoScope\venv\Scripts\python.exe (
    echo [Error] Project venv not found at: YaoScope\venv\Scripts\python.exe
    echo [Info] Please run start.bat first to create project venv
    pause
    exit /b 1
)

cd publish\Yao-Release\YaoScope
echo [Create] Creating venv for release using project Python...
..\..\..\YaoScope\venv\Scripts\python.exe -m venv venv
if errorlevel 1 (
    echo [Error] Failed to create venv
    cd ..\..\..
    pause
    exit /b 1
)

echo [Install] Installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo [Error] Failed to install dependencies
    cd ..\..\..
    pause
    exit /b 1
)

echo [Fix] Ensuring anyio is correctly installed...
venv\Scripts\pip.exe install --ignore-installed --no-deps anyio==4.11.0 >nul 2>&1
cd ..\..\..
echo [Success] Python environment ready
echo.

REM 5. Clean temporary files
echo ====================================
echo [5/6] Cleaning temporary files...
echo ====================================
cd publish\Yao-Release\YaoScope\service
if exist __pycache__ rmdir /S /Q __pycache__ 2>nul
if exist api\__pycache__ rmdir /S /Q api\__pycache__ 2>nul
if exist core\__pycache__ rmdir /S /Q core\__pycache__ 2>nul
if exist tools\__pycache__ rmdir /S /Q tools\__pycache__ 2>nul
if exist data\screenshots rmdir /S /Q data\screenshots 2>nul
if exist runs rmdir /S /Q runs 2>nul
if exist logs\*.log del /Q logs\*.log 2>nul
cd ..\..\..\..
echo [Success] Temporary files cleaned
echo.

REM 6. Create config and scripts
echo ====================================
echo [6/6] Creating config and scripts...
echo ====================================
(
echo {
echo   "provider": "openai",
echo   "baseUrl": "https://api.openai.com/v1",
echo   "apiKey": "",
echo   "model": "gpt-4",
echo   "models": [],
echo   "vlModel": "",
echo   "lightModel": "",
echo   "advancedModel": "",
echo   "streamingEnabled": true,
echo   "defaultThink": false,
echo   "maxContextMessages": 20,
echo   "temperature": 0.7,
echo   "language": "zh-CN",
echo   "mcpServers": [],
echo   "mcpServerInfos": {},
echo   "mcpMaxRetries": 3,
echo   "mcpReflectionEnabled": false,
echo   "embeddingModelPath": "models/bge-m3-Q4_K_M.gguf",
echo   "pythonVenvPath": "YaoScope/venv"
echo }
) > publish\Yao-Release\config\settings.json

copy /Y publish\start_template.bat publish\Yao-Release\start.bat >nul
copy /Y publish\stop_template.bat publish\Yao-Release\stop.bat >nul
echo Please place Embedding model files here > publish\Yao-Release\models\README.txt
echo Application log files will be saved here > publish\Yao-Release\logs\README.txt

echo ====================================
echo   Packaging Complete!
echo ====================================
echo.
echo Location: publish\Yao-Release\
pause
