@echo off
chcp 65001 >nul
echo ========================================
echo       内网遥控器 - 启动脚本
echo ========================================
echo.

REM 优先使用uv
where uv >nul 2>&1
if not errorlevel 1 (
    echo [信息] 使用uv运行...
    echo.
    echo ========================================
    echo   请确保运行本程序的电脑和投影设备在同一局域网内
    echo   在手机浏览器访问以下地址:
    echo.

    REM 获取本机IP并显示
    python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(f'   http://{s.getsockname()[0]}:8080'); s.close()" 2>nul || echo   http://[您的电脑IP]:8080
    echo   http://localhost:8080 (本机)
    echo ========================================
    echo.
    echo 按 Ctrl+C 停止服务
    echo.

    uv run python server.py
    goto :end
)

REM 如果没有uv，使用普通Python
echo [提示] 未检测到uv，将使用普通Python
echo [提示] 推荐安装uv以获得更好的体验: https://github.com/astral-sh/uv
echo.

REM 检查Python是否安装 - 尝试多个可能的命令
set PYTHON_CMD=
python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
)
if not defined PYTHON_CMD (
    python3 --version >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=python3
    )
)
if not defined PYTHON_CMD (
    py --version >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=py
    )
)

if not defined PYTHON_CMD (
    echo [错误] 未找到Python，请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] 使用 %PYTHON_CMD%
echo [信息] 检查依赖...
%PYTHON_CMD% -c "import aiohttp, websockets" >nul 2>&1
if errorlevel 1 (
    echo [信息] 正在安装依赖...
    %PYTHON_CMD% -m pip install aiohttp websockets
)

echo.
echo ========================================
echo   请确保运行本程序的电脑和投影设备在同一局域网内
echo   在手机浏览器访问以下地址:
echo.
%PYTHON_CMD% -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(f'   http://{s.getsockname()[0]}:8080'); s.close()" 2>nul || echo   http://[您的电脑IP]:8080
echo   http://localhost:8080 (本机)
echo ========================================
echo.
echo 按 Ctrl+C 停止服务
echo.

%PYTHON_CMD% server.py

:end
pause
