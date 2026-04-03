"""
内部 WebSocket API 服务端

在 main 进程中运行，Web 服务器作为客户端连接以接收实时数据。
拆分后 main 和 web 是独立进程，通过 WebSocket 通信。
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Set, Optional

import cv2
import numpy as np
import websockets


class InternalAPIServer:
    """
    内部 WebSocket API 服务端

    在 main 进程中运行，Web 服务器作为客户端连接以接收实时数据。
    提供视频帧、检测结果、追踪结果、运行状态、统计数据的推送能力。
    """

    def __init__(self, host: str = '127.0.0.1', port: int = 5002, logger: logging.Logger = None):
        """
        初始化内部 API 服务端

        Args:
            host: 监听地址，默认 127.0.0.1
            port: 监听端口，默认 5002
            logger: 日志记录器，默认使用模块 logger
        """
        self.host = host
        self.port = port
        self.logger = logger or logging.getLogger(__name__)
        self._clients: Set[websockets.WebSocketServerProtocol] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # 缓存最新状态，供新连接使用
        self._latest_frame_jpeg: Optional[bytes] = None
        self._latest_detections = []
        self._latest_tracks = []
        self._running = False
        self._statistics = {}
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """在后台线程中启动 WebSocket 服务"""
        self._thread = threading.Thread(target=self._run_server, daemon=True, name="InternalAPI")
        self._thread.start()
        self.logger.info(f"内部 API 服务已启动: ws://{self.host}:{self.port}")

    def _run_server(self) -> None:
        """运行 WebSocket 服务器（在独立线程中）"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def main():
            async with websockets.serve(self._handler, self.host, self.port):
                await asyncio.Future()  # 永远运行

        try:
            self._loop.run_until_complete(main())
        except Exception as e:
            self.logger.error(f"内部 API 服务异常: {e}")

    async def _handler(self, websocket):
        """处理客户端连接"""
        self._clients.add(websocket)
        self.logger.info(f"内部 API 客户端已连接 (当前 {len(self._clients)} 个)")
        try:
            # 发送当前状态给新连接的客户端
            await websocket.send(json.dumps({
                'type': 'status',
                'data': {'running': self._running}
            }))
            if self._statistics:
                await websocket.send(json.dumps({
                    'type': 'statistics',
                    'data': self._statistics
                }))
            if self._latest_detections:
                await websocket.send(json.dumps({
                    'type': 'detections',
                    'data': self._latest_detections
                }))
            if self._latest_tracks:
                await websocket.send(json.dumps({
                    'type': 'tracks',
                    'data': self._latest_tracks
                }))
            if self._latest_frame_jpeg is not None:
                await websocket.send(self._latest_frame_jpeg)

            # 保持连接，忽略客户端消息（stop/restart 由 web 端直接调 bat 脚本）
            async for message in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.logger.debug(f"内部 API 客户端连接异常: {e}")
        finally:
            self._clients.discard(websocket)
            self.logger.info(f"内部 API 客户端断开 (当前 {len(self._clients)} 个)")

    def push_frame(self, frame: np.ndarray) -> None:
        """推送视频帧（binary WebSocket frame）"""
        if not self._clients or self._loop is None:
            return
        try:
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                self._latest_frame_jpeg = buffer.tobytes()
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_binary(self._latest_frame_jpeg),
                    self._loop
                )
        except Exception as e:
            self.logger.debug(f"推送帧失败: {e}")

    def push_detections(self, detections: list) -> None:
        """推送检测结果"""
        try:
            data = [d.to_dict() if hasattr(d, 'to_dict') else d for d in detections]
            self._latest_detections = data
            self._broadcast_json({
                'type': 'detections',
                'data': data
            })
        except Exception as e:
            self.logger.debug(f"推送检测结果失败: {e}")

    def push_tracks(self, tracks: list) -> None:
        """推送追踪结果"""
        try:
            data = [
                {'id': t.track_id, 'bbox': list(t.bbox) if hasattr(t, 'bbox') else list(t.tlwh)}
                for t in tracks
            ]
            self._latest_tracks = data
            self._broadcast_json({
                'type': 'tracks',
                'data': data
            })
        except Exception as e:
            self.logger.debug(f"推送追踪结果失败: {e}")

    def push_status(self, running: bool) -> None:
        """推送运行状态"""
        self._running = running
        self._broadcast_json({
            'type': 'status',
            'data': {'running': running}
        })

    def push_statistics(self, statistics: dict) -> None:
        """推送统计数据"""
        self._statistics = statistics
        self._broadcast_json({
            'type': 'statistics',
            'data': statistics
        })

    def push_records_update(self) -> None:
        """通知记录更新"""
        self._broadcast_json({
            'type': 'records_update',
            'data': {'timestamp': datetime.now().isoformat()}
        })

    def _broadcast_json(self, message: dict) -> None:
        """线程安全地广播 JSON 消息"""
        if not self._loop or not self._clients:
            return
        data = json.dumps(message)
        asyncio.run_coroutine_threadsafe(
            self._broadcast_text(data),
            self._loop
        )

    async def _broadcast_text(self, data: str) -> None:
        """广播文本消息到所有客户端"""
        if not self._clients:
            return
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(data)
            except Exception:
                disconnected.add(client)
        self._clients -= disconnected

    async def _broadcast_binary(self, data: bytes) -> None:
        """广播二进制数据到所有客户端"""
        if not self._clients:
            return
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(data)
            except Exception:
                disconnected.add(client)
        self._clients -= disconnected
