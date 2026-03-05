"""
视频采集模块

该模块负责从USB摄像头、RTSP流或go2rtc获取视频帧，并提供统一的视频采集接口。

支持三种摄像头类型：
1. USB摄像头（usb）
2. RTSP网络摄像头（rtsp）
3. go2rtc流媒体服务器（go2rtc）
"""

import cv2
import threading
import time
import requests
import subprocess
import numpy as np
import sys
from typing import Optional, Tuple, Dict, Any
from queue import Queue, Empty
from dataclasses import dataclass


class Camera:
    """
    摄像头类

    该类负责从USB摄像头或RTSP流获取视频帧，支持多线程读取以提高性能。

    Attributes:
        camera_type: 摄像头类型（'usb' 或 'rtsp'）
        device_id: USB摄像头设备号
        rtsp_url: RTSP流地址
        width: 视频宽度
        height: 视频高度
        fps: 帧率
        buffer_size: 缓冲区大小
        cap: VideoCapture对象
        queue: 帧队列
        stopped: 停止标志
        thread: 读取线程
    """

    def __init__(
        self,
        camera_type: str = 'usb',
        device_id: int = 0,
        rtsp_url: str = '',
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        buffer_size: int = 1
    ):
        """
        初始化摄像头

        Args:
            camera_type: 摄像头类型（'usb' 或 'rtsp'）
            device_id: USB摄像头设备号
            rtsp_url: RTSP流地址
            width: 视频宽度
            height: 视频高度
            fps: 帧率
            buffer_size: 缓冲区大小
        """
        self.camera_type = camera_type
        self.device_id = device_id
        self.rtsp_url = rtsp_url
        self.width = width
        self.height = height
        self.fps = fps
        self.buffer_size = buffer_size

        self.cap: Optional[cv2.VideoCapture] = None
        self.queue: Queue = Queue(maxsize=buffer_size)
        self.stopped = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """
        启动摄像头

        Returns:
            是否成功启动
        """
        if self.camera_type == 'usb':
            self.cap = cv2.VideoCapture(self.device_id)
        elif self.camera_type == 'rtsp':
            if not self.rtsp_url:
                raise ValueError("RTSP URL不能为空")
            self.cap = cv2.VideoCapture(self.rtsp_url)
        else:
            raise ValueError(f"不支持的摄像头类型: {self.camera_type}")

        if not self.cap.isOpened():
            return False

        # 设置摄像头参数
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        # 设置缓冲区大小
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)

        # 启动读取线程
        self.stopped = False
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

        return True

    def _update(self) -> None:
        """
        更新帧队列（在单独线程中运行）
        """
        while not self.stopped:
            if not self.cap or not self.cap.isOpened():
                break

            ret, frame = self.cap.read()
            if not ret:
                # 读取失败，尝试重新连接
                if self.camera_type == 'rtsp':
                    self.cap.release()
                    time.sleep(1)
                    self.cap = cv2.VideoCapture(self.rtsp_url)
                    if not self.cap.isOpened():
                        continue
                continue

            # 如果队列已满，移除最旧的帧
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except Empty:
                    pass

            # 添加新帧
            self.queue.put(frame)

            # 控制帧率
            time.sleep(1.0 / self.fps)

    def read(self) -> Tuple[bool, Optional[cv2.typing.MatLike]]:
        """
        读取一帧（带超时的阻塞读取）

        使用短超时避免永久阻塞，同时减少"读取帧失败"的误报。

        Returns:
            (是否成功, 帧数据)
        """
        try:
            # 使用0.1秒超时，平衡实时性和稳定性
            frame = self.queue.get(timeout=0.1)
            return True, frame
        except Empty:
            return False, None

    def read_blocking(self) -> Tuple[bool, Optional[cv2.typing.MatLike]]:
        """
        阻塞读取一帧

        Returns:
            (是否成功, 帧数据)
        """
        try:
            frame = self.queue.get(timeout=5.0)
            return True, frame
        except Empty:
            return False, None

    def stop(self) -> None:
        """
        停止摄像头
        """
        self.stopped = True

        if self.thread:
            self.thread.join(timeout=2.0)

        # 停止FFmpeg进程（如果在使用）
        if self.use_ffmpeg:
            self._stop_ffmpeg_process()

        # 释放OpenCV VideoCapture（如果在使用）
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


@dataclass
class Go2RTCConfig:
    """
    go2rtc配置类

    Attributes:
        host: go2rtc服务器地址
        rtsp_port: RTSP端口
        api_port: API端口
        webrtc_port: WebRTC端口
        camera_name: 摄像头名称
        use_webrtc: 是否使用WebRTC流
        username: RTSP认证用户名（可选）
        password: RTSP认证密码（可选）
        use_ffmpeg: 是否使用FFmpeg转码（默认True，解决H265解码问题）
        ffmpeg_path: FFmpeg可执行文件路径（可选，默认使用系统PATH中的ffmpeg）
        decoder: FFmpeg解码器类型（可选，默认auto自动选择）
                可选值: 'auto', 'hevc', 'hevc_qsv', 'hevc_cuvid', 'hevc_amf'
    """
    host: str = "localhost"
    rtsp_port: int = 8554
    api_port: int = 1984
    webrtc_port: int = 8888
    camera_name: str = "xiaomi_cam"
    use_webrtc: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    use_ffmpeg: bool = True
    ffmpeg_path: Optional[str] = None
    decoder: str = "auto"  # 新增：解码器配置


class Go2RTCCamera:
    """
    go2rtc摄像头类

    通过go2rtc流媒体服务器获取视频流，支持小米摄像头4等网络摄像头。
    使用FFmpeg转码解决H265解码问题。

    Attributes:
        config: go2rtc配置对象
        width: 视频宽度
        height: 视频高度
        fps: 帧率
        buffer_size: 缓冲区大小
        cap: VideoCapture对象
        queue: 帧队列
        stopped: 停止标志
        thread: 读取线程
        ffmpeg_process: FFmpeg子进程对象
        use_ffmpeg: 是否使用FFmpeg转码
    """

    def __init__(
        self,
        config: Go2RTCConfig,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        buffer_size: int = 1
    ):
        """
        初始化go2rtc摄像头

        Args:
            config: go2rtc配置对象
            width: 视频宽度
            height: 视频高度
            fps: 帧率
            buffer_size: 缓冲区大小
        """
        self.config = config
        self.width = width
        self.height = height
        self.fps = fps
        self.buffer_size = buffer_size

        self.cap: Optional[cv2.VideoCapture] = None
        self.queue: Queue = Queue(maxsize=buffer_size)
        self.stopped = False
        self.thread: Optional[threading.Thread] = None
        self.stream_url = ""
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.use_ffmpeg = config.use_ffmpeg
        self.ffmpeg_path = config.ffmpeg_path or "ffmpeg"

        # H265解码器回退机制（2026-03-05）
        self._decoder_attempts = 0  # 当前尝试的解码器索引
        self._max_decoder_attempts = 5  # 最多尝试5种解码器
        # Windows平台优先使用Intel QuickSync，然后是软件解码
        self._decoders = [
            'hevc_qsv',     # Intel QuickSync硬件加速
            'hevc',         # 软件解码（兼容性最好）
        ]
        # 如果需要支持更多平台，可以根据sys.platform添加不同的解码器列表

    def _build_stream_url(self) -> str:
        """
        构建RTSP流地址

        Returns:
            RTSP流地址字符串

        Note:
            使用RTSP流而不是MJPEG，因为：
            1. FFmpeg可以更好地处理RTSP流
            2. RTSP流更稳定，延迟更低
            3. 通过FFmpeg转码为H264，OpenCV可以正常解码
        """
        # 构建RTSP流地址
        auth = ""
        if self.config.username and self.config.password:
            auth = f"{self.config.username}:{self.config.password}@"
        return f"rtsp://{auth}{self.config.host}:{self.config.rtsp_port}/{self.config.camera_name}"

    def _build_ffmpeg_command(self, decoder: str = 'auto') -> list:
        """
        构建FFmpeg转码命令（H265→BGR24直接解码）

        Args:
            decoder: 解码器类型，可选值：
                - 'auto': 自动选择（默认）
                - 'hevc': 软件H265解码器
                - 'hevc_qsv': Intel QuickSync硬件加速（需要Intel CPU）

        Returns:
            FFmpeg命令列表

        Note:
            改进的H265解码方案（2026-03-05）：
            问题：小米摄像头的H265流存在严重的解码问题
            解决方案：
            1. 直接将H265解码为BGR24（避免二次编码损失）
            2. 使用更宽容的错误恢复参数
            3. 增加缓冲区大小以处理不稳定的流

            参数优化：
            - thread_queue_size: 增加到2048，处理解码延迟
            - max_delay: 设置为更大的值，允许更多缓冲
            - 设置输出帧率，避免帧率不匹配
        """
        rtsp_url = self._build_stream_url()

        # 根据decoder参数选择解码器
        decoder_option = []
        if decoder == 'hevc_qsv':
            decoder_option = ['-c:v', 'hevc_qsv', '-hwaccel', 'qsv', '-hwaccel_output_format', 'bgr24']
        elif decoder == 'hevc' or decoder == 'auto':
            # 使用软件解码
            decoder_option = []
        else:
            # 自定义解码器
            decoder_option = ['-c:v', decoder]

        command = [
            self.ffmpeg_path,
            '-rtsp_transport', 'tcp',        # 使用TCP传输（更稳定）
            '-err_detect', 'ignore_err',     # 忽略解码错误，继续播放
            '-fflags', '+genpts+igndts',     # 生成PTS，忽略DTS，提高容错性
            '-max_delay', '500000',          # 0.5秒最大延迟（之前0太小）
            '-fflags', '+discardcorrupt',    # 丢弃损坏的数据包
            '-avioflags', 'direct',          # 减少缓冲延迟
            '-probesize', '1000000',         # 增加探测大小，更好地检测流参数
            '-analyzeduration', '3000000',   # 增加分析时间
            '-thread_queue_size', '2048',    # 大幅增加线程队列
            '-vsync', '0',                   # 不同步帧率，使用原始流帧率
        ]

        # 添加解码器选项
        command.extend(decoder_option)

        # 添加输入和输出选项
        command.extend([
            '-i', rtsp_url,                  # 输入RTSP流
            '-c:v', 'rawvideo',              # 不重新编码，直接输出原始视频
            '-pix_fmt', 'bgr24',             # BGR格式（OpenCV原生格式）
            '-f', 'rawvideo',                # 输出原始视频
            '-an',                           # 禁用音频
            '-'                              # 输出到stdout
        ])

        return command

    def _start_ffmpeg_process(self) -> bool:
        """
        启动FFmpeg转码进程（带解码器回退机制）

        Returns:
            是否成功启动

        H265解码器回退机制（2026-03-05）：
            - 尝试多种解码器，直到找到可用的
            - 优先使用硬件解码器（性能更好）
            - 如果硬件解码失败，自动回退到软件解码
        """
        max_attempts = len(self._decoders)

        while self._decoder_attempts < max_attempts:
            current_decoder = self._decoders[self._decoder_attempts]
            print(f"\n[H265解码] 尝试解码器 {self._decoder_attempts + 1}/{max_attempts}: {current_decoder}")

            try:
                command = self._build_ffmpeg_command(decoder=current_decoder)
                print(f"FFmpeg命令: {' '.join(command)}")

                # 创建FFmpeg子进程
                self.ffmpeg_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,  # 捕获stdout
                    stderr=subprocess.PIPE,  # 捕获stderr（用于调试）
                    bufsize=10**8            # 大缓冲区
                )

                # 启动stderr监控线程
                self._stderr_lines = []
                stderr_thread = threading.Thread(
                    target=self._monitor_ffmpeg_stderr,
                    daemon=True
                )
                stderr_thread.start()

                # 重置帧大小检测状态（每次重启FFmpeg都需要重新检测）
                if hasattr(self, '_detected_frame_size'):
                    delattr(self, '_detected_frame_size')
                if hasattr(self, '_warmup_frames'):
                    delattr(self, '_warmup_frames')
                if hasattr(self, '_frame_read_count'):
                    delattr(self, '_frame_read_count')

                # 等待一下让进程启动
                time.sleep(2)

                # 检查进程是否还在运行
                if self.ffmpeg_process.poll() is not None:
                    # 进程已经退出，读取错误信息
                    _, stderr = self.ffmpeg_process.communicate()
                    stderr_text = stderr.decode('utf-8', errors='ignore')

                    # 检查是否是硬件解码器不可用的错误
                    # 支持的错误模式：No such device, not found, does not support, Hardware device setup failed
                    if ('No such device' in stderr_text or 'not found' in stderr_text or
                        'does not support' in stderr_text or 'Hardware device setup failed' in stderr_text or
                        'Error opening output file' in stderr_text):
                        print(f"⚠ 解码器 '{current_decoder}' 不可用，尝试下一个...")
                        self._stop_ffmpeg_process()
                        self._decoder_attempts += 1
                        continue
                    else:
                        print(f"❌ FFmpeg进程启动失败!")
                        print(f"错误输出:\n{stderr_text}")
                        # 如果是未知错误，也尝试下一个解码器
                        if self._decoder_attempts < max_attempts - 1:
                            print(f"尝试使用下一个解码器...")
                            self._stop_ffmpeg_process()
                            self._decoder_attempts += 1
                            continue
                        return False

                print(f"✓ FFmpeg转码进程启动成功（使用解码器: {current_decoder}）")
                print("开始帧大小自动检测...")

                # 打印FFmpeg输出的前几行（用于诊断）
                time.sleep(1)
                if hasattr(self, '_stderr_lines') and self._stderr_lines:
                    print("FFmpeg初始化日志（前10行）:")
                    for line in self._stderr_lines[:10]:
                        print(f"  {line}")

                # 监控初始错误，如果出现大量解码错误，尝试下一个解码器
                time.sleep(3)
                if hasattr(self, '_stderr_lines'):
                    # 统计严重错误数量
                    severe_errors = sum(1 for line in self._stderr_lines
                                      if 'Could not find ref' in line
                                      or 'Error constructing the frame' in line
                                      or 'Skipping invalid' in line)

                    if severe_errors > 10 and self._decoder_attempts < max_attempts - 1:
                        print(f"⚠ 检测到 {severe_errors} 个严重解码错误，尝试下一个解码器...")
                        self._stop_ffmpeg_process()
                        self._decoder_attempts += 1
                        continue

                return True

            except FileNotFoundError:
                print(f"❌ 错误: 找不到FFmpeg可执行文件 '{self.ffmpeg_path}'")
                print("请确保已安装FFmpeg并添加到系统PATH，或指定正确的ffmpeg_path")
                return False
            except Exception as e:
                print(f"❌ 启动FFmpeg进程失败: {e}")
                import traceback
                traceback.print_exc()
                self._decoder_attempts += 1
                continue

        print(f"❌ 所有解码器尝试失败（共尝试{max_attempts}种）")
        return False

    def _monitor_ffmpeg_stderr(self) -> None:
        """
        监控FFmpeg的stderr输出（在单独线程中运行）
        """
        if not self.ffmpeg_process:
            return

        try:
            for line in iter(self.ffmpeg_process.stderr.readline, b''):
                if line:
                    decoded_line = line.decode('utf-8', errors='ignore').strip()
                    self._stderr_lines.append(decoded_line)

                    # 打印关键信息
                    if any(keyword in decoded_line.lower() for keyword in
                           ['error', 'warning', 'input', 'output', 'stream', 'frame']):
                        print(f"[FFmpeg] {decoded_line}")
        except Exception as e:
            print(f"stderr监控线程异常: {e}")

    def _diagnose_ffmpeg_output(self) -> None:
        """
        诊断FFmpeg输出状态（用于调试）

        修复说明（2026-03-05）：
            - 移除 Windows 上不兼容的 select.select() 调用
            - 在 Windows 上直接尝试读取 stdout，避免 OSError: [WinError 10038]
            - 使用 sys.platform 检测平台，提供更好的跨平台兼容性
        """
        print("\n=== FFmpeg输出诊断 ===")

        # 检查进程状态
        if not self.ffmpeg_process:
            print("❌ FFmpeg进程对象为None")
            return

        poll_result = self.ffmpeg_process.poll()
        if poll_result is not None:
            print(f"❌ FFmpeg进程已退出，返回码: {poll_result}")
            # 读取剩余的stderr
            try:
                remaining_stderr = self.ffmpeg_process.stderr.read()
                if remaining_stderr:
                    print(f"剩余stderr输出:\n{remaining_stderr.decode('utf-8', errors='ignore')}")
            except:
                pass
            return
        else:
            print("✓ FFmpeg进程正在运行")

        # 尝试从stdout读取一小块数据
        try:
            print("\n尝试从stdout读取数据...")

            # 检测操作系统平台
            is_windows = sys.platform.startswith('win')

            if is_windows:
                # Windows平台：使用线程进行超时读取（避免阻塞）
                import threading
                import queue

                result_queue = queue.Queue()

                def read_with_timeout():
                    try:
                        data = self.ffmpeg_process.stdout.read(100)
                        result_queue.put(('success', data))
                    except Exception as e:
                        result_queue.put(('error', str(e)))

                # 启动读取线程
                read_thread = threading.Thread(target=read_with_timeout, daemon=True)
                read_thread.start()
                read_thread.join(timeout=0.5)  # 最多等待500ms

                if read_thread.is_alive():
                    print("⚠ 读取超时（500ms），FFmpeg可能还在初始化")
                    print("   这很正常，系统会等待FFmpeg准备好...")
                else:
                    try:
                        status, data = result_queue.get_nowait()
                        if status == 'success':
                            print(f"✓ 成功读取 {len(data)} 字节测试数据")
                            if len(data) > 0:
                                print(f"  前10字节: {data[:10].hex()}")
                            else:
                                print("⚠ 读取到0字节（FFmpeg还未输出）")
                        else:
                            print(f"⚠ 读取错误: {data}")
                    except queue.Empty:
                        print("⚠ 无法获取读取结果")
            else:
                # Unix/Linux平台：使用 select 进行非阻塞检查
                import select
                readable, _, _ = select.select([self.ffmpeg_process.stdout], [], [], 0.1)
                if readable:
                    test_data = self.ffmpeg_process.stdout.read(100)
                    print(f"✓ 成功读取 {len(test_data)} 字节测试数据")
                    if len(test_data) > 0:
                        print(f"  前10字节: {test_data[:10].hex()}")
                else:
                    print("❌ stdout没有数据可读（超时100ms）")

        except Exception as e:
            print(f"❌ 读取stdout测试失败: {e}")
            import traceback
            traceback.print_exc()

        # 打印stderr的最后几行
        if hasattr(self, '_stderr_lines') and self._stderr_lines:
            print(f"\nFFmpeg stderr记录（共{len(self._stderr_lines)}行）:")
            print("最后5行:")
            for line in self._stderr_lines[-5:]:
                print(f"  {line}")
        else:
            print("\n⚠ 没有stderr输出记录")

        print("=== 诊断结束 ===\n")

    def _read_frame_from_ffmpeg(self) -> Optional[np.ndarray]:
        """
        从FFmpeg进程读取一帧（改进版，支持帧大小自动检测和更健壮的读取逻辑）

        Returns:
            帧数据（BGR格式的numpy数组），读取失败返回None
        """
        if not self.ffmpeg_process or self.ffmpeg_process.poll() is not None:
            print("⚠ FFmpeg进程未运行或已退出")
            return None

        try:
            # 初始化帧大小（第一次读取时可能需要调整）
            if not hasattr(self, '_detected_frame_size'):
                self._detected_frame_size = None
                self._warmup_frames = 0
                self._max_warmup_frames = 10  # 最多跳过10帧预热
                self._frame_read_count = 0

            # 计算期望的帧大小
            expected_frame_size = self.width * self.height * 3  # BGR格式，3个通道

            # 如果还未检测到实际帧大小，尝试自动检测
            if self._detected_frame_size is None:
                # 在预热阶段，尝试从缓冲区读取并检测实际帧大小
                if self._warmup_frames < self._max_warmup_frames:
                    print(f"\n[预热阶段] 第{self._warmup_frames + 1}/{self._max_warmup_frames}次尝试")

                    # 在第一次预热时运行诊断
                    if self._warmup_frames == 0:
                        self._diagnose_ffmpeg_output()

                    # 尝试读取一个较大的缓冲区来检测实际帧大小
                    try:
                        # 读取最大可能的帧大小（假设最大4K分辨率）
                        max_buffer_size = 4096 * 2160 * 3
                        print(f"尝试读取最大缓冲区: {max_buffer_size} 字节...")

                        # 使用线程进行超时读取（避免阻塞）
                        import threading
                        import queue

                        result_queue = queue.Queue()

                        def read_buffer():
                            try:
                                data = self.ffmpeg_process.stdout.read(max_buffer_size)
                                result_queue.put(('success', data))
                            except Exception as e:
                                result_queue.put(('error', str(e)))

                        # 启动读取线程
                        read_thread = threading.Thread(target=read_buffer, daemon=True)
                        read_thread.start()
                        read_thread.join(timeout=2.0)  # 最多等待2秒

                        if read_thread.is_alive():
                            print("⚠ 读取超时（2秒），FFmpeg可能还在解码第一帧")
                            self._warmup_frames += 1
                            time.sleep(0.2)
                            return None

                        # 获取读取结果
                        try:
                            status, buffer = result_queue.get_nowait()
                            if status == 'error':
                                print(f"❌ 读取错误: {buffer}")
                                self._warmup_frames += 1
                                time.sleep(0.1)
                                return None
                        except queue.Empty:
                            print("❌ 无法获取读取结果")
                            self._warmup_frames += 1
                            time.sleep(0.1)
                            return None

                        print(f"实际读取: {len(buffer)} 字节")

                        if len(buffer) == 0:
                            # 没有数据，继续等待
                            print("⚠ 未读取到数据，继续等待...")
                            self._warmup_frames += 1
                            time.sleep(0.1)
                            return None

                        print(f"✓ 成功读取 {len(buffer)} 字节数据")

                        # 尝试检测实际帧大小
                        # 常见分辨率：1920x1080, 1280x720, 640x480
                        possible_sizes = [
                            (1920, 1080),  # Full HD
                            (1280, 720),   # HD
                            (640, 480),    # VGA
                            (2560, 1440),  # 2K
                            (3840, 2160),  # 4K
                        ]

                        detected = False
                        for w, h in possible_sizes:
                            size = w * h * 3
                            if len(buffer) >= size:
                                try:
                                    # 尝试用这个大小创建帧
                                    test_frame = np.frombuffer(buffer[:size], dtype=np.uint8).reshape((h, w, 3))
                                    # 如果成功，使用这个大小
                                    self._detected_frame_size = size
                                    self._actual_width = w
                                    self._actual_height = h
                                    detected = True
                                    print(f"✓ 检测到实际分辨率: {w}x{h}, 帧大小: {size} 字节")
                                    break
                                except ValueError:
                                    continue

                        if not detected:
                            # 无法检测，使用配置的大小
                            self._detected_frame_size = expected_frame_size
                            self._actual_width = self.width
                            self._actual_height = self.height
                            print(f"⚠ 无法自动检测帧大小，使用配置值: {self.width}x{self.height}")

                        self._warmup_frames += 1
                        return None  # 预热帧不返回

                    except Exception as e:
                        print(f"❌ 帧大小检测失败: {e}")
                        import traceback
                        traceback.print_exc()
                        self._detected_frame_size = expected_frame_size
                        self._actual_width = self.width
                        self._actual_height = self.height
                else:
                    # 超过预热帧数，使用配置值
                    self._detected_frame_size = expected_frame_size
                    self._actual_width = self.width
                    self._actual_height = self.height
                    print(f"预热完成，使用配置的帧大小: {self.width}x{self.height}")

            # 使用检测到的帧大小读取
            frame_size = self._detected_frame_size

            # 改进的读取逻辑：使用线程进行超时读取
            import threading
            import queue

            raw_frame = b''
            bytes_remaining = frame_size
            max_attempts = 3  # 最多尝试3次
            attempt = 0

            while bytes_remaining > 0 and attempt < max_attempts:
                # 使用线程读取，避免阻塞
                result_queue = queue.Queue()

                def read_chunk():
                    try:
                        data = self.ffmpeg_process.stdout.read(bytes_remaining)
                        result_queue.put(('success', data))
                    except Exception as e:
                        result_queue.put(('error', str(e)))

                # 启动读取线程
                read_thread = threading.Thread(target=read_chunk, daemon=True)
                read_thread.start()
                read_thread.join(timeout=0.1)  # 100ms 超时

                if read_thread.is_alive():
                    # 读取超时
                    if self._frame_read_count < 5:
                        print(f"⚠ 读取尝试 {attempt + 1}: 超时（100ms）")
                    attempt += 1
                    time.sleep(0.01)
                    continue

                # 获取读取结果
                try:
                    status, chunk = result_queue.get_nowait()
                    if status == 'error':
                        print(f"❌ 读取错误: {chunk}")
                        break
                except queue.Empty:
                    attempt += 1
                    time.sleep(0.01)
                    continue

                if len(chunk) == 0:
                    # 没有数据可读
                    if self._frame_read_count < 5:
                        print(f"⚠ 读取尝试 {attempt + 1}: 无数据")
                    attempt += 1
                    time.sleep(0.01)
                    continue

                raw_frame += chunk
                bytes_remaining -= len(chunk)
                attempt += 1

            # 检查是否读取了完整的帧
            if len(raw_frame) != frame_size:
                # 添加调试信息
                if self._frame_read_count < 5:  # 只在前5帧打印详细信息
                    print(f"❌ 帧读取不完整: 期望 {frame_size} 字节, 实际读取 {len(raw_frame)} 字节")
                    print(f"   已尝试 {attempt} 次, 剩余 {bytes_remaining} 字节")
                    print(f"   实际分辨率: {self._actual_width}x{self._actual_height}")

                # 如果读取的字节数太少，可能是流出了问题
                if len(raw_frame) < frame_size * 0.5:  # 少于50%
                    self._frame_read_count += 1
                    return None

                # 尝试调整：如果读取的字节数接近期望值，尝试填充或截断
                if len(raw_frame) > frame_size * 0.9:  # 超过90%
                    # 填充或截断到正确大小
                    if len(raw_frame) > frame_size:
                        raw_frame = raw_frame[:frame_size]
                    else:
                        raw_frame = raw_frame + b'\x00' * (frame_size - len(raw_frame))

            # 将原始数据转换为numpy数组
            try:
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape(
                    (self._actual_height, self._actual_width, 3)
                )
                if self._frame_read_count < 3:
                    print(f"✓ 成功读取第{self._frame_read_count + 1}帧: {self._actual_width}x{self._actual_height}")
                self._frame_read_count += 1
                return frame
            except ValueError as e:
                # reshape失败，说明帧大小不对
                if self._frame_read_count < 5:
                    print(f"❌ 帧reshape失败: {e}")
                    print(f"   原始数据大小: {len(raw_frame)}, 目标形状: ({self._actual_height}, {self._actual_width}, 3)")
                    # 重置帧大小检测，尝试重新检测
                    self._detected_frame_size = None
                    self._warmup_frames = 0
                self._frame_read_count += 1
                return None

        except Exception as e:
            print(f"❌ 从FFmpeg读取帧时发生异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _stop_ffmpeg_process(self) -> None:
        """
        停止FFmpeg转码进程
        """
        if self.ffmpeg_process:
            try:
                # 发送终止信号
                self.ffmpeg_process.terminate()
                # 等待进程结束（最多2秒）
                self.ffmpeg_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # 如果进程没有及时结束，强制杀死
                self.ffmpeg_process.kill()
                self.ffmpeg_process.wait()
            except Exception as e:
                print(f"停止FFmpeg进程时出错: {e}")
            finally:
                self.ffmpeg_process = None

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
            print(f"警告: 无法连接到go2rtc服务器 {self.config.host}")
            print("将尝试直接连接流地址...")

        # 根据配置选择启动方式
        if self.use_ffmpeg:
            # 使用FFmpeg转码方式
            if not self._start_ffmpeg_process():
                print("FFmpeg转码进程启动失败，尝试使用OpenCV直接读取...")
                # 降级到OpenCV直接读取
                self.use_ffmpeg = False
                return self._start_opencv_direct()
            else:
                # FFmpeg启动成功，启动读取线程
                self.stopped = False
                self.thread = threading.Thread(target=self._update_with_ffmpeg, daemon=True)
                self.thread.start()

                print(f"go2rtc摄像头已启动（FFmpeg转码）: {self.config.camera_name}")
                print(f"RTSP地址: {self.stream_url}")
                return True
        else:
            # 使用OpenCV直接读取（需要H264编码）
            return self._start_opencv_direct()

    def _start_opencv_direct(self) -> bool:
        """
        使用OpenCV直接启动（不使用FFmpeg）

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

        # 设置缓冲区大小
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)

        # 启动读取线程
        self.stopped = False
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

        print(f"go2rtc摄像头已启动（OpenCV直接读取）: {self.config.camera_name}")
        print(f"流地址: {self.stream_url}")
        return True

    def _update(self) -> None:
        """
        更新帧队列（在单独线程中运行）- OpenCV直接读取模式
        改进版：增加容错性，处理H265解码不稳定问题
        """
        consecutive_errors = 0
        max_consecutive_errors = 10  # 允许最多10次连续读取失败
        reconnect_threshold = 5     # 5次失败后尝试重新连接

        while not self.stopped:
            if not self.cap or not self.cap.isOpened():
                break

            ret, frame = self.cap.read()
            if not ret:
                consecutive_errors += 1

                # 只有连续多次失败才打印日志
                if consecutive_errors == 1:
                    print(f"⚠ 读取帧失败（H265解码不稳定，这是正常的）")

                # 如果达到重新连接阈值，尝试重新连接
                if consecutive_errors >= reconnect_threshold:
                    print(f"连续{consecutive_errors}次读取失败，尝试重新连接...")
                    self.cap.release()
                    time.sleep(1)  # 减少等待时间
                    self.cap = cv2.VideoCapture(self.stream_url)
                    if self.cap.isOpened():
                        print("✓ 重新连接成功")
                        consecutive_errors = 0  # 重置计数
                    else:
                        print("❌ 重新连接失败")
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"❌ 连续{max_consecutive_errors}次失败，停止读取")
                            break
                        time.sleep(2)

                # 短暂等待后继续
                time.sleep(0.05)
                continue

            # 读取成功，重置错误计数
            if consecutive_errors > 0:
                print(f"✓ 读取恢复（之前连续失败{consecutive_errors}次）")
                consecutive_errors = 0

            # 如果队列已满，移除最旧的帧
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except Empty:
                    pass

            # 添加新帧
            self.queue.put(frame)

            # 控制帧率（使用更短的延迟）
            time.sleep(0.01)  # 减少延迟，提高响应速度

    def _update_with_ffmpeg(self) -> None:
        """
        更新帧队列（在单独线程中运行）- FFmpeg转码模式
        """
        consecutive_errors = 0
        max_consecutive_errors = 5

        while not self.stopped:
            # 检查FFmpeg进程是否还在运行
            if not self.ffmpeg_process or self.ffmpeg_process.poll() is not None:
                print("FFmpeg进程已停止，尝试重启...")
                # 尝试重启FFmpeg进程
                if not self._start_ffmpeg_process():
                    print("FFmpeg进程重启失败")
                    break
                consecutive_errors = 0

            # 从FFmpeg读取帧
            frame = self._read_frame_from_ffmpeg()

            if frame is None:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"连续{max_consecutive_errors}次读取帧失败，尝试重启FFmpeg进程...")
                    self._stop_ffmpeg_process()
                    consecutive_errors = 0
                time.sleep(0.1)
                continue

            # 重置错误计数
            consecutive_errors = 0

            # 如果队列已满，移除最旧的帧
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except Empty:
                    pass

            # 添加新帧
            self.queue.put(frame)

            # 控制帧率
            time.sleep(1.0 / self.fps)

    def read(self) -> Tuple[bool, Optional[cv2.typing.MatLike]]:
        """
        读取一帧（带超时的阻塞读取）

        使用短超时避免永久阻塞，同时减少"读取帧失败"的误报。

        Returns:
            (是否成功, 帧数据)
        """
        try:
            # 使用0.1秒超时，平衡实时性和稳定性
            frame = self.queue.get(timeout=0.1)
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
        try:
            frame = self.queue.get(timeout=timeout)
            return True, frame
        except Empty:
            return False, None

    def stop(self) -> None:
        """
        停止摄像头
        """
        self.stopped = True

        if self.thread:
            self.thread.join(timeout=2.0)

        # 停止FFmpeg进程（如果在使用）
        if self.use_ffmpeg:
            self._stop_ffmpeg_process()

        # 释放OpenCV VideoCapture（如果在使用）
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
            'use_webrtc': self.config.use_webrtc,
            'use_ffmpeg': self.use_ffmpeg,
            'ffmpeg_path': self.ffmpeg_path,
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


def create_camera_from_config(config: Dict[str, Any]) -> Any:
    """
    根据配置字典创建摄像头实例

    Args:
        config: 配置字典，包含camera和go2rtc配置

    Returns:
        摄像头实例（Camera或Go2RTCCamera）

    Examples:
        >>> config = {
        ...     'camera': {'type': 'go2rtc'},
        ...     'go2rtc': {'host': 'localhost', 'camera_name': 'xiaomi_cam'}
        ... }
        >>> cam = create_camera_from_config(config)
    """
    camera_config = config.get('camera', {})
    camera_type = camera_config.get('type', 'usb')

    if camera_type == 'go2rtc':
        # 创建go2rtc摄像头
        go2rtc_config = config.get('go2rtc', {})
        go2rtc_cfg = Go2RTCConfig(
            host=go2rtc_config.get('host', 'localhost'),
            rtsp_port=go2rtc_config.get('rtsp_port', 8554),
            api_port=go2rtc_config.get('api_port', 1984),
            webrtc_port=go2rtc_config.get('webrtc_port', 8888),
            camera_name=go2rtc_config.get('camera_name', 'xiaomi_cam'),
            use_webrtc=go2rtc_config.get('use_webrtc', False),
            username=go2rtc_config.get('username'),
            password=go2rtc_config.get('password'),
            use_ffmpeg=go2rtc_config.get('use_ffmpeg', True),  # 默认启用FFmpeg
            ffmpeg_path=go2rtc_config.get('ffmpeg_path'),
            decoder=go2rtc_config.get('decoder', 'auto')  # 新增：解码器配置
        )
        return Go2RTCCamera(
            config=go2rtc_cfg,
            width=camera_config.get('width', 1920),
            height=camera_config.get('height', 1080),
            fps=camera_config.get('fps', 30),
            buffer_size=camera_config.get('buffer_size', 1)
        )
    else:
        # 创建普通摄像头
        return Camera(
            camera_type=camera_type,
            device_id=camera_config.get('device_id', 0),
            rtsp_url=camera_config.get('rtsp_url', ''),
            width=camera_config.get('width', 1280),
            height=camera_config.get('height', 720),
            fps=camera_config.get('fps', 30),
            buffer_size=camera_config.get('buffer_size', 1)
        )
