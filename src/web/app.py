"""
Web界面模块

该模块提供FastAPI Web应用，用于实时视频流展示和统计数据查看。
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, date
import json
from typing import Optional, Dict, List
import io
import cv2
import numpy as np
from pathlib import Path
import asyncio
import subprocess
import time
import websockets
import logging
import sys
import threading


class ConnectionManager:
    """
    WebSocket连接管理器

    管理所有活跃的WebSocket连接，支持广播消息。
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受新的WebSocket连接"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """移除WebSocket连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """向所有连接广播消息"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    def broadcast_sync(self, message: dict):
        """
        同步方式广播消息（供非async上下文调用）
        尝试获取或创建事件循环来发送消息
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环已在运行，创建一个Task
                asyncio.ensure_future(self.broadcast(message))
            else:
                loop.run_until_complete(self.broadcast(message))
        except RuntimeError:
            # 没有事件循环，尝试创建新的
            try:
                asyncio.run(self.broadcast(message))
            except Exception:
                pass
        except Exception:
            pass


# ============================================================================
# 服务监控辅助函数
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent

LOG_FILES = {
    "main": PROJECT_ROOT / "logs" / "main.log",
    "manager": PROJECT_ROOT / "logs" / "manager.log",
    "go2rtc": PROJECT_ROOT / "logs" / "go2rtc.log",
    "mcp": PROJECT_ROOT / "logs" / "mcp.log",
    "web": PROJECT_ROOT / "logs" / "web.log",
}

# 进程缓存
_process_cache = {"data": [], "cache_time": 0}


def _refresh_process_cache():
    """刷新进程缓存（1秒有效期）"""
    now = time.time()
    if _process_cache["cache_time"] and now - _process_cache["cache_time"] < 1:
        return
    try:
        result = subprocess.run(
            ['wmic', 'process', 'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        _process_cache["data"] = result.stdout.strip().split('\n')
        _process_cache["cache_time"] = now
    except Exception:
        pass


def find_process_by_commandline(pattern: str) -> Optional[int]:
    """通过命令行参数查找进程 PID"""
    _refresh_process_cache()
    try:
        for line in _process_cache["data"]:
            if pattern.lower() in line.lower():
                parts = line.split(',')
                if len(parts) >= 3:
                    pid_str = parts[-1].strip().strip('"')
                    if pid_str.isdigit():
                        return int(pid_str)
    except Exception:
        pass
    return None


def get_service_status(service: str) -> Dict:
    """获取单个服务状态"""
    patterns = {
        "main": "src\\main.py",
        "manager": "src\\manager.py",
        "go2rtc": "go2rtc.exe",
        "mcp": "cat-litter-monitor\\src\\mcp\\server",
        "web": "cat-litter-monitor\\src\\web\\app",
    }

    if service == "go2rtc":
        # go2rtc 用 tasklist 检查
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq go2rtc.exe', '/NH'],
                capture_output=True, text=True, encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            running = 'go2rtc.exe' in result.stdout
            pid = None
            if running:
                parts = result.stdout.strip().split()
                for i, p in enumerate(parts):
                    if p == 'go2rtc.exe' and i + 1 < len(parts):
                        pid_str = parts[i + 1]
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            break
            return {"running": running, "pid": pid}
        except Exception:
            return {"running": False, "pid": None}

    pattern = patterns.get(service)
    if not pattern:
        return {"running": False, "pid": None}

    pid = find_process_by_commandline(pattern)
    return {"running": pid is not None, "pid": pid}


def read_last_lines(log_file: Path, lines: int = 100) -> List[str]:
    """读取日志文件最后 N 行"""
    if not log_file.exists():
        return ["等待服务启动..."]
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            result = [ensure_timestamp(line.strip()) for line in all_lines[-lines:] if line.strip()]
            return result if result else ["等待日志输出..."]
    except Exception as e:
        return [f"读取日志失败: {e}"]


def ensure_timestamp(line: str) -> str:
    """统一日志行时间戳格式为 [YYYY-MM-DD HH:MM:SS]"""
    if not line:
        return line
    import re
    # 已有统一格式，直接返回
    if re.match(r'^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]', line):
        return line
    # go2rtc 格式：HH:MM:SS.mmm INF/WRN/ERR message → 保留原始时间，补上日期
    go2rtc_match = re.match(r'^(\d{2}:\d{2}:\d{2})\.\d+\s+(?:INF|WRN|ERR|DBG)\s+(.*)', line)
    if go2rtc_match:
        date_part = datetime.now().strftime("%Y-%m-%d")
        return f"[{date_part} {go2rtc_match.group(1)}] {go2rtc_match.group(2)}"
    # 其他无时间戳行，补充当前时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] {line}"


class MainBridge:
    """
    WebSocket 客户端，连接到 main 进程的 InternalAPI 接收实时数据。

    在后台线程中运行，断线自动重连。
    """

    def __init__(self, ws_url: str, web_app: 'WebApp', logger: logging.Logger = None):
        self.ws_url = ws_url
        self.web_app = web_app
        self.logger = logger or logging.getLogger(__name__)
        self._running = False
        self._ws = None       # 当前活跃的 WebSocket 连接引用
        self._ws_loop = None  # 当前 asyncio event loop 引用

    def start(self) -> None:
        """在后台线程中启动连接"""
        self._running = True
        thread = threading.Thread(target=self._connect_loop, daemon=True, name="MainBridge")
        thread.start()
        self.logger.info(f"MainBridge 已启动，将连接 {self.ws_url}")

    def stop(self) -> None:
        """停止连接"""
        self._running = False

    def _connect_loop(self) -> None:
        """连接循环，断线自动重连"""
        while self._running:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._connect_and_receive(loop))
                loop.close()
            except Exception as e:
                self.logger.debug(f"MainBridge 连接异常: {e}")

            if self._running:
                self.logger.info("MainBridge 将在 2 秒后重连...")
                time.sleep(2)

    async def _connect_and_receive(self, loop: asyncio.AbstractEventLoop) -> None:
        """建立连接并接收数据"""
        async with websockets.connect(self.ws_url) as ws:
            self._ws = ws
            self._ws_loop = loop
            self.logger.info("MainBridge 已连接到 main 进程")
            try:
                async for message in ws:
                    if not self._running:
                        break
                    # binary frame = JPEG 视频帧
                    if isinstance(message, bytes):
                        try:
                            frame = cv2.imdecode(np.frombuffer(message, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                self.web_app.system_state['frame'] = frame
                        except Exception as e:
                            self.logger.debug(f"解码帧失败: {e}")
                    # text frame = JSON 数据
                    else:
                        try:
                            data = json.loads(message)
                            msg_type = data.get('type')
                            msg_data = data.get('data')

                            if msg_type == 'status':
                                self.web_app.system_state['running'] = msg_data['running']
                                self.web_app.manager.broadcast_sync({
                                    'type': 'status_update',
                                    'data': msg_data
                                })
                            elif msg_type == 'statistics':
                                self.web_app.system_state['statistics'] = msg_data
                                self.web_app.manager.broadcast_sync({
                                    'type': 'statistics_update',
                                    'data': msg_data
                                })
                            elif msg_type == 'detections':
                                self.web_app.system_state['detections'] = msg_data
                            elif msg_type == 'tracks':
                                self.web_app.system_state['tracks'] = msg_data
                            elif msg_type == 'records_update':
                                self.web_app.manager.broadcast_sync({
                                    'type': 'records_update',
                                    'data': msg_data
                                })
                        except json.JSONDecodeError:
                            self.logger.debug(f"无法解析消息: {message}")
                        except Exception as e:
                            self.logger.debug(f"处理消息失败: {e}")
            finally:
                self._ws = None
                self._ws_loop = None

    def send_frame_push_command(self, enabled: bool) -> None:
        """Send frame push enable/disable command to main process via WebSocket"""
        if self._ws and self._ws_loop:
            import json
            message = json.dumps({
                'type': 'set_frame_push',
                'enabled': enabled
            })
            asyncio.run_coroutine_threadsafe(
                self._ws.send(message),
                self._ws_loop
            )


# 缩略图缓存 {filepath: (content_type, thumbnail_bytes)}
_thumbnail_cache: Dict[str, tuple] = {}


class WebApp:
    """
    Web应用类

    负责FastAPI应用的创建和路由配置。

    Attributes:
        app: FastAPI应用实例
        manager: WebSocket连接管理器
        host: 主机地址
        port: 端口
        debug: 调试模式
        stop_callback: 停止系统的回调函数
    """

    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 5000,
        debug: bool = False,
        secret_key: str | None = None,
        database=None,
        main_ws_url: str = None
    ):
        """
        初始化Web应用

        Args:
            host: 主机地址
            port: 端口
            debug: 调试模式
            secret_key: 密钥
            database: 数据库实例（可选）
        """
        self.host = host
        self.port = port
        self.debug = debug
        self.stop_callback = None
        self.restart_callback = None
        self.database = database

        # 内部API连接URL
        self.main_ws_url = main_ws_url
        self._main_bridge = None

        # 视频流客户端计数器
        self.stream_clients = 0

        # 模板和静态文件目录
        self.templates_dir = Path(__file__).parent / 'templates'

        # 创建FastAPI应用
        self.app = FastAPI()

        # 启用CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 禁用静态文件缓存
        class NoCacheMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                if request.url.path.startswith("/static/") and not request.url.path.startswith("/static/photo/"):
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    response.headers["Pragma"] = "no-cache"
                    response.headers["Expires"] = "0"
                return response
        self.app.add_middleware(NoCacheMiddleware)

        # 创建WebSocket连接管理器
        self.manager = ConnectionManager()

        # 存储系统状态
        self.system_state = {
            'running': False,
            'frame': None,
            'detections': [],
            'tracks': [],
            'statistics': {},
            'frame_push_enabled': True
        }

        # 注册路由
        self._register_routes()

        # 挂载静态文件目录
        self.app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    def _register_routes(self) -> None:
        """
        注册路由
        """

        @self.app.get('/')
        async def index(request: Request):
            """主页 - 根据设备类型返回不同模板"""
            user_agent = request.headers.get('user-agent', '').lower()

            # 检测是否是移动设备
            is_mobile = any(mobile in user_agent for mobile in
                          ['iphone', 'android', 'ipad', 'mobile', 'ipod'])

            if is_mobile:
                template_path = self.templates_dir / 'mobile.html'
            else:
                template_path = self.templates_dir / 'index.html'

            return FileResponse(str(template_path))

        @self.app.get('/mobile')
        async def mobile():
            """移动端专用页面（可手动访问）"""
            template_path = self.templates_dir / 'mobile.html'
            return FileResponse(str(template_path))

        @self.app.get('/api/status')
        async def status():
            """获取系统状态"""
            return JSONResponse({
                'running': self.system_state['running'],
                'timestamp': datetime.now().isoformat()
            })

        @self.app.get('/api/statistics')
        async def statistics():
            """获取统计数据"""
            return JSONResponse(self.system_state['statistics'])

        @self.app.get('/api/frame-push')
        async def get_frame_push():
            """获取画面推送状态"""
            return JSONResponse({'enabled': self.system_state.get('frame_push_enabled', True)})

        @self.app.post('/api/frame-push')
        async def set_frame_push(request: Request):
            """设置画面推送开关"""
            try:
                data = await request.json()
                enabled = data.get('enabled', True)

                # 更新本地状态（影响 MJPEG 生成）
                self.system_state['frame_push_enabled'] = enabled

                # 转发命令到主进程
                if self._main_bridge:
                    self._main_bridge.send_frame_push_command(enabled)

                # 广播给所有浏览器 WebSocket 客户端
                self.manager.broadcast_sync({
                    'type': 'frame_push_update',
                    'data': {'enabled': enabled}
                })

                return JSONResponse({'success': True, 'enabled': enabled})
            except Exception as e:
                return JSONResponse({'success': False, 'error': str(e)}, status_code=500)

        @self.app.get('/api/records/today')
        async def records_today():
            """获取今天和昨天的记录"""
            try:
                from src.storage.database import Database
                from src.config import get_config

                config = get_config()
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                # 获取今天和昨天的记录
                today_records = database.get_today_records()
                yesterday_records = database.get_yesterday_records()

                return JSONResponse({
                    'success': True,
                    'today': today_records,
                    'yesterday': yesterday_records
                })
            except Exception as e:
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.get('/api/records/unidentified')
        async def records_unidentified():
            """获取未识别的照片列表（包括未识别和无法识别的照片）"""
            try:
                from src.storage.photo_manager import PhotoManager
                from src.config import get_config

                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = photo_config.get('photo_base_dir', 'photo')

                photo_manager = PhotoManager(photo_base_dir)
                unidentified_photos = photo_manager.get_unidentified_photos()
                unidentifiable_photos = photo_manager.get_unidentifiable_photos()

                # 合并两个列表
                photos = unidentified_photos + unidentifiable_photos

                return JSONResponse({
                    'success': True,
                    'photos': photos,
                    'count': len(photos)
                })
            except Exception as e:
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.post('/api/records/mark-unidentifiable')
        async def mark_unidentifiable(request: Request):
            """将照片标记为无法识别，移动到 Unidentifiable 文件夹"""
            try:
                from src.storage.photo_manager import PhotoManager
                from src.config import get_config
                import os

                data = await request.json()
                photo_path = data.get('photo_path')

                if not photo_path:
                    return JSONResponse({
                        'success': False,
                        'error': '缺少照片路径'
                    }, status_code=400)

                # photo_path 是相对路径，格式: YYYY-MM-DD/Unidentified/filename.jpg
                # 需要加上 photo/ 前缀
                if not photo_path.startswith('photo/'):
                    photo_path = f'photo/{photo_path}'

                # 转换为绝对路径
                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = config.get_absolute_path(photo_config.get('photo_base_dir', 'photo'))
                abs_photo_path = config.get_absolute_path(photo_path)

                # 安全检查：确保路径不包含路径穿越
                full_path_resolved = Path(abs_photo_path).resolve()
                photo_dir_resolved = Path(photo_base_dir).resolve()
                if not str(full_path_resolved).startswith(str(photo_dir_resolved)):
                    return JSONResponse({
                        'success': False,
                        'error': 'Invalid path'
                    }, status_code=400)

                # 从路径中提取日期部分
                parts = photo_path.split('/')
                date_str = parts[1] if len(parts) > 1 else None

                if not date_str:
                    return JSONResponse({
                        'success': False,
                        'error': '无法从路径中提取日期'
                    }, status_code=400)

                # 使用 PhotoManager 移动照片
                photo_manager = PhotoManager(photo_config.get('photo_base_dir', 'photo'))

                new_path = photo_manager.move_to_unidentifiable(abs_photo_path, date_str)

                if new_path:
                    # 通知前端记录已更新
                    self.notify_records_update()

                    return JSONResponse({
                        'success': True,
                        'message': '已标记为无法识别',
                        'new_path': new_path
                    })
                else:
                    return JSONResponse({
                        'success': False,
                        'error': '移动照片失败'
                    }, status_code=500)
            except Exception as e:
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.delete('/api/records/delete/{record_id}')
        async def delete_record(record_id: int):
            """删除单条记录"""
            try:
                from src.storage.database import Database
                from src.config import get_config
                import os

                config = get_config()
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                # 获取记录信息（用于删除照片文件）
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT photo_path FROM litter_records WHERE id = ?", (record_id,))
                    record = cursor.fetchone()

                if not record:
                    return JSONResponse({
                        'success': False,
                        'error': '记录不存在'
                    }, status_code=404)

                photo_path = record['photo_path']

                # 删除数据库记录
                success = database.delete_record_by_id(record_id)

                if success:
                    # 尝试删除照片文件
                    if photo_path:
                        abs_photo_path = config.get_absolute_path(photo_path)
                        if os.path.exists(abs_photo_path):
                            try:
                                os.remove(abs_photo_path)
                            except Exception as e:
                                print(f"删除照片文件失败: {e}")

                    return JSONResponse({
                        'success': True,
                        'message': '删除成功'
                    })
                else:
                    return JSONResponse({
                        'success': False,
                        'error': '删除失败'
                    }, status_code=500)
            except Exception as e:
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.put('/api/records/edit/{record_id}')
        async def edit_record(request: Request, record_id: int):
            """编辑记录的猫咪"""
            try:
                from src.storage.database import Database
                from src.config import get_config
                from src.storage.photo_manager import PhotoManager
                import os
                import shutil

                data = await request.json()
                new_cat_name = data.get('cat_name')

                if not new_cat_name:
                    return JSONResponse({
                        'success': False,
                        'error': '缺少猫咪名称'
                    }, status_code=400)

                config = get_config()
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                # 获取记录信息
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT cat_name, photo_path, record_date, record_time FROM litter_records WHERE id = ?",
                        (record_id,)
                    )
                    record = cursor.fetchone()

                if not record:
                    return JSONResponse({
                        'success': False,
                        'error': '记录不存在'
                    }, status_code=404)

                old_cat_name = record['cat_name']
                photo_path = record['photo_path']
                record_date = record['record_date']
                record_time = record['record_time']

                # 如果猫咪名称没有变化，直接返回成功
                if old_cat_name == new_cat_name:
                    return JSONResponse({
                        'success': True,
                        'message': '猫咪名称未变化'
                    })

                # 先移动照片，再更新数据库
                photo_moved = False
                new_photo_path = photo_path  # 默认保持原路径

                if photo_path:
                    abs_photo_path = config.get_absolute_path(photo_path)

                    if os.path.exists(abs_photo_path):
                        # 构建新路径：photo/YYYY-MM-DD/Identified/新猫名/文件名
                        filename = os.path.basename(photo_path)
                        new_photo_path = f'photo/{record_date}/Identified/{new_cat_name}/{filename}'
                        new_abs_photo_path = config.get_absolute_path(new_photo_path)

                        try:
                            # 确保目标目录存在
                            os.makedirs(os.path.dirname(new_abs_photo_path), exist_ok=True)

                            # 如果目标文件已存在，先删除它
                            if os.path.exists(new_abs_photo_path):
                                os.remove(new_abs_photo_path)

                            # 移动照片
                            shutil.move(abs_photo_path, new_abs_photo_path)
                            photo_moved = True
                        except Exception as e:
                            print(f"移动照片文件失败: {e}")
                            # 照片移动失败，保持原路径
                            new_photo_path = photo_path
                            photo_moved = False
                    else:
                        print(f"原照片文件不存在: {abs_photo_path}")

                # 更新数据库中的猫咪名称和照片路径
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE litter_records SET cat_name = ?, photo_path = ? WHERE id = ?",
                        (new_cat_name, new_photo_path, record_id)
                    )
                    conn.commit()

                # 更新每日统计
                from datetime import datetime
                record_date_obj = datetime.fromisoformat(record_date).date() if isinstance(record_date, str) else record_date
                database.update_daily_statistics(record_date_obj)

                return JSONResponse({
                    'success': True,
                    'message': '修改成功',
                    'photo_moved': photo_moved
                })
            except Exception as e:
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.delete('/api/records/unidentified/delete')
        async def delete_unidentified_photo(request: Request):
            """删除未识别的照片"""
            try:
                from src.config import get_config
                import os

                data = await request.json()
                photo_path = data.get('photo_path')

                if not photo_path:
                    return JSONResponse({
                        'success': False,
                        'error': '缺少照片路径'
                    }, status_code=400)

                # photo_path 是相对路径，格式: YYYY-MM-DD/Unidentified/filename.jpg
                # 需要加上 photo/ 前缀
                if not photo_path.startswith('photo/'):
                    photo_path = f'photo/{photo_path}'

                # 转换为绝对路径
                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = config.get_absolute_path(photo_config.get('photo_base_dir', 'photo'))
                abs_photo_path = config.get_absolute_path(photo_path)

                # 安全检查：确保路径不包含路径穿越
                full_path_resolved = Path(abs_photo_path).resolve()
                photo_dir_resolved = Path(photo_base_dir).resolve()
                if not str(full_path_resolved).startswith(str(photo_dir_resolved)):
                    return JSONResponse({
                        'success': False,
                        'error': 'Invalid path'
                    }, status_code=400)

                if os.path.exists(abs_photo_path):
                    os.remove(abs_photo_path)
                    return JSONResponse({
                        'success': True,
                        'message': '删除成功'
                    })
                else:
                    return JSONResponse({
                        'success': False,
                        'error': f'文件不存在: {abs_photo_path}'
                    }, status_code=404)
            except Exception as e:
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.post('/api/records/manual-add')
        async def manual_add_record(request: Request):
            """手动添加记录（将未识别照片入库）"""
            try:
                from src.storage.database import Database
                from src.storage.photo_manager import PhotoManager
                from src.config import get_config
                import os
                from datetime import datetime

                data = await request.json()
                photo_rel_path = data.get('photo_path')  # 格式: YYYY-MM-DD/Unidentified/filename.jpg
                cat_name = data.get('cat_name')

                if not photo_rel_path or not cat_name:
                    return JSONResponse({
                        'success': False,
                        'error': '缺少照片路径或猫咪名称'
                    }, status_code=400)

                # 构建完整路径
                if not photo_rel_path.startswith('photo/'):
                    photo_rel_path = f'photo/{photo_rel_path}'

                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = config.get_absolute_path(photo_config.get('photo_base_dir', 'photo'))
                abs_photo_path = config.get_absolute_path(photo_rel_path)

                # 安全检查：确保路径不包含路径穿越
                full_path_resolved = Path(abs_photo_path).resolve()
                photo_dir_resolved = Path(photo_base_dir).resolve()
                if not str(full_path_resolved).startswith(str(photo_dir_resolved)):
                    return JSONResponse({
                        'success': False,
                        'error': 'Invalid path'
                    }, status_code=400)

                if not os.path.exists(abs_photo_path):
                    return JSONResponse({
                        'success': False,
                        'error': f'照片文件不存在: {abs_photo_path}'
                    }, status_code=404)

                # 从文件名提取日期和时间
                # 文件名格式: YYYYMMDD_HHMMSS.jpg
                filename = os.path.basename(abs_photo_path)
                name_without_ext = os.path.splitext(filename)[0]

                try:
                    # 解析文件名获取日期时间
                    record_date = f"{name_without_ext[0:4]}-{name_without_ext[4:6]}-{name_without_ext[6:8]}"
                    record_time = f"{name_without_ext[9:11]}:{name_without_ext[11:13]}:{name_without_ext[13:15]}"
                except IndexError:
                    # 如果文件名格式不对，使用文件修改时间
                    mtime = os.path.getmtime(abs_photo_path)
                    dt = datetime.fromtimestamp(mtime)
                    record_date = dt.strftime('%Y-%m-%d')
                    record_time = dt.strftime('%H:%M:%S')

                # 使用PhotoManager移动照片
                photo_manager = PhotoManager(photo_config.get('photo_base_dir', 'photo'))

                # 从路径中提取日期部分
                parts = photo_rel_path.split('/')
                date_part = parts[1] if len(parts) > 1 else record_date

                # 移动照片到对应猫咪的文件夹
                new_photo_rel_path = photo_manager.move_photo(
                    photo_rel_path,
                    cat_name,
                    date_part
                )

                if not new_photo_rel_path:
                    return JSONResponse({
                        'success': False,
                        'error': '照片移动失败'
                    }, status_code=500)

                # 插入数据库记录
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                record_id = database.insert_litter_record(
                    cat_name=cat_name,
                    record_date=record_date,
                    record_time=record_time,
                    photo_path=new_photo_rel_path
                )

                # 通知前端记录已更新
                self.notify_records_update()

                return JSONResponse({
                    'success': True,
                    'message': '入库成功',
                    'record_id': record_id
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JSONResponse({
                    'success': False,
                    'error': str(e)
                }, status_code=500)

        @self.app.post('/api/stop')
        async def stop_service():
            """停止系统服务"""
            try:
                import subprocess
                import sys
                from pathlib import Path

                # 获取项目根目录
                project_root = Path(__file__).parent.parent.parent
                stop_script = project_root / 'stop.bat'

                if stop_script.exists():
                    # 在后台执行停止脚本
                    if sys.platform == 'win32':
                        # Windows: 使用 shell=True 并传递字符串
                        subprocess.Popen(
                            f'cmd /c "{stop_script}"',
                            shell=True,
                            cwd=str(project_root),
                            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                        )
                    else:
                        subprocess.Popen(
                            [str(stop_script)],
                            cwd=str(project_root),
                            start_new_session=True
                        )
                    return JSONResponse({'status': 'stopping', 'message': '系统正在停止...'})
                else:
                    return JSONResponse({'status': 'error', 'message': f'停止脚本不存在: {stop_script}'}, status_code=500)
            except Exception as e:
                return JSONResponse({'status': 'error', 'message': f'停止失败: {str(e)}'}, status_code=500)

        @self.app.post('/api/restart')
        async def restart_service():
            """重启系统服务"""
            try:
                import subprocess
                import sys
                from pathlib import Path

                # 获取项目根目录
                project_root = Path(__file__).parent.parent.parent
                restart_script = project_root / 'restart.bat'

                if restart_script.exists():
                    # 在后台执行重启脚本
                    if sys.platform == 'win32':
                        # Windows: 使用 shell=True 并传递字符串
                        subprocess.Popen(
                            f'cmd /c "{restart_script}"',
                            shell=True,
                            cwd=str(project_root),
                            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                        )
                    else:
                        subprocess.Popen(
                            [str(restart_script)],
                            cwd=str(project_root),
                            start_new_session=True
                        )
                    return JSONResponse({'status': 'restarting', 'message': '系统正在重启...'})
                else:
                    return JSONResponse({'status': 'error', 'message': f'重启脚本不存在: {restart_script}'}, status_code=500)
            except Exception as e:
                return JSONResponse({'status': 'error', 'message': f'重启失败: {str(e)}'}, status_code=500)

        @self.app.get('/video_feed')
        async def video_feed():
            """视频流"""
            return StreamingResponse(
                self._generate_frames(),
                media_type='multipart/x-mixed-replace; boundary=frame'
            )

        @self.app.get('/static/photo/{filepath:path}')
        async def serve_photo(filepath: str):
            """提供照片文件访问"""
            try:
                from src.config import get_config
                import os
                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = config.get_absolute_path(photo_config.get('photo_base_dir', 'photo'))

                # 构建完整文件路径
                full_path = os.path.join(photo_base_dir, filepath)

                # 安全检查：确保full_path在photo_base_dir内
                full_path_resolved = Path(full_path).resolve()
                photo_dir_resolved = Path(photo_base_dir).resolve()

                if not str(full_path_resolved).startswith(str(photo_dir_resolved)):
                    return JSONResponse({'error': 'Invalid path'}, status_code=400)

                if not full_path_resolved.exists():
                    return JSONResponse({'error': 'File not found'}, status_code=404)

                response = FileResponse(str(full_path_resolved))
                response.headers["Cache-Control"] = "public, max-age=86400"
                return response
            except Exception as e:
                return JSONResponse({'error': str(e)}, status_code=404)

        @self.app.get('/thumb/{filepath:path}')
        async def serve_photo_thumbnail(filepath: str):
            """提供照片缩略图（200px 宽，保持宽高比）"""
            try:
                from src.config import get_config
                import os
                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = config.get_absolute_path(photo_config.get('photo_base_dir', 'photo'))

                # 构建完整文件路径
                full_path = os.path.join(photo_base_dir, filepath)

                # 安全检查
                full_path_resolved = Path(full_path).resolve()
                photo_dir_resolved = Path(photo_base_dir).resolve()
                if not str(full_path_resolved).startswith(str(photo_dir_resolved)):
                    return JSONResponse({'error': 'Invalid path'}, status_code=400)

                if not full_path_resolved.exists():
                    return JSONResponse({'error': 'File not found'}, status_code=404)

                # 检查内存缓存
                if filepath in _thumbnail_cache:
                    content_type, thumbnail_bytes = _thumbnail_cache[filepath]
                    return StreamingResponse(
                        io.BytesIO(thumbnail_bytes),
                        media_type=content_type,
                        headers={"Cache-Control": "public, max-age=86400"}
                    )

                # 读取并生成缩略图
                img = cv2.imread(str(full_path_resolved))
                if img is None:
                    return JSONResponse({'error': 'Failed to read image'}, status_code=500)

                h, w = img.shape[:2]
                thumb_width = 200
                thumb_height = int(h * thumb_width / w)
                thumbnail = cv2.resize(img, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)

                # 编码为 JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                success, buffer = cv2.imencode('.jpg', thumbnail, encode_param)
                if not success:
                    return JSONResponse({'error': 'Failed to encode image'}, status_code=500)

                thumbnail_bytes = buffer.tobytes()
                content_type = 'image/jpeg'

                # 存入缓存
                _thumbnail_cache[filepath] = (content_type, thumbnail_bytes)

                return StreamingResponse(
                    io.BytesIO(thumbnail_bytes),
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"}
                )
            except Exception as e:
                return JSONResponse({'error': str(e)}, status_code=500)

        # ---- 服务监控 API ----

        @self.app.get("/api/services/status")
        async def get_services_status():
            """获取所有服务的运行状态"""
            services = ["main", "manager", "go2rtc", "mcp", "web"]
            status = {}
            for service in services:
                status[service] = get_service_status(service)
            return {"status": status, "timestamp": datetime.now().isoformat()}

        @self.app.get("/api/logs/{service}")
        async def get_service_logs(service: str, lines: int = 100):
            """获取服务日志"""
            if service not in LOG_FILES:
                return JSONResponse({"error": "Service not found"}, status_code=404)

            log_file = LOG_FILES[service]
            log_lines = read_last_lines(log_file, lines)
            return {
                "service": service,
                "lines": log_lines,
                "count": len(log_lines),
                "timestamp": datetime.now().isoformat()
            }

        @self.app.websocket("/ws/logs/{service}")
        async def websocket_service_log(websocket: WebSocket, service: str):
            """WebSocket 实时日志流"""
            if service not in LOG_FILES:
                await websocket.close(code=4004)
                return

            await websocket.accept()
            log_file = LOG_FILES[service]

            try:
                await websocket.send_json({"type": "connected", "service": service})

                # 发送最后 50 行作为初始内容
                if log_file.exists():
                    last_lines = read_last_lines(log_file, 50)
                    for line in last_lines:
                        await websocket.send_json({"type": "log", "data": line})

                # 持续监控新内容
                if log_file.exists():
                    with open(log_file, "r", encoding="utf-8") as f:
                        f.seek(0, 2)  # 跳到文件末尾
                        while True:
                            line = f.readline()
                            if line:
                                await websocket.send_json({"type": "log", "data": ensure_timestamp(line.strip())})
                            else:
                                await asyncio.sleep(0.1)
                else:
                    # 文件不存在，等待创建
                    while True:
                        await asyncio.sleep(1)
                        if log_file.exists():
                            # 文件创建了，重新打开并开始 tail
                            with open(log_file, "r", encoding="utf-8") as f:
                                f.seek(0, 2)
                                while True:
                                    line = f.readline()
                                    if line:
                                        await websocket.send_json({"type": "log", "data": ensure_timestamp(line.strip())})
                                    else:
                                        await asyncio.sleep(0.1)

            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        @self.app.websocket("/ws/services/status")
        async def websocket_services_status(websocket: WebSocket):
            """WebSocket 实时服务状态推送"""
            await websocket.accept()
            try:
                await websocket.send_json({"type": "connected"})
                while True:
                    services = ["main", "manager", "go2rtc", "mcp", "web"]
                    status = {}
                    for service in services:
                        status[service] = get_service_status(service)
                    await websocket.send_json({
                        "type": "status_update",
                        "data": status,
                        "timestamp": datetime.now().isoformat()
                    })
                    await asyncio.sleep(2)
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        @self.app.websocket('/ws')
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket端点"""
            await self.manager.connect(websocket)
            try:
                # 发送连接成功消息
                await websocket.send_json({
                    'type': 'connected',
                    'data': 'Connected to Litter Monitor'
                })
                # 保持连接，等待客户端消息（心跳）
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.manager.disconnect(websocket)
                print('Client disconnected')
            except Exception:
                self.manager.disconnect(websocket)

    def _generate_frames(self):
        """
        生成视频帧

        Yields:
            JPEG格式的视频帧
        """
        self.stream_clients += 1
        try:
            while True:
                if not self.system_state.get('frame_push_enabled', True):
                    time.sleep(0.5)
                    continue
                if self.system_state['frame'] is not None:
                    # 编码为JPEG，降低质量以减少带宽
                    ret, buffer = cv2.imencode('.jpg', self.system_state['frame'],
                                              [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ret:
                        frame = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        finally:
            self.stream_clients -= 1

    def update_frame(self, frame: np.ndarray) -> None:
        """
        更新当前帧（只在有客户端连接时才复制）

        Args:
            frame: 视频帧
        """
        try:
            # 只在有客户端观看视频流时才更新帧
            if self.stream_clients > 0:
                self.system_state['frame'] = frame.copy()
        except Exception as e:
            # 静默处理，避免影响主循环
            pass

    def update_detections(self, detections: list) -> None:
        """
        更新检测结果

        Args:
            detections: 检测列表
        """
        try:
            self.system_state['detections'] = [
                d.to_dict() if hasattr(d, 'to_dict') else d
                for d in detections
            ]
        except Exception as e:
            # 静默处理，避免影响主循环
            self.system_state['detections'] = []

    def update_tracks(self, tracks: list) -> None:
        """
        更新追踪结果

        Args:
            tracks: 追踪列表
        """
        try:
            self.system_state['tracks'] = [
                {'id': t.track_id, 'bbox': t.bbox if hasattr(t, 'bbox') else (t.tlwh.tolist() if hasattr(t, 'tlwh') else [])}
                for t in tracks
            ]
        except Exception as e:
            # 静默处理，避免影响主循环
            self.system_state['tracks'] = []

    def update_statistics(self, statistics: Dict) -> None:
        """
        更新统计数据

        Args:
            statistics: 统计数据字典
        """
        self.system_state['statistics'] = statistics

        # 通过WebSocket发送更新
        self.manager.broadcast_sync({
            'type': 'statistics_update',
            'data': statistics
        })

    def set_running(self, running: bool) -> None:
        """
        设置运行状态

        Args:
            running: 是否运行中
        """
        self.system_state['running'] = running
        self.manager.broadcast_sync({
            'type': 'status_update',
            'data': {'running': running}
        })

    def notify_records_update(self) -> None:
        """
        通知前端记录已更新

        通过WebSocket发送更新通知
        """
        try:
            self.manager.broadcast_sync({
                'type': 'records_update',
                'data': {
                    'timestamp': datetime.now().isoformat()
                }
            })
        except Exception as e:
            # 静默处理，避免影响主循环
            pass

    def run(self) -> None:
        """
        运行Web应用
        """
        # 如果配置了 main WebSocket URL，启动 MainBridge 连接
        if self.main_ws_url:
            self._main_bridge = MainBridge(
                ws_url=self.main_ws_url,
                web_app=self,
                logger=logging.getLogger(__name__)
            )
            self._main_bridge.start()

        import uvicorn
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="debug" if self.debug else "warning",
            access_log=False
        )


def create_templates_directory():
    """
    创建模板和静态文件目录
    """
    from pathlib import Path

    templates_dir = Path(__file__).parent / 'templates'
    static_dir = Path(__file__).parent / 'static'
    templates_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)


def main():
    """
    Web服务器独立入口
    """
    import argparse
    import sys
    from pathlib import Path

    # 添加项目路径
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # 设置日志重定向
    from src.utils.log_writer import setup_logging
    setup_logging('web')

    parser = argparse.ArgumentParser(description='猫厕所监控系统 - Web服务器')
    parser.add_argument('--config', type=str, default=None, help='配置文件路径')
    args = parser.parse_args()

    from src.config import get_config
    config = get_config(args.config)

    web_config = config.get_web_config()
    internal_api_config = config.get_main_config()
    internal_api_host = internal_api_config.get('host', '127.0.0.1')
    internal_api_port = internal_api_config.get('port', 5002)

    app = WebApp(
        host=web_config.get('host', '0.0.0.0'),
        port=web_config.get('port', 5000),
        debug=web_config.get('debug', False),
        main_ws_url=f"ws://{internal_api_host}:{internal_api_port}"
    )

    # 创建模板目录
    create_templates_directory()

    app.run()


if __name__ == '__main__':
    main()
