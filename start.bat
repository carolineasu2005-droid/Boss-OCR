@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到 Python 虚拟环境。
    echo 请先运行 setup.bat 安装依赖。
    pause
    exit /b 1
)

echo ========================================
echo  BOSS 直聘自动刷简历
echo ========================================
echo.
echo 1. 打开 Edge，进入 BOSS 直聘"推荐牛人"页面
echo 2. 将鼠标移到第一位候选人卡片上
echo 3. 本窗口倒计时 3 秒后将自动开始
echo.
echo 按 ESC 键停止，空格键暂停/继续
echo ========================================
echo.

"venv\Scripts\python.exe" "simple_brush.py"

if errorlevel 1 (
    echo.
    echo [错误] 脚本异常退出，错误码: %errorlevel%
    pause
)

endlocal
