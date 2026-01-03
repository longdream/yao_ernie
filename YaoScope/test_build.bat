@echo off
chcp 65001 >nul
echo ====================================
echo   测试打包后的YaoScope程序
echo ====================================
echo.

REM 检查打包是否完成
if not exist "dist\YaoScope\YaoScope.exe" (
    echo [ERROR] 找不到打包后的程序
    echo [INFO] 请先运行 build_exe.bat 进行打包
    pause
    exit /b 1
)

echo [INFO] 找到可执行文件: dist\YaoScope\YaoScope.exe
echo.

REM 显示文件大小
echo [INFO] 检查文件大小...
dir dist\YaoScope\YaoScope.exe | findstr "YaoScope.exe"
echo.

REM 显示目录结构
echo [INFO] 目录结构:
dir /b dist\YaoScope
echo.

REM 询问是否启动测试
echo [WARNING] 即将启动打包后的程序进行测试
echo [INFO] 程序将在新的控制台窗口中运行
echo [INFO] 服务地址: http://127.0.0.1:8765
echo.
echo 按任意键启动测试，或关闭窗口取消...
pause >nul

REM 启动程序
echo.
echo [INFO] 启动中...
start "YaoScope Test" cmd /k "cd /d %~dp0dist\YaoScope && YaoScope.exe"

REM 等待服务启动
echo [INFO] 等待服务启动（10秒）...
timeout /t 10 /nobreak >nul

REM 测试服务是否响应
echo [INFO] 测试服务连接...
curl -s http://127.0.0.1:8765/docs >nul 2>&1
if errorlevel 1 (
    echo [WARNING] 无法连接到服务，请检查服务窗口的输出
    echo [INFO] 如果服务正常启动，可以手动访问: http://127.0.0.1:8765/docs
) else (
    echo [OK] 服务响应正常！
    echo [INFO] 打开浏览器访问: http://127.0.0.1:8765/docs
    start http://127.0.0.1:8765/docs
)

echo.
echo ====================================
echo   测试说明
echo ====================================
echo.
echo 1. 检查服务窗口是否有错误信息
echo 2. 访问 http://127.0.0.1:8765/docs 查看API文档
echo 3. 尝试调用几个API接口测试功能
echo 4. 测试完成后关闭服务窗口
echo.
echo 如果测试成功，说明打包正常，可以分发使用！
echo.
pause


