@echo off
chcp 65001 >nul
echo ====================================
echo   YaoScope Service - 打包为EXE
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

REM 检查PyInstaller是否安装
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller未安装，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller安装失败
        pause
        exit /b 1
    )
)

REM 清理之前的构建
echo [INFO] 清理之前的构建...
if exist "dist\" rmdir /s /q dist
if exist "build\" rmdir /s /q build

REM 开始打包
echo.
echo ====================================
echo   开始打包...
echo ====================================
echo.
echo [INFO] 这可能需要5-10分钟，请耐心等待...
echo.

pyinstaller build_exe.spec

if errorlevel 1 (
    echo.
    echo [ERROR] 打包失败
    pause
    exit /b 1
)

echo.
echo ====================================
echo   打包成功！
echo ====================================
echo.
echo [INFO] 可执行文件位置: dist\YaoScope\YaoScope.exe
echo.
echo [INFO] 使用说明:
echo   1. 将整个 dist\YaoScope 文件夹复制到目标机器
echo   2. 确保 models 文件夹在同一目录（如果需要）
echo   3. 直接运行 YaoScope.exe
echo.
echo [INFO] 预计大小: 500MB-1GB
echo.

REM 创建运行说明
echo 创建运行说明文件...
(
echo YaoScope Service - 独立可执行版本
echo =====================================
echo.
echo 使用方法:
echo 1. 双击 YaoScope.exe 启动服务
echo 2. 服务默认运行在 http://127.0.0.1:8765
echo 3. 查看控制台输出确认服务状态
echo.
echo 注意事项:
echo - 首次启动可能需要10-30秒解压
echo - 确保端口8765未被占用
echo - 如需使用OCR功能，确保models文件夹存在
echo.
echo 目录结构:
echo YaoScope/
echo   YaoScope.exe        - 主程序
echo   _internal/          - 依赖库（自动生成）
echo   models/             - 模型文件（需手动复制）
echo   data/               - 数据目录（自动创建）
echo.
echo 故障排除:
echo - 如果启动失败，检查是否有杀毒软件拦截
echo - 确保有足够的磁盘空间（至少2GB）
echo - 查看控制台错误信息
echo.
) > dist\YaoScope\README.txt

echo [OK] 运行说明已创建: dist\YaoScope\README.txt
echo.
pause


