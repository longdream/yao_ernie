@echo off
chcp 65001 >nul
echo ====================================
echo   YaoScope Service Startup
echo ====================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python未安装或未添加到PATH
    echo [INFO] 请先安装Python 3.9或更高版本
    pause
    exit /b 1
)

echo [INFO] Python版本:
python --version
echo.

REM 检查虚拟环境
if not exist "venv\" (
    echo [INFO] 虚拟环境不存在，正在创建...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建成功
)

REM 激活虚拟环境
echo [INFO] 激活虚拟环境...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] 激活虚拟环境失败
    pause
    exit /b 1
)

REM 检查依赖
echo [INFO] 检查依赖...
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] 依赖未安装！
    echo.
    echo 请先运行以下命令安装依赖:
    echo   install_dependencies.bat
    echo.
    echo 或者快速安装:
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo [OK] 依赖检查通过

REM 启动服务
echo.
echo ====================================
echo   Starting YaoScope Service...
echo ====================================
echo.

REM 设置Python路径（添加项目根目录）
set PYTHONPATH=%CD%;%PYTHONPATH%

REM 进入service目录并启动
cd service
python main.py

if errorlevel 1 (
    echo.
    echo [ERROR] 服务启动失败
    pause
    exit /b 1
)

echo.
echo [INFO] 服务已停止
pause

