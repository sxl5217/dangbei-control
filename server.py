#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内网遥控器 - Python后端服务
支持在Windows上运行
"""

import asyncio
import datetime
import ipaddress
import json
import logging
import socket
import subprocess
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Optional

try:
    from aiohttp import web
    import websockets
except ImportError:
    print("正在安装依赖...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "aiohttp", "websockets"]
    )
    from aiohttp import web
    import websockets

# 当贝设备默认端口
DANGBEI_CONTROL_PORT = 6689

# 配置文件路径（项目相对路径）
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / ".data"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 配置日志（生产级：自动轮转，最大5MB，保留3份）
# 确保日志目录存在
LOG_DIR = BASE_DIR / ".logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("dangbei-control")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# 控制台输出（INFO级别及以上）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

# 文件输出（DEBUG级别及以上）
file_handler = RotatingFileHandler(
    filename=LOG_DIR / "control.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 音量配置
VOLUME_MIN = 0
VOLUME_MAX = 15  # 共16格 (0-15)
VOLUME_DEFAULT = 2

# 设备状态
STATE_ONLINE = "online"
STATE_OFFLINE = "offline"
STATE_SCANNING = "scanning"


# 组合命令定义
AGENT_COMMANDS: Dict[str, str | list] = {
    "power": "lerad_power",
    "home": "lerad_home",
    "back": "lerad_back",
    "menu": "lerad_menu",
    "ok": "lerad_ok",
    "up": "lerad_up",
    "down": "lerad_down",
    "left": "lerad_left",
    "right": "lerad_right",
    "sidebar": "lerad_side_key",
    "volumeup": 'lerad_volumn_add#&&#{"relative":"+"}',
    "volumedown": 'lerad_volumn_add#&&#{"relative":"-"}',
    "find": "lerad_find_controller",
    "reboot": ["power", "right", "ok"],
    "shutdown": ["power", "ok"],
}


@dataclass
class Device:
    id: str
    name: str
    ip: str
    port: int = DANGBEI_CONTROL_PORT


class ConfigManager:
    """配置管理器"""

    def __init__(self, executor=None):
        self.config: dict = {}
        self._executor = executor
        self._save_lock = asyncio.Lock()
        self._load()

    def _load(self):
        """加载配置（同步，启动时只调用一次）"""
        CONFIG_DIR.mkdir(exist_ok=True)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def _save_sync(self, config_copy):
        """同步保存配置（内部使用）"""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_copy, f, ensure_ascii=False, indent=2)

    async def _save(self):
        """异步保存配置：使用线程池避免阻塞事件循环"""
        async with self._save_lock:
            if self._executor:
                loop = asyncio.get_running_loop()
                # 传一份拷贝给子线程，实现读写隔离
                config_copy = self.config.copy()
                await loop.run_in_executor(self._executor, self._save_sync, config_copy)
            else:
                self._save_sync(self.config)

    def get_device(self) -> Optional[dict]:
        """获取配置的设备"""
        return self.config.get("last_device")

    async def set_device(self, device: Device):
        """保存设备"""
        self.config["last_device"] = {
            "id": device.id,
            "name": device.name,
            "ip": device.ip,
            "port": device.port,
        }
        await self._save()

    def get_volume(self) -> int:
        """获取音量，默认2格"""
        return self.config.get("volume", VOLUME_DEFAULT)

    async def set_volume(self, volume: int):
        """保存音量"""
        self.config["volume"] = max(VOLUME_MIN, min(VOLUME_MAX, volume))
        await self._save()

    def get_device_state(self) -> str:
        """获取设备状态"""
        return self.config.get("device_state", STATE_OFFLINE)

    async def set_device_state(self, state: str):
        """保存设备状态"""
        self.config["device_state"] = state
        await self._save()

    def get_scan_network(self) -> Optional[str]:
        """获取自定义扫描网段（如 "192.168.1.0/24"）"""
        return self.config.get("scan_network")

    def get_last_reboot_date(self) -> str:
        """获取最后一次重启执行日期"""
        return self.config.get("last_reboot_date", "")

    async def set_last_reboot_date(self, date_str: str):
        """保存最后一次重启执行日期"""
        self.config["last_reboot_date"] = date_str
        await self._save()


async def _check_port(ip: str, port: int, timeout: float = 0.2) -> Optional[str]:
    """检查端口是否开放"""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return ip
    except Exception:
        return None


def _get_local_ip() -> str:
    """获取本机局域网 IP（不联网方式）"""
    try:
        # 方法1：枚举所有网络接口

        # 获取所有网卡接口
        interfaces = []
        try:
            import netifaces
            # 如果有 netifaces 库，优先使用
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info['addr']
                        if not ip.startswith('127.') and not ip.startswith('169.254.'):
                            interfaces.append(ip)
        except ImportError:
            # 没有 netifaces，使用 socket 自带方法
            hostname = socket.gethostname()
            try:
                # 尝试通过 hostname 获取
                addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
                for addr in addrs:
                    ip = addr[4][0]
                    if not ip.startswith('127.') and not ip.startswith('169.254.'):
                        interfaces.append(ip)
            except Exception:
                pass

        # 移除重复
        interfaces = list(set(interfaces))

        # 优先选择常见的局域网网段
        priority = []
        for ip in interfaces:
            if ip.startswith('192.168.'):
                priority.insert(0, ip)  # 192.168.x.x 优先级最高
            elif ip.startswith('10.'):
                priority.append(ip)
            elif ip.startswith('172.'):
                # 172.16-31.x.x 是私有网段
                try:
                    second_octet = int(ip.split('.')[1])
                    if 16 <= second_octet <= 31:
                        priority.append(ip)
                except (IndexError, ValueError):
                    pass

        if priority:
            return priority[0]
        if interfaces:
            return interfaces[0]

        # 都失败了，返回默认值
        return "192.168.1.1"
    except Exception:
        return "192.168.1.1"


async def discover_projector(custom_network: Optional[str] = None) -> Optional[Device]:
    """扫描局域网发现设备"""
    logger.info("开始局域网扫描...")
    logger.debug(f"自定义网段: {custom_network}")

    if custom_network:
        network_str = custom_network
    else:
        # 默认使用本机 IP 所在的 /24 网段
        local_ip = _get_local_ip()
        logger.debug(f"本机IP: {local_ip}")
        # strict=False 允许输入主机IP，自动转换为网段地址
        network_str = f"{local_ip}/24"

    try:
        # 生成网段对象
        network = ipaddress.IPv4Network(network_str, strict=False)
    except ValueError as e:
        logger.error(f"无效的网段配置 {network_str}: {e}")
        return None

    # network.hosts() 自动生成网段内所有可用主机IP（排除网络地址和广播地址）
    hosts = list(network.hosts())
    logger.info(f"准备扫描网段: {network_str}，共包含 {len(hosts)} 个 IP")

    # 限制最大扫描范围，避免资源消耗过大
    if len(hosts) > 2048:
        logger.warning(
            f"扫描范围过大 ({len(hosts)} 个 IP)，为保护网络资源，将截断仅扫描前 2048 个 IP"
        )
        hosts = hosts[:2048]

    # 限制最大并发数
    sem = asyncio.Semaphore(254)
    logger.debug("开始并发扫描...")

    async def _bounded_check(ip_obj):
        async with sem:
            return await _check_port(str(ip_obj), DANGBEI_CONTROL_PORT)

    # 批量生成任务并等待
    tasks = [_bounded_check(ip) for ip in hosts]
    results = await asyncio.gather(*tasks)

    valid_ips = [ip for ip in results if ip]
    logger.debug(f"扫描完成，发现 {len(valid_ips)} 个可用设备")

    if valid_ips:
        discovered = valid_ips[0]
        logger.info(f"扫描到设备: {discovered}")
        return Device(
            id=f'device_{discovered.replace(".", "_")}',
            name=f'当贝设备 ({discovered.split(".")[-1]})',
            ip=discovered,
        )
    logger.debug("未扫描到设备")
    return None




class ControlServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        from concurrent.futures import ThreadPoolExecutor

        self._executor = ThreadPoolExecutor(max_workers=2)
        self.config_manager = ConfigManager(executor=self._executor)
        self.device_ip: Optional[str] = None
        self._is_scanning = False
        self._scan_lock = asyncio.Lock()
        self._cached_connected: bool = False
        self._device_monitor_task_obj: Optional[asyncio.Task] = None
        self._daily_restart_task_obj: Optional[asyncio.Task] = None
        self._ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_lock = asyncio.Lock()
        self._ws_send_lock = asyncio.Lock()
        self.app = self._create_app()

    def _create_app(self):
        app = web.Application()
        app.add_routes(
            [
                web.get("/", self.index),
                web.post("/api/key", self.handle_key),
                web.get("/api/status", self.handle_status),
                web.post("/api/scan", self.handle_scan),
            ]
        )
        app.router.add_static("/css/", path=str(BASE_DIR / "css"))
        app.router.add_static("/js/", path=str(BASE_DIR / "js"))
        app.router.add_static("/", path=str(BASE_DIR))
        app.on_startup.append(self._on_startup)
        app.on_cleanup.append(self._on_cleanup)
        return app

    async def _on_startup(self, app):
        """启动时：尝试连接配置文件里的设备"""
        logger.debug("开始启动初始化...")
        device_config = self.config_manager.get_device()
        if device_config:
            device_ip = device_config.get("ip")
            if device_ip:
                # 无论当前通不通，先把它设为靶子，探针才有目标
                self.device_ip = device_ip
                logger.debug(f"尝试连接已知设备: {device_ip}")
                result = await _check_port(device_ip, DANGBEI_CONTROL_PORT, timeout=0.5)
                if result:
                    self._cached_connected = True
                    await self.config_manager.set_device_state(STATE_ONLINE)
                    logger.info(f"启动成功连上设备: {result}")
                else:
                    logger.debug(f"已知设备 {device_ip} 连接失败，等待探针接管")
                    self._cached_connected = False
                    await self.config_manager.set_device_state(STATE_OFFLINE)
            else:
                self._cached_connected = False
                await self.config_manager.set_device_state(STATE_OFFLINE)
        else:
            logger.debug("无已知设备配置")
            self._cached_connected = False
            await self.config_manager.set_device_state(STATE_OFFLINE)

        # 启动双轨监控任务
        self._device_monitor_task_obj = asyncio.create_task(self._device_monitor_task())
        self._daily_restart_task_obj = asyncio.create_task(self._daily_restart_task())
        logger.info("双轨监控任务已启动")
        logger.debug("启动初始化完成")

    async def _on_cleanup(self, app):
        """清理：停止后台任务，关闭WebSocket连接"""
        for task in [self._device_monitor_task_obj, self._daily_restart_task_obj]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self._close_ws_connection()
        if self._executor:
            self._executor.shutdown(wait=False)

    async def _device_monitor_task(self):
        """网络探针任务：监控设备物理在线状态"""
        logger.debug("网络探针任务已启动")
        while True:
            try:
                ip_to_check = self.device_ip
                if not ip_to_check and self.config_manager.get_device():
                    ip_to_check = self.config_manager.get_device().get("ip")

                if not ip_to_check:
                    await asyncio.sleep(10)
                    continue

                is_online = bool(
                    await _check_port(ip_to_check, DANGBEI_CONTROL_PORT, timeout=0.5)
                )

                if is_online != self._cached_connected:
                    self._cached_connected = is_online
                    await self.config_manager.set_device_state(
                        STATE_ONLINE if is_online else STATE_OFFLINE
                    )

                    if is_online:
                        logger.info(f"设备已上线: {ip_to_check}")
                        self.device_ip = ip_to_check
                    else:
                        logger.info("设备已离线，关闭残余连接")
                        await self._close_ws_connection()

                await asyncio.sleep(3 if self._cached_connected else 10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"网络探针异常: {e}")
                await asyncio.sleep(10)

    async def _daily_restart_task(self):
        """每日重启监控任务：纯内存读取，捕捉每日首次上线"""
        logger.debug("每日重启监控任务已启动")
        was_offline = not self._cached_connected

        while True:
            try:
                await asyncio.sleep(1)

                today_str = datetime.datetime.now().strftime("%Y-%m-%d")
                last_reboot = self.config_manager.get_last_reboot_date()

                if today_str == last_reboot:
                    was_offline = not self._cached_connected
                    continue

                is_online = self._cached_connected

                if is_online and was_offline:
                    logger.info("检测到今日首次设备上线，等待5秒确保设备初始化完成...")
                    await asyncio.sleep(5)

                    if self._cached_connected:
                        try:
                            logger.info("开始发送重启指令序列")
                            await self._send_command_persistent(
                                AGENT_COMMANDS["reboot"]
                            )
                            await self.config_manager.set_last_reboot_date(today_str)
                            logger.info(f"今日首次重启已执行，记录日期: {today_str}")

                            await self._close_ws_connection()
                            self._cached_connected = False
                        except Exception as e:
                            logger.error(f"重启指令发送失败: {e}")

                was_offline = not is_online

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"每日重启监控异常: {e}")
                await asyncio.sleep(5)

    async def index(self, request):
        with open(BASE_DIR / "index.html", "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")

    async def _safe_scan(self) -> Optional[Device]:
        """线程安全的扫描，防止并发扫描"""
        async with self._scan_lock:
            if self._is_scanning:
                logger.info("扫描已在进行中，跳过")
                return None
            self._is_scanning = True
            try:
                custom_network = self.config_manager.get_scan_network()
                return await discover_projector(custom_network)
            finally:
                self._is_scanning = False

    async def _get_ws_connection(self) -> websockets.WebSocketClientProtocol:
        """获取或创建持久化的 WebSocket 连接"""
        async with self._ws_lock:
            # 如果有连接，先检查是否可用（兼容不同版本的websockets库）
            if self._ws_connection:
                try:
                    # 检查连接是否可用（不同版本的websockets库属性名可能不同）
                    is_closed = False
                    if hasattr(self._ws_connection, "closed"):
                        is_closed = self._ws_connection.closed
                    elif hasattr(self._ws_connection, "close_code"):
                        is_closed = self._ws_connection.close_code is not None

                    if not is_closed:
                        return self._ws_connection
                except Exception:
                    # 检查失败，说明连接已失效
                    pass

            # 创建新连接
            ws_url = f"ws://{self.device_ip}:{DANGBEI_CONTROL_PORT}"
            logger.info(f"建立新的 WebSocket 连接: {ws_url}")

            # 关闭心跳检测，设备不响应 PONG
            self._ws_connection = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    close_timeout=1,
                    open_timeout=1,
                    ping_interval=None,
                    ping_timeout=None,
                ),
                timeout=1,
            )

            # 连接建立成功后，同步在线状态
            if not self._cached_connected:
                self._cached_connected = True
                asyncio.create_task(self.config_manager.set_device_state(STATE_ONLINE))

            return self._ws_connection

    async def _close_ws_connection(self):
        """关闭 WebSocket 连接"""
        if self._ws_connection:
            try:
                await self._ws_connection.close()
            except Exception:
                pass
            self._ws_connection = None

    async def _send_command_persistent(
        self, command: str | list, is_retry: bool = False
    ) -> bool:
        """使用持久化连接发送命令，具备并发锁与智能重试机制"""
        ws = await self._get_ws_connection()
        try:
            # 加锁，确保同一时间只有一个协程发送
            async with self._ws_send_lock:
                if isinstance(command, list):
                    for step in command:
                        cmd = AGENT_COMMANDS.get(step)
                        if cmd and not isinstance(cmd, list):
                            await asyncio.wait_for(ws.send(cmd), timeout=0.5)
                            await asyncio.sleep(0.6)
                else:
                    await asyncio.wait_for(ws.send(command), timeout=0.5)
                    await asyncio.sleep(0.1)
            return True
        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.InvalidHandshake,
            Exception,
        ) as e:
            logger.warning(f"WebSocket 发送异常: {e}")
            await self._close_ws_connection()

            if isinstance(e, websockets.exceptions.InvalidHandshake):
                self._cached_connected = False
                asyncio.create_task(self.config_manager.set_device_state(STATE_OFFLINE))

            # 如果是单个按键失败，可以重试；如果是宏指令（list）失败，绝不重试防止误操作
            if not is_retry and not isinstance(command, list):
                logger.info("尝试重新连接并补发单键指令...")
                return await self._send_command_persistent(command, is_retry=True)

            raise

    async def handle_key(self, request):
        """处理按键请求"""
        try:
            data = await request.json()
            key = data.get("key", "").lower()
            logger.debug(f"收到按键请求: {key}")

            if not key:
                logger.debug("请求缺少key参数")
                return web.json_response(
                    {"success": False, "error": "缺少key参数"}, status=400
                )

            # 检查设备状态
            state = self.config_manager.get_device_state()
            if state == STATE_OFFLINE:
                logger.debug(f"设备离线，拒绝按键请求: {key}")
                return web.json_response(
                    {"success": False, "error": "device_offline", "state": state},
                    status=503,
                )

            target_cmd = AGENT_COMMANDS.get(key)
            if not target_cmd:
                logger.debug(f"未知命令: {key}")
                return web.json_response(
                    {"success": False, "error": "未知命令"}, status=400
                )

            if not self.device_ip:
                logger.debug("无设备IP，标记为离线")
                self._cached_connected = False
                await self.config_manager.set_device_state(STATE_OFFLINE)
                return web.json_response(
                    {
                        "success": False,
                        "error": "device_offline",
                        "state": STATE_OFFLINE,
                    },
                    status=503,
                )

            try:
                logger.debug(f"发送命令到设备: {key}")
                await self._send_command_persistent(target_cmd)
            except Exception as e:
                # 发送失败，直接返回离线，不扫描重试
                logger.warning(f"发送失败: {e}")
                self._cached_connected = False
                await self._close_ws_connection()
                await self.config_manager.set_device_state(STATE_OFFLINE)
                return web.json_response(
                    {
                        "success": False,
                        "error": "device_offline",
                        "state": STATE_OFFLINE,
                    },
                    status=503,
                )

            # 处理音量变化
            if key == "volumeup":
                volume = self.config_manager.get_volume()
                volume = min(VOLUME_MAX, volume + 1)
                await self.config_manager.set_volume(volume)
                logger.debug(f"音量增加至: {volume}")
            elif key == "volumedown":
                volume = self.config_manager.get_volume()
                volume = max(VOLUME_MIN, volume - 1)
                await self.config_manager.set_volume(volume)
                logger.debug(f"音量减少至: {volume}")

            logger.debug(f"按键请求处理成功: {key}")
            return web.json_response({"success": True})

        except Exception as e:
            logger.error(f"处理按键失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_status(self, request):
        """获取设备状态"""
        state = self.config_manager.get_device_state()
        volume = self.config_manager.get_volume()
        return web.json_response(
            {
                "connected": self._cached_connected,
                "state": state,
                "volume": volume,
                "volumeMin": VOLUME_MIN,
                "volumeMax": VOLUME_MAX,
                "deviceIp": self.device_ip,
            }
        )

    async def handle_scan(self, request):
        """触发扫描 - 优先尝试上次连接的设备"""
        logger.info("用户触发扫描...")
        await self.config_manager.set_device_state(STATE_SCANNING)

        device_config = self.config_manager.get_device()
        if device_config:
            last_ip = device_config.get("ip")
            if last_ip:
                logger.info(f"先尝试上次连接的设备: {last_ip}")
                result = await _check_port(last_ip, DANGBEI_CONTROL_PORT, timeout=0.5)
                if result:
                    if self.device_ip and self.device_ip != result:
                        await self._close_ws_connection()
                    self.device_ip = result
                    self._cached_connected = True
                    await self.config_manager.set_device_state(STATE_ONLINE)
                    logger.info(f"成功连上上次的设备: {result}")
                    return web.json_response(
                        {
                            "success": True,
                            "found": True,
                            "device": {
                                "ip": result,
                                "name": device_config.get("name", "当贝设备"),
                            },
                        }
                    )

        logger.info("上次的设备连不上，开始全网扫描...")
        new_device = await self._safe_scan()
        if new_device:
            if self.device_ip and self.device_ip != new_device.ip:
                await self._close_ws_connection()
            self.device_ip = new_device.ip
            self._cached_connected = True
            await self.config_manager.set_device(new_device)
            await self.config_manager.set_device_state(STATE_ONLINE)
            return web.json_response(
                {
                    "success": True,
                    "found": True,
                    "device": {"ip": new_device.ip, "name": new_device.name},
                }
            )
        else:
            self._cached_connected = False
            await self._close_ws_connection()
            await self.config_manager.set_device_state(STATE_OFFLINE)
            return web.json_response({"success": True, "found": False})

    def start(self):
        logger.info("=" * 50)
        logger.info("  内网遥控器服务启动")
        logger.info("=" * 50)
        local_ip = self._get_local_ip()
        logger.info("请确保运行本程序的电脑和投影设备在同一局域网内")
        logger.info("在手机浏览器访问:")
        logger.info(f"  http://{local_ip}:{self.port}")
        logger.info(f"  http://localhost:{self.port} (本机)")
        logger.info("=" * 50)
        web.run_app(self.app, host=self.host, port=self.port)

    def _get_local_ip(self) -> str:
        return _get_local_ip()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="内网遥控器服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="控制台输出DEBUG级别日志")
    parser.add_argument(
        "--quiet", action="store_true", help="只输出WARNING及以上级别日志"
    )
    args = parser.parse_args()

    # 根据命令行参数调整控制台日志级别
    if args.debug:
        console_handler.setLevel(logging.DEBUG)
        logger.debug("控制台已启用DEBUG级别日志")
    elif args.quiet:
        console_handler.setLevel(logging.WARNING)

    logger.debug("服务启动中...")
    ControlServer(host=args.host, port=args.port).start()


if __name__ == "__main__":
    main()
