@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo ========================================
echo  BOSS 直聘自动刷简历 - 环境初始化
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.10 或更高版本，
    echo       并勾选"Add Python to PATH"。
    echo       下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Python 已找到:
python --version
echo.

if exist "venv" (
    echo [2/3] 虚拟环境已存在，跳过创建
) else (
    echo [2/3] 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo       虚拟环境创建完成
)
echo.

echo [3/3] 安装依赖包...
"venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)
echo       依赖安装完成
echo.

echo ========================================
echo  初始化完成！现在可以运行 start.bat
echo ========================================
pause

endlocal
