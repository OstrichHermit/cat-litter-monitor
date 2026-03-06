"""
拍照管理模块

该模块负责在猫咪进入ROI区域并停留指定时间后自动拍照。
"""

import cv2
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class PhotoCaptureConfig:
    """
    拍照配置类

    Attributes:
        min_stay_seconds: 最小停留时间（秒）
        photo_interval: 拍照间隔（秒），同一停留时间内只拍一次
        photo_base_dir: 照片基础目录
    """
    min_stay_seconds: float = 3.0
    photo_interval: float = 10.0
    photo_base_dir: str = "photo"


class PhotoCaptureManager:
    """
    拍照管理器类

    监控猫咪在ROI区域的停留时间，当停留时间超过阈值时自动拍照。

    Attributes:
        config: 拍照配置
        track_stay_time: 追踪ID到停留时间的映射
        last_photo_time: 追踪ID到上次拍照时间的映射
        logger: 日志对象
    """

    def __init__(self, config: PhotoCaptureConfig, logger=None):
        """
        初始化拍照管理器

        Args:
            config: 拍照配置
            logger: 日志对象
        """
        self.config = config
        self.track_stay_time: Dict[int, float] = {}
        self.last_photo_time: Dict[int, datetime] = {}
        self.logger = logger

        # 确保基础目录存在
        self.base_dir = Path(config.photo_base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def update(
        self,
        track_id: int,
        in_roi: bool,
        current_frame,
        fps: float = 30.0
    ) -> Optional[str]:
        """
        更新追踪状态并判断是否需要拍照

        Args:
            track_id: 追踪ID
            in_roi: 是否在ROI内
            current_frame: 当前帧
            fps: 帧率

        Returns:
            如果拍照成功返回照片路径，否则返回None
        """
        current_time = datetime.now()

        if in_roi:
            # 在ROI内，累加停留时间
            if track_id not in self.track_stay_time:
                self.track_stay_time[track_id] = 0.0

            self.track_stay_time[track_id] += 1.0 / fps

            # 判断是否需要拍照
            stay_time = self.track_stay_time[track_id]

            # 检查是否达到最小停留时间
            if stay_time >= self.config.min_stay_seconds:
                # 检查是否在拍照间隔内
                should_capture = False
                if track_id not in self.last_photo_time:
                    should_capture = True
                else:
                    elapsed = (current_time - self.last_photo_time[track_id]).total_seconds()
                    if elapsed >= self.config.photo_interval:
                        should_capture = True

                if should_capture:
                    # 拍照
                    photo_path = self._capture_photo(current_frame, track_id)
                    if photo_path:
                        self.last_photo_time[track_id] = current_time
                        if self.logger:
                            self.logger.info(
                                f"Track {track_id} 在ROI停留 {stay_time:.1f}秒，"
                                f"拍照保存: {photo_path}"
                            )
                        return photo_path

        else:
            # 不在ROI内，重置停留时间
            if track_id in self.track_stay_time:
                del self.track_stay_time[track_id]
            # 保留 last_photo_time，避免离开ROI后立即返回又重复拍照

        return None

    def _capture_photo(self, frame, track_id: int) -> Optional[str]:
        """
        拍照并保存

        Args:
            frame: 视频帧
            track_id: 追踪ID

        Returns:
            照片保存路径，如果失败返回None
        """
        try:
            # 生成文件路径：photo/YYYY-MM-DD/Unidentified/YYYYMMDD_HHMMSS.jpg
            today = datetime.now()
            date_dir = today.strftime("%Y-%m-%d")
            filename = today.strftime("%Y%m%d_%H%M%S.jpg")

            unidentified_dir = self.base_dir / date_dir / "Unidentified"
            unidentified_dir.mkdir(parents=True, exist_ok=True)

            photo_path = unidentified_dir / filename

            # 保存照片
            cv2.imwrite(str(photo_path), frame)

            return str(photo_path)

        except Exception as e:
            if self.logger:
                self.logger.error(f"拍照失败: {e}")
            return None

    def reset_track(self, track_id: int) -> None:
        """
        重置追踪状态

        Args:
            track_id: 追踪ID
        """
        if track_id in self.track_stay_time:
            del self.track_stay_time[track_id]
        if track_id in self.last_photo_time:
            del self.last_photo_time[track_id]

    def reset_all(self) -> None:
        """
        重置所有追踪状态
        """
        self.track_stay_time.clear()
        self.last_photo_time.clear()
