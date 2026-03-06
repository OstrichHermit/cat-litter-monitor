"""
行为分析模块

该模块使用位置法（ROI区域判断）检测猫是否进入猫砂盆区域，
并记录相关事件。
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EventType(Enum):
    """
    事件类型枚举

    Attributes:
        ENTER: 进入事件
        EXIT: 离开事件
        INSIDE: 在内部事件
    """
    ENTER = "enter"
    EXIT = "exit"
    INSIDE = "inside"


@dataclass
class LitterEvent:
    """
    猫砂盆事件类

    表示一次完整的使用事件。

    Attributes:
        track_id: 追踪ID
        cat_id: 猫ID（未知时为-1）
        cat_name: 猫名称（未知时为"未知"）
        enter_time: 进入时间
        exit_time: 离开时间
        duration: 持续时间（秒）
        start_frame: 开始帧号
        end_frame: 结束帧号
        roi_id: ROI区域ID（用于标识是哪个猫砂盆）
    """
    track_id: int
    cat_id: int = -1
    cat_name: str = "未知"
    enter_time: datetime = None
    exit_time: Optional[datetime] = None
    duration: float = 0.0
    start_frame: int = 0
    end_frame: Optional[int] = None
    roi_id: int = 1

    def is_complete(self) -> bool:
        """
        事件是否完成（已离开）

        Returns:
            是否完成
        """
        return self.exit_time is not None

    def to_dict(self) -> Dict:
        """
        转换为字典

        Returns:
            事件字典
        """
        return {
            'track_id': self.track_id,
            'cat_id': self.cat_id,
            'cat_name': self.cat_name,
            'enter_time': self.enter_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'duration': self.duration,
            'start_frame': self.start_frame,
            'end_frame': self.end_frame,
            'roi_id': self.roi_id
        }


class ROI:
    """
    ROI（感兴趣区域）类

    定义猫砂盆的感兴趣区域。

    Attributes:
        type: ROI类型（'rectangle' 或 'polygon'）
        rectangle: 矩形ROI参数 [x, y, w, h]
        polygon: 多边形ROI顶点列表
    """

    def __init__(
        self,
        roi_type: str = 'rectangle',
        rectangle: Optional[List[int]] = None,
        polygon: Optional[List[List[int]]] = None
    ):
        """
        初始化ROI

        Args:
            roi_type: ROI类型（'rectangle' 或 'polygon'）
            rectangle: 矩形ROI参数 [x, y, w, h]
            polygon: 多边形ROI顶点列表 [[x1, y1], [x2, y2], ...]
        """
        self.type = roi_type
        self.rectangle = rectangle or [100, 100, 300, 300]
        self.polygon = polygon or [[100, 100], [400, 100], [400, 400], [100, 400]]

    def contains(self, point: Tuple[float, float]) -> bool:
        """
        判断点是否在ROI内

        Args:
            point: 点坐标 (x, y)

        Returns:
            是否在ROI内
        """
        x, y = point

        if self.type == 'rectangle':
            rx, ry, rw, rh = self.rectangle
            return rx <= x <= rx + rw and ry <= y <= ry + rh

        elif self.type == 'polygon':
            # 使用射线法判断点是否在多边形内
            polygon = np.array(self.polygon, dtype=np.int32)
            return cv2.pointPolygonTest(polygon, (x, y), False) >= 0

        return False

    def draw(self, frame: np.ndarray, color: Tuple[int, int, int] = (0, 255, 0)) -> np.ndarray:
        """
        在帧上绘制ROI

        Args:
            frame: 输入帧
            color: 颜色 (B, G, R)

        Returns:
            绘制后的帧
        """
        frame_copy = frame.copy()

        if self.type == 'rectangle':
            x, y, w, h = self.rectangle
            cv2.rectangle(frame_copy, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame_copy,
                'ROI',
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                color,
                2
            )

        elif self.type == 'polygon':
            polygon = np.array(self.polygon, dtype=np.int32)
            cv2.polylines(frame_copy, [polygon], True, color, 2)

            # 绘制标签
            center = np.mean(self.polygon, axis=0).astype(int)
            cv2.putText(
                frame_copy,
                'ROI',
                tuple(center),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                color,
                2
            )

        return frame_copy


class MultiROI:
    """
    多ROI区域管理类

    管理多个猫砂盆的ROI区域。

    Attributes:
        rois: ROI对象列表
        min_frames_in_roi: 在ROI中的最小帧数
        exit_delay_frames: 离开延迟帧数
    """

    def __init__(self, rois: Optional[List[ROI]] = None):
        """
        初始化多ROI管理器

        Args:
            rois: ROI对象列表
        """
        self.rois = rois or []

    def has_multiple_rois(self) -> bool:
        """
        判断是否有多个ROI

        Returns:
            是否有多个ROI
        """
        return len(self.rois) > 1

    def contains_any(self, point: Tuple[float, float]) -> bool:
        """
        判断点是否在任一ROI内

        Args:
            point: 点坐标 (x, y)

        Returns:
            是否在任一ROI内
        """
        return any(roi.contains(point) for roi in self.rois)

    def get_roi_id(self, point: Tuple[float, float]) -> Optional[int]:
        """
        获取点所在的ROI ID

        Args:
            point: 点坐标 (x, y)

        Returns:
            ROI ID（从1开始），如果不在任何ROI内则返回None
        """
        for i, roi in enumerate(self.rois, start=1):
            if roi.contains(point):
                return i
        return None

    def get_roi_by_id(self, roi_id: int) -> Optional[ROI]:
        """
        根据ID获取ROI对象

        Args:
            roi_id: ROI ID（从1开始）

        Returns:
            ROI对象，如果不存在则返回None
        """
        if 1 <= roi_id <= len(self.rois):
            return self.rois[roi_id - 1]
        return None

    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        """
        在帧上绘制所有ROI

        Args:
            frame: 输入帧

        Returns:
            绘制后的帧
        """
        frame_copy = frame.copy()

        # 为不同的ROI使用不同的颜色
        colors = [
            (0, 255, 0),    # 绿色
            (255, 0, 0),    # 蓝色
            (0, 0, 255),    # 红色
            (255, 255, 0),  # 青色
            (255, 0, 255),  # 品红色
        ]

        for i, roi in enumerate(self.rois):
            color = colors[i % len(colors)]

            if roi.type == 'rectangle':
                x, y, w, h = roi.rectangle
                cv2.rectangle(frame_copy, (x, y), (x + w, y + h), color, 2)
                cv2.putText(
                    frame_copy,
                    f'ROI {i + 1}',
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    color,
                    2
                )

            elif roi.type == 'polygon':
                polygon = np.array(roi.polygon, dtype=np.int32)
                cv2.polylines(frame_copy, [polygon], True, color, 2)

                # 绘制标签
                center = np.mean(roi.polygon, axis=0).astype(int)
                cv2.putText(
                    frame_copy,
                    f'ROI {i + 1}',
                    tuple(center),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    color,
                    2
                )

        return frame_copy


class BehaviorAnalyzer:
    """
    行为分析器类

    使用位置法检测猫是否进入猫砂盆区域。

    Attributes:
        multi_roi: MultiROI对象，管理多个ROI区域
        min_frames_in_roi: 在ROI中的最小帧数
        exit_delay_frames: 离开延迟帧数
        min_duration: 最小持续时间（秒）
        min_interval: 两次事件最小间隔（秒）
        track_states: 追踪状态字典
        events: 事件列表
        frame_count: 帧计数
    """

    def __init__(
        self,
        roi: Optional[ROI] = None,
        multi_roi: Optional[MultiROI] = None,
        min_frames_in_roi: int = 15,
        exit_delay_frames: int = 30,
        min_duration: float = 5.0,
        min_interval: float = 30.0
    ):
        """
        初始化行为分析器

        Args:
            roi: ROI对象（已弃用，保留用于向后兼容）
            multi_roi: MultiROI对象，管理多个ROI区域
            min_frames_in_roi: 在ROI中的最小帧数（用于判断是否进入）
            exit_delay_frames: 离开延迟帧数（用于判断是否真的离开）
            min_duration: 最小持续时间（秒）
            min_interval: 两次事件最小间隔（秒）
        """
        # 向后兼容：如果只提供了单个ROI，将其转换为MultiROI
        if multi_roi is not None:
            self.multi_roi = multi_roi
        elif roi is not None:
            self.multi_roi = MultiROI([roi])
        else:
            self.multi_roi = MultiROI([ROI()])

        self.min_frames_in_roi = min_frames_in_roi
        self.exit_delay_frames = exit_delay_frames
        self.min_duration = min_duration
        self.min_interval = min_interval

        # 追踪状态
        self.track_states: Dict[int, Dict] = {}

        # 事件记录
        self.events: List[LitterEvent] = []
        self.frame_count = 0

    def update(
        self,
        tracks: List,
        fps: float = 30.0
    ) -> List[LitterEvent]:
        """
        更新行为分析

        Args:
            tracks: 追踪列表
            fps: 帧率

        Returns:
            新完成的事件列表
        """
        self.frame_count += 1
        completed_events = []

        # 处理每个追踪
        for track in tracks:
            track_id = track.track_id

            # 获取中心点
            if hasattr(track, 'bbox'):
                bbox = track.bbox
                center_x = bbox[0] + bbox[2] / 2
                center_y = bbox[1] + bbox[3] / 2
                center = (center_x, center_y)
            elif hasattr(track, 'tlwh'):
                tlwh = track.tlwh
                center_x = tlwh[0] + tlwh[2] / 2
                center_y = tlwh[1] + tlwh[3] / 2
                center = (center_x, center_y)
            else:
                continue

            # 判断是否在任一ROI内
            in_roi = self.multi_roi.contains_any(center)
            roi_id = self.multi_roi.get_roi_id(center) or 1

            # 更新追踪状态
            if track_id not in self.track_states:
                self.track_states[track_id] = {
                    'in_roi': False,
                    'frames_in_roi': 0,
                    'frames_out_roi': 0,
                    'current_event': None,
                    'last_event_time': None,
                    'current_roi_id': None
                }

            state = self.track_states[track_id]

            if in_roi:
                # 在ROI内
                state['frames_in_roi'] += 1
                state['frames_out_roi'] = 0

                # 通知追踪器在ROI内（还未确认进入）
                if hasattr(track, 'set_in_roi'):
                    track.set_in_roi(True)

                # 判断是否进入
                if not state['in_roi'] and state['frames_in_roi'] >= self.min_frames_in_roi:
                    # 检查距上次事件的时间间隔
                    if state['last_event_time'] is not None:
                        elapsed = (datetime.now() - state['last_event_time']).total_seconds()
                        if elapsed < self.min_interval:
                            # 间隔太短，忽略
                            continue

                    # 创建进入事件
                    event = LitterEvent(
                        track_id=track_id,
                        cat_id=-1,  # 尚未分类
                        cat_name='未知',
                        enter_time=datetime.now(),
                        exit_time=None,
                        duration=0.0,
                        start_frame=self.frame_count,
                        end_frame=None,
                        roi_id=roi_id
                    )
                    state['current_event'] = event
                    state['in_roi'] = True
                    state['current_roi_id'] = roi_id

                    # 通知追踪器确认ROI进入（延长存活时间）
                    if hasattr(track, 'confirm_roi_entry'):
                        track.confirm_roi_entry()

            else:
                # 不在ROI内
                state['frames_out_roi'] += 1

                # 通知追踪器不在ROI内（但还未确认离开）
                if hasattr(track, 'set_in_roi'):
                    track.set_in_roi(False)

                # 判断是否离开
                if state['in_roi'] and state['frames_out_roi'] >= self.exit_delay_frames:
                    # 结束事件
                    if state['current_event'] is not None:
                        event = state['current_event']
                        event.exit_time = datetime.now()
                        event.end_frame = self.frame_count
                        event.duration = (event.exit_time - event.enter_time).total_seconds()

                        # 检查持续时间
                        if event.duration >= self.min_duration:
                            self.events.append(event)
                            completed_events.append(event)

                            state['last_event_time'] = datetime.now()

                        state['current_event'] = None

                    state['in_roi'] = False
                    state['frames_in_roi'] = 0

                    # 通知追踪器离开ROI
                    if hasattr(track, 'exit_roi'):
                        track.exit_roi()

        return completed_events

    def get_cat_name_for_track(self, track_id: int) -> Optional[str]:
        """
        获取追踪ID对应的猫名字

        Args:
            track_id: 追踪ID

        Returns:
            猫名字，如果未知则返回None
        """
        if track_id in self.track_states:
            return self.track_states[track_id].get('cat_name')
        return None

    def get_active_events(self) -> List[LitterEvent]:
        """
        获取进行中的事件

        Returns:
            进行中的事件列表
        """
        active_events = []

        for state in self.track_states.values():
            if state['current_event'] is not None:
                active_events.append(state['current_event'])

        return active_events

    def get_completed_events(self) -> List[LitterEvent]:
        """
        获取已完成的事件

        Returns:
            已完成的事件列表
        """
        return self.events.copy()

    def get_events_by_cat(self, cat_id: int) -> List[LitterEvent]:
        """
        获取特定猫的事件

        Args:
            cat_id: 猫ID

        Returns:
            事件列表
        """
        return [e for e in self.events if e.cat_id == cat_id]

    def get_events_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[LitterEvent]:
        """
        获取时间范围内的事件

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            事件列表
        """
        return [
            e for e in self.events
            if start_time <= e.enter_time <= end_time
        ]

    def get_daily_statistics(self, date: Optional[datetime] = None) -> Dict[int, int]:
        """
        获取每日统计

        Args:
            date: 日期，如果为None则使用今天

        Returns:
            猫ID到使用次数的映射
        """
        if date is None:
            date = datetime.now().date()

        daily_events = [
            e for e in self.events
            if e.enter_time.date() == date
        ]

        stats = {}
        for event in daily_events:
            cat_id = event.cat_id
            stats[cat_id] = stats.get(cat_id, 0) + 1

        return stats

    def draw_analysis(
        self,
        frame: np.ndarray,
        tracks: List
    ) -> np.ndarray:
        """
        在帧上绘制分析结果

        Args:
            frame: 输入帧
            tracks: 追踪列表（保留参数以兼容接口，但不使用）

        Returns:
            绘制后的帧
        """
        frame_copy = frame.copy()

        # 绘制所有ROI区域
        frame_copy = self.multi_roi.draw_all(frame_copy)

        return frame_copy

    def reset(self) -> None:
        """
        重置分析器
        """
        self.track_states.clear()
        self.events.clear()
        self.frame_count = 0
