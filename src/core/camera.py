"""
视频采集模块

该模块负责通过go2rtc流媒体服务器获取视频帧，并提供统一的视频采集接口。

摄像头类型：
- go2rtc流媒体服务器（go2rtc）+ OpenCV直接读取
"""

import cv2
import threading
import time
import requests
import numpy as np
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from queue import Queue, Empty


@dataclass
class Go2RTCConfig:
    """
    go2rtc配置类

    Attributes:
        host: go2rtc服务器地址
        rtsp_port: RTSP端口
        api_port: API端口
        camera_name: 摄像头名称
        username: RTSP认证用户名（可选）
        password: RTSP认证密码（可选）
    """
    host: str = "localhost"
    rtsp_port: int = 8554
    api_port: int = 1984
    camera_name: str = "xiaomi_cam"
    username: Optional[str] = None
    password: Optional[str] = None


class Go2RTCCamera:
    """
    go2rtc摄像头类

    通过go2rtc流媒体服务器获取视频流，支持小米摄像头4等网络摄像头。
    使用OpenCV直接读取RTSP流。

    Attributes:
        config: go2rtc配置对象
        width: 视频宽度
        height: 视频高度
        fps: 帧率
        cap: VideoCapture对象
        stream_url: RTSP流地址
    """

    def __init__(
        self,
        config: Go2RTCConfig,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ):
        """
        初始化go2rtc摄像头

        Args:
            config: go2rtc配置对象
            width: 视频宽度
            height: 视频高度
            fps: 帧率
        """
        self.config = config
        self.width = width
        self.height = height
        self.fps = fps

        self.cap: Optional[cv2.VideoCapture] = None
        self.queue: Queue = Queue(maxsize=1)
        self.stopped = False
        self.thread: Optional[threading.Thread] = None
        self._need_frame = threading.Event()
        self._need_frame.set()  # 允许立即读取第一帧
        self.stream_url = ""

    def _build_stream_url(self) -> str:
        """
        构建RTSP流地址

        Returns:
            RTSP流地址字符串
        """
        auth = ""
        if self.config.username and self.config.password:
            auth = f"{self.config.username}:{self.config.password}@"
        return f"rtsp://{auth}{self.config.host}:{self.config.rtsp_port}/{self.config.camera_name}"

    def check_connection(self) -> bool:
        """
        检查go2rtc服务器连接

        Returns:
            是否连接成功
        """
        try:
            response = requests.get(
                f"http://{self.config.host}:{self.config.api_port}/api/streams",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # 检查指定的摄像头是否在线
                if self.config.camera_name in data:
                    stream_info = data[self.config.camera_name]
                    # 检查是否有生产者（producers）表示流在线
                    producers = stream_info.get('producers', [])
                    return len(producers) > 0
            return False
        except Exception as e:
            print(f"检查go2rtc连接失败: {e}")
            return False

    def get_stream_status(self) -> Dict[str, Any]:
        """
        获取流状态信息

        Returns:
            流状态字典
        """
        try:
            response = requests.get(
                f"http://{self.config.host}:{self.config.api_port}/api/streams",
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {}

    def start(self) -> bool:
        """
        启动摄像头

        Returns:
            是否成功启动
        """
        # 构建流地址
        self.stream_url = self._build_stream_url()

        # 检查go2rtc连接
        if not self.check_connection():
            print(f"警告: 无法连接go2rtc服务器 {self.config.host}，尝试直连")

        # 使用OpenCV直接读取
        return self._start_opencv_direct()

    def _start_opencv_direct(self) -> bool:
        """
        使用OpenCV直接启动RTSP流读取

        Returns:
            是否成功启动
        """
        self.cap = cv2.VideoCapture(self.stream_url)

        if not self.cap.isOpened():
            print(f"无法打开流: {self.stream_url}")
            return False

        # 设置摄像头参数
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # 启动读取线程
        self.stopped = False
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

        print(f"go2rtc摄像头已启动（OpenCV）: {self.config.camera_name}")
        return True

    def _update(self) -> None:
        """
        后台读取线程：与主循环同步，只在需要时才读取帧。

        主循环每次调用 read() 时通过 Event 通知线程读取一帧，
        读取完成后线程阻塞等待下一次通知。这样摄像头线程的读取频率
        与主循环完全一致（10fps），不会浪费帧。
        """
        consecutive_errors = 0

        while not self.stopped:
            # 等待主循环请求下一帧
            self._need_frame.wait()
            if self.stopped:
                break
            self._need_frame.clear()

            if not self.cap or not self.cap.isOpened():
                break

            try:
                ret, frame = self.cap.read()
            except cv2.error as e:
                consecutive_errors += 1
                print(f"OpenCV异常 (连续{consecutive_errors}次): {e}")
                time.sleep(0.05)
                continue
            if not ret:
                consecutive_errors += 1
                time.sleep(0.05)
                continue

            if consecutive_errors > 0:
                consecutive_errors = 0

            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except Empty:
                    pass

            self.queue.put(frame)

    def read(self) -> Tuple[bool, Optional[cv2.typing.MatLike]]:
        """
        读取一帧。通知摄像头线程读取，然后等待结果。

        Returns:
            (是否成功, 帧数据)
        """
        self._need_frame.set()
        try:
            frame = self.queue.get(timeout=0.5)
            return True, frame
        except Empty:
            return False, None

    def read_blocking(self, timeout: float = 5.0) -> Tuple[bool, Optional[cv2.typing.MatLike]]:
        """
        阻塞读取一帧

        Args:
            timeout: 超时时间（秒）

        Returns:
            (是否成功, 帧数据)
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            ret, frame = self.read()
            if ret:
                return True, frame
            time.sleep(0.05)
        return False, None

    def stop(self) -> None:
        """
        停止摄像头
        """
        self.stopped = True

        if self.thread:
            self.thread.join(timeout=2.0)

        if self.cap:
            self.cap.release()
            self.cap = None

    def is_opened(self) -> bool:
        """
        检查摄像头是否打开

        Returns:
            是否打开
        """
        return self.cap is not None and self.cap.isOpened()

    def get_resolution(self) -> Tuple[int, int]:
        """
        获取当前分辨率

        Returns:
            (宽度, 高度)
        """
        if not self.cap:
            return 0, 0

        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return width, height

    def get_fps(self) -> float:
        """
        获取当前帧率

        Returns:
            帧率
        """
        if not self.cap:
            return 0.0

        return self.cap.get(cv2.CAP_PROP_FPS)

    def set_resolution(self, width: int, height: int) -> bool:
        """
        设置分辨率

        Args:
            width: 宽度
            height: 高度

        Returns:
            是否成功设置
        """
        if not self.cap:
            return False

        self.width = width
        self.height = height
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        return True

    def get_config_info(self) -> Dict[str, Any]:
        """
        获取配置信息

        Returns:
            配置信息字典
        """
        return {
            'type': 'go2rtc',
            'host': self.config.host,
            'camera_name': self.config.camera_name,
            'stream_url': self.stream_url,
            'width': self.width,
            'height': self.height,
            'fps': self.fps
        }

    def __enter__(self):
        """
        上下文管理器入口
        """
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        上下文管理器退出
        """
        self.stop()

    def __del__(self):
        """
        析构函数
        """
        self.stop()

    def __repr__(self) -> str:
        """
        字符串表示
        """
        return f"Go2RTCCamera(camera_name={self.config.camera_name}, host={self.config.host})"


def create_camera_from_config(config: Dict[str, Any]) -> Go2RTCCamera:
    """
    根据配置字典创建go2rtc摄像头实例

    Args:
        config: 配置字典，包含camera和go2rtc配置

    Returns:
        Go2RTCCamera实例

    Examples:
        >>> config = {
        ...     'camera': {'width': 1920, 'height': 1080},
        ...     'go2rtc': {'host': 'localhost', 'camera_name': 'xiaomi_cam'}
        ... }
        >>> cam = create_camera_from_config(config)
    """
    camera_config = config.get('camera', {})
    go2rtc_config = config.get('go2rtc', {})
    go2rtc_cfg = Go2RTCConfig(
        host=go2rtc_config.get('host', 'localhost'),
        rtsp_port=go2rtc_config.get('rtsp_port', 8554),
        api_port=go2rtc_config.get('api_port', 1984),
        camera_name=go2rtc_config.get('camera_name', 'xiaomi_cam'),
        username=go2rtc_config.get('username'),
        password=go2rtc_config.get('password')
    )
    return Go2RTCCamera(
        config=go2rtc_cfg,
        width=1920,   # fallback, auto-detected from stream
        height=1080,   # fallback, auto-detected from stream
        fps=30,
    )
