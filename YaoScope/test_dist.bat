@echo off
chcp 65001 >nul
echo ====================================
echo   YaoScope 分发包测试工具
echo ====================================
echo.

REM 检查分发包是否存在
set FULL_DIR=dist\YaoScope-Full
set LITE_DIR=dist\YaoScope-Lite

if not exist "%FULL_DIR%\YaoScope.exe" (
    if not exist "%LITE_DIR%\YaoScope.exe" (
        echo [ERROR] 找不到分发包
        echo [INFO] 请先运行 build_dist.bat 构建分发包
        pause
        exit /b 1
    )
)

echo 请选择要测试的版本:
echo.
echo 1. Full 版本 (完整离线版)
echo 2. Lite 版本 (在线精简版)
echo 3. 退出
echo.
set /p choice="请输入选项 (1-3): "

if "%choice%"=="1" (
    if not exist "%FULL_DIR%\YaoScope.exe" (
        echo [ERROR] Full 版本不存在
        pause
        exit /b 1
    )
    echo.
    echo [INFO] 测试 Full 版本...
    echo [INFO] 目录: %FULL_DIR%
    echo.
    cd "%FULL_DIR%"
    YaoScope.exe
    cd ..\..
) else if "%choice%"=="2" (
    if not exist "%LITE_DIR%\YaoScope.exe" (
        echo [ERROR] Lite 版本不存在
        pause
        exit /b 1
    )
    echo.
    echo [INFO] 测试 Lite 版本...
    echo [INFO] 目录: %LITE_DIR%
    echo [WARNING] 首次运行会自动下载依赖（需要网络）
    echo.
    cd "%LITE_DIR%"
    YaoScope.exe
    cd ..\..
) else if "%choice%"=="3" (
    exit /b 0
) else (
    echo [ERROR] 无效的选项
    pause
    exit /b 1
)

echo.
echo [INFO] 测试完成
pause



