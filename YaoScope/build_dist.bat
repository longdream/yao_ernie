@echo off
chcp 65001 >nul
echo ====================================
echo   YaoScope 分发包构建工具
echo ====================================
echo.

REM 检查虚拟环境
if not exist "venv\" (
    echo [ERROR] 虚拟环境不存在
    echo [INFO] 请先运行 start.bat 创建虚拟环境
    pause
    exit /b 1
)

REM 激活虚拟环境
echo [INFO] 激活虚拟环境...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] 激活虚拟环境失败
    pause
    exit /b 1
)

REM 步骤1: 运行 Python 构建脚本
echo.
echo ====================================
echo   步骤 1/3: 构建 Python 环境
echo ====================================
echo.

python distribution\build.py
if errorlevel 1 (
    echo [ERROR] Python 环境构建失败
    pause
    exit /b 1
)

REM 步骤2: 编译 Rust 启动器
echo.
echo ====================================
echo   步骤 2/3: 编译 Rust 启动器
echo ====================================
echo.

cd launcher
echo [INFO] 编译 Release 版本...
cargo build --release
if errorlevel 1 (
    echo [ERROR] Rust 启动器编译失败
    cd ..
    pause
    exit /b 1
)
cd ..

REM 检查编译产物
if not exist "launcher\target\release\YaoScope.exe" (
    echo [ERROR] 找不到编译后的启动器
    pause
    exit /b 1
)

echo [OK] 启动器编译成功: launcher\target\release\YaoScope.exe

REM 步骤3: 复制启动器到分发目录
echo.
echo ====================================
echo   步骤 3/3: 整合分发包
echo ====================================
echo.

REM 复制到 Full 版本
if exist "dist\YaoScope-Full\" (
    echo [INFO] 复制启动器到 Full 版本...
    copy /Y "launcher\target\release\YaoScope.exe" "dist\YaoScope-Full\YaoScope.exe" >nul
    if errorlevel 1 (
        echo [ERROR] 复制失败
        pause
        exit /b 1
    )
    echo [OK] Full 版本: dist\YaoScope-Full\YaoScope.exe
)

REM 复制到 Lite 版本
if exist "dist\YaoScope-Lite\" (
    echo [INFO] 复制启动器到 Lite 版本...
    copy /Y "launcher\target\release\YaoScope.exe" "dist\YaoScope-Lite\YaoScope.exe" >nul
    if errorlevel 1 (
        echo [ERROR] 复制失败
        pause
        exit /b 1
    )
    echo [OK] Lite 版本: dist\YaoScope-Lite\YaoScope.exe
)

REM 显示构建结果
echo.
echo ====================================
echo   构建完成！
echo ====================================
echo.

REM 显示分发包信息
echo [INFO] 分发包信息:
echo.

if exist "dist\YaoScope-Full\" (
    echo Full 版本 (完整离线版^):
    echo   位置: dist\YaoScope-Full\
    echo   特点: 包含所有依赖，无需网络
    echo.
)

if exist "dist\YaoScope-Lite\" (
    echo Lite 版本 (在线精简版^):
    echo   位置: dist\YaoScope-Lite\
    echo   特点: 首次启动自动下载依赖
    echo.
)

echo ====================================
echo   下一步
echo ====================================
echo.
echo 1. 测试 Full 版本:
echo    cd dist\YaoScope-Full
echo    YaoScope.exe
echo.
echo 2. 测试 Lite 版本:
echo    cd dist\YaoScope-Lite
echo    YaoScope.exe
echo.
echo 3. 打包分发:
echo    将 dist\YaoScope-Full 或 dist\YaoScope-Lite 压缩为 zip
echo    分发给用户使用
echo.

pause

