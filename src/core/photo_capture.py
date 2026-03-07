"""
拍照管理模块

该模块负责在猫咪进入ROI区域并停留指定时间后自动拍照。
支持多个ROI区域使用独立的拍照间隔和停留时间管理。
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
        photo_interval: 拍照间隔（秒），可以是单个值或每个ROI的独立间隔列表
        photo_base_dir: 照片基础目录
    """
    min_stay_seconds: float = 3.0
    photo_interval: float = 10.0  # 默认值，保持向后兼容
    photo_base_dir: str = "photo"

    def __post_init__(self):
        """初始化后处理，支持多种间隔配置格式"""
        # 如果 photo_interval 是列表，直接使用
        # 如果是单个值，创建一个包含该值的列表（默认支持2个ROI）
        if isinstance(self.photo_interval, (list, tuple)):
            self.photo_intervals = list(self.photo_interval)
        else:
            # 默认支持2个ROI，都使用相同的间隔
            self.photo_intervals = [self.photo_interval, self.photo_interval]

    def get_interval(self, roi_index: int) -> float:
        """
        获取指定ROI的拍照间隔

        Args:
            roi_index: ROI索引（从1开始）

        Returns:
            该ROI的拍照间隔（秒）
        """
        # 转换为从0开始的索引
        idx = roi_index - 1
        if 0 <= idx < len(self.photo_intervals):
            return self.photo_intervals[idx]
        # 如果超出范围，返回第一个ROI的间隔
        return self.photo_intervals[0] if self.photo_intervals else self.photo_interval


class PhotoCaptureManager:
    """
    拍照管理器类

    监控猫咪在ROI区域的停留时间，当停留时间超过阈值时自动拍照。
支持每个ROI独立的拍照间隔和停留时间管理。
不依赖追踪ID，只基于ROI区域的检测状态。

    Attributes:
        config: 拍照配置
        roi_stay_time: 每个ROI的累计停留时间（秒），键为roi_index
        roi_has_detection: 每个ROI当前是否有检测，键为roi_index
        last_photo_time: 每个ROI的上次拍照时间，键为roi_index
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
        self.roi_stay_time: Dict[int, float] = {}
        self.roi_has_detection: Dict[int, bool] = {}
        self.last_photo_time: Dict[int, datetime] = {}  # 键为 roi_index
        self.logger = logger

        # 确保基础目录存在
        self.base_dir = Path(config.photo_base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def update(
        self,
        roi_index: int,
        has_detection: bool,
        current_frame,
        fps: float = 30.0
    ) -> Optional[str]:
        """
        更新ROI状态并判断是否需要拍照

        Args:
            roi_index: ROI索引（从1开始，0表示不在任何ROI内）
            has_detection: 该ROI当前是否有检测到猫咪
            current_frame: 当前帧
            fps: 帧率

        Returns:
            如果拍照成功返回照片路径，否则返回None
        """
        current_time = datetime.now()

        if roi_index > 0 and has_detection:
            # ROI内有检测
            self.roi_has_detection[roi_index] = True

            # 初始化停留时间
            if roi_index not in self.roi_stay_time:
                self.roi_stay_time[roi_index] = 0.0

            # 累加停留时间
            self.roi_stay_time[roi_index] += 1.0 / fps

            # 获取该ROI的拍照间隔
            photo_interval = self.config.get_interval(roi_index)
            stay_time = self.roi_stay_time[roi_index]

            # 检查是否达到最小停留时间
            if stay_time >= self.config.min_stay_seconds:
                # 检查是否在拍照间隔内
                should_capture = True

                if roi_index in self.last_photo_time:
                    last_photo_elapsed = (current_time - self.last_photo_time[roi_index]).total_seconds()
                    if last_photo_elapsed < photo_interval:
                        should_capture = False

                if should_capture:
                    # 拍照
                    photo_path = self._capture_photo(current_frame, roi_index)
                    if photo_path:
                        self.last_photo_time[roi_index] = current_time
                        if self.logger:
                            self.logger.info(
                                f"ROI {roi_index}检测到猫咪停留 {stay_time:.1f}秒，"
                                f"拍照保存: {photo_path}"
                            )
                        return photo_path

        else:
            # ROI内无检测或roi_index=0
            if roi_index > 0:
                self.roi_has_detection[roi_index] = False
                # 重置该ROI的停留时间
                if roi_index in self.roi_stay_time:
                    del self.roi_stay_time[roi_index]
            # 保留 last_photo_time，避免离开ROI后立即返回又重复拍照

        return None

    def _capture_photo(self, frame, roi_index: int) -> Optional[str]:
        """
        拍照并保存

        Args:
            frame: 视频帧
            roi_index: ROI索引

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

    def reset_all(self) -> None:
        """
        重置所有状态
        """
        self.roi_stay_time.clear()
        self.roi_has_detection.clear()
        self.last_photo_time.clear()
