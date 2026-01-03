@echo off
chcp 65001 >nul
echo ========================================
echo [测试] 验证发布包完整性
echo ========================================
echo.

set PUBLISH_DIR=publish\Yao-Release

if not exist "%PUBLISH_DIR%" (
    echo [错误] 发布目录不存在: %PUBLISH_DIR%
    echo 请先运行 publish_build.bat 或 publish_build.ps1
    pause
    exit /b 1
)

echo [检查] 验证文件完整性...
echo.

:: 检查主程序
if exist "%PUBLISH_DIR%\yao.exe" (
    echo ✓ yao.exe 存在
) else (
    echo ✗ yao.exe 不存在
)

:: 检查启动脚本
if exist "%PUBLISH_DIR%\start.bat" (
    echo ✓ start.bat 存在
) else (
    echo ✗ start.bat 不存在
)

if exist "%PUBLISH_DIR%\stop.bat" (
    echo ✓ stop.bat 存在
) else (
    echo ✗ stop.bat 不存在
)

:: 检查 Python 服务
if exist "%PUBLISH_DIR%\YaoScope\service" (
    echo ✓ YaoScope/service 存在
) else (
    echo ✗ YaoScope/service 不存在
)

if exist "%PUBLISH_DIR%\YaoScope\planscope" (
    echo ✓ YaoScope/planscope 存在
) else (
    echo ✗ YaoScope/planscope 不存在
)

if exist "%PUBLISH_DIR%\YaoScope\venv" (
    echo ✓ YaoScope/venv 存在
) else (
    echo ✗ YaoScope/venv 不存在
)

:: 检查 Python 可执行文件
if exist "%PUBLISH_DIR%\YaoScope\venv\Scripts\python.exe" (
    echo ✓ Python 虚拟环境可执行文件存在
) else (
    echo ✗ Python 虚拟环境可执行文件不存在
)

:: 检查配置文件
if exist "%PUBLISH_DIR%\config\settings.json.template" (
    echo ✓ 配置模板存在
) else (
    echo ✗ 配置模板不存在
)

:: 检查 README
if exist "%PUBLISH_DIR%\README.md" (
    echo ✓ README.md 存在
) else (
    echo ✗ README.md 不存在
)

echo.
echo [检查] 验证 Python 依赖...
echo.

cd "%PUBLISH_DIR%\YaoScope"
call venv\Scripts\activate.bat
python -c "import fastapi; import paddleocr; import langchain; print('✓ 核心依赖包已安装')" 2>nul
if errorlevel 1 (
    echo ✗ 部分依赖包未安装
) else (
    echo ✓ 所有核心依赖包已安装
)
call deactivate
cd ..\..

echo.
echo ========================================
echo [完成] 验证完成
echo ========================================
echo.

pause


