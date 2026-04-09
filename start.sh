#!/bin/bash

echo "========================================"
echo "      内网遥控器 - 启动脚本"
echo "========================================"
echo ""

# 优先使用uv
if command -v uv &> /dev/null; then
    echo "[信息] 使用uv运行..."
    echo ""
    echo "========================================"
    echo "  请确保运行本程序的电脑和投影设备在同一局域网内"
    echo "  在手机浏览器访问以下地址:"
    echo ""

    # 获取本机IP
    local_ip=$(python3 -c "from server import _get_local_ip; print(_get_local_ip())" 2>/dev/null || echo "127.0.0.1")
    echo "   http://$local_ip:8080"
    echo "   http://localhost:8080 (本机)"
    echo "========================================"
    echo ""
    echo "按 Ctrl+C 停止服务"
    echo ""

    uv run python server.py
    exit 0
fi

# 如果没有uv，使用普通Python
echo "[提示] 未检测到uv，将使用普通Python"
echo "[提示] 推荐安装uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到Python3，请先安装Python 3.8+"
    exit 1
fi

# 检查依赖
if ! python3 -c "import aiohttp, websockets" 2>/dev/null; then
    echo "[信息] 正在安装依赖..."
    pip3 install aiohttp websockets
fi

echo ""
echo "========================================"
echo "  请确保运行本程序的电脑和投影设备在同一局域网内"
echo "  在手机浏览器访问以下地址:"
echo ""
local_ip=$(python3 -c "from server import _get_local_ip; print(_get_local_ip())" 2>/dev/null || echo "127.0.0.1")
echo "   http://$local_ip:8080"
echo "   http://localhost:8080 (本机)"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python3 server.py
