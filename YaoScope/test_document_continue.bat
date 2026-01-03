@echo off
chcp 65001 > nul
echo ========================================
echo YaoScope 文档续写测试
echo ========================================
echo.

REM 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo [错误] 虚拟环境未找到
    echo 请先运行 install_dependencies.bat
    pause
    exit /b 1
)

echo [激活] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 验证关键依赖
echo [验证] 检查关键依赖...
python -c "import pywinauto; print('[OK] PyWinAuto')" 2>nul || (echo [ERROR] PyWinAuto未安装 & pause & exit /b 1)
python -c "import cv2; print('[OK] OpenCV')" 2>nul || (echo [ERROR] OpenCV未安装 & pause & exit /b 1)

REM 验证PaddleOCR及其依赖
echo [验证] 检查PaddleOCR...
python -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang='ch', device='cpu'); print('[OK] PaddleOCR完整')" 2>nul
if errorlevel 1 (
    echo [警告] PaddleOCR依赖不完整，正在修复...
    echo.
    echo [修复] 安装 paddlex[ocr-core]...
    python -m pip install --quiet "paddlex[ocr-core]" 2>nul
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        echo.
        echo 请手动运行: fix_paddleocr_deps.bat
        pause
        exit /b 1
    )
    echo [OK] 依赖修复成功
    echo.
)

REM 检查并启动服务
echo [检查] 正在检查YaoScope服务状态...
curl -s http://localhost:8765/health > nul 2>&1
if errorlevel 1 (
    echo [信息] YaoScope服务未运行，正在启动...
    echo.
    
    REM 停止可能存在的Python进程
    taskkill /F /IM python.exe 2>nul
    timeout /t 2 /nobreak > nul
    
    REM 启动服务（后台运行）
    cd service
    start /MIN "" ..\venv\Scripts\python.exe main.py
    cd ..
    
    echo [等待] 等待服务启动...
    timeout /t 8 /nobreak > nul
    
    REM 再次检查
    curl -s http://localhost:8765/health > nul 2>&1
    if errorlevel 1 (
        echo [错误] 服务启动失败
        echo 请手动启动服务：cd service ^&^& ..\venv\Scripts\python.exe main.py
        pause
        exit /b 1
    )
    echo [OK] 服务启动成功
) else (
    echo [OK] YaoScope服务正在运行
)
echo.

REM 提示准备应用
echo ========================================
echo 测试准备清单
echo ========================================
echo.
echo 请确保以下准备工作已完成:
echo.
echo   [1] 记事本已打开 'test_data\国庆作文.txt' 文件
echo       - 确认文件内容完整显示
echo       - 窗口处于活动状态
echo.
echo [提示] 本测试将使用OCR识别文档内容，然后生成续写
echo [提示] 鼠标坐标将用于裁剪编辑区域（排除标题栏和菜单栏）
echo.
echo 准备就绪后按任意键开始测试...
pause > nul

REM 执行测试
echo.
echo ========================================
echo 开始执行测试
echo ========================================
echo.

python test_document_continue.py

REM 保存退出码
set TEST_EXIT_CODE=%errorlevel%

REM 显示结果
echo.
echo ========================================
echo 测试完成
echo ========================================
echo.

if %TEST_EXIT_CODE% equ 0 (
    echo [SUCCESS] 文档续写测试通过！
    echo === START SUCCESS ===
) else if %TEST_EXIT_CODE% equ 1 (
    echo [WARNING] 文档续写测试失败，请查看上方日志
) else if %TEST_EXIT_CODE% equ 2 (
    echo [INFO] 测试被用户中断
) else (
    echo [ERROR] 测试执行异常，退出码: %TEST_EXIT_CODE%
)

echo.
echo 按任意键关闭窗口...
pause > nul

exit /b %TEST_EXIT_CODE%


