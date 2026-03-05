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
        cat_id: 猫ID（分类器结果）
        cat_name: 猫名称
        enter_time: 进入时间
        exit_time: 离开时间
        duration: 持续时间（秒）
        start_frame: 开始帧号
        end_frame: 结束帧号
    """
    track_id: int
    cat_id: int
    cat_name: str
    enter_time: datetime
    exit_time: Optional[datetime]
    duration: float
    start_frame: int
    end_frame: Optional[int]

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
            'end_frame': self.end_frame
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


class BehaviorAnalyzer:
    """
    行为分析器类

    使用位置法检测猫是否进入猫砂盆区域。

    Attributes:
        roi: ROI对象
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
        min_frames_in_roi: int = 15,
        exit_delay_frames: int = 30,
        min_duration: float = 5.0,
        min_interval: float = 30.0
    ):
        """
        初始化行为分析器

        Args:
            roi: ROI对象
            min_frames_in_roi: 在ROI中的最小帧数（用于判断是否进入）
            exit_delay_frames: 离开延迟帧数（用于判断是否真的离开）
            min_duration: 最小持续时间（秒）
            min_interval: 两次事件最小间隔（秒）
        """
        self.roi = roi or ROI()
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

            # 判断是否在ROI内
            in_roi = self.roi.contains(center)

            # 更新追踪状态
            if track_id not in self.track_states:
                self.track_states[track_id] = {
                    'in_roi': False,
                    'frames_in_roi': 0,
                    'frames_out_roi': 0,
                    'current_event': None,
                    'last_event_time': None,
                    'cat_name': None,  # 持久化存储猫名字
                    'cat_id': -1  # 持久化存储猫ID
                }

            state = self.track_states[track_id]

            if in_roi:
                # 在ROI内
                state['frames_in_roi'] += 1
                state['frames_out_roi'] = 0

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
                        end_frame=None
                    )
                    state['current_event'] = event
                    state['in_roi'] = True

            else:
                # 不在ROI内
                state['frames_out_roi'] += 1

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

        return completed_events

    def update_cat_info(self, track_id: int, cat_id: int, cat_name: str) -> None:
        """
        更新事件的猫信息

        Args:
            track_id: 追踪ID
            cat_id: 猫ID
            cat_name: 猫名称
        """
        # 更新追踪状态（持久化存储）
        if track_id in self.track_states:
            state = self.track_states[track_id]
            state['cat_name'] = cat_name
            state['cat_id'] = cat_id

            # 更新当前事件
            if state['current_event'] is not None:
                state['current_event'].cat_id = cat_id
                state['current_event'].cat_name = cat_name

        # 更新最近的事件
        for event in reversed(self.events):
            if event.track_id == track_id and event.cat_id == -1:
                event.cat_id = cat_id
                event.cat_name = cat_name
                break

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
            tracks: 追踪列表

        Returns:
            绘制后的帧
        """
        frame_copy = frame.copy()

        # 绘制ROI
        frame_copy = self.roi.draw(frame_copy)

        # 绘制追踪状态
        for track in tracks:
            track_id = track.track_id

            # 获取中心点
            if hasattr(track, 'bbox'):
                bbox = track.bbox
                center = (int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2))
            elif hasattr(track, 'tlwh'):
                tlwh = track.tlwh
                center = (int(tlwh[0] + tlwh[2] / 2), int(tlwh[1] + tlwh[3] / 2))
            else:
                continue

            # 检查是否在ROI内
            in_roi = self.roi.contains(center)

            # 绘制中心点
            color = (0, 255, 0) if in_roi else (0, 0, 255)
            cv2.circle(frame_copy, center, 5, color, -1)

            # 绘制标签
            label = f"ID:{track_id}"
            if in_roi and track_id in self.track_states:
                state = self.track_states[track_id]
                label += f" IN:{state['frames_in_roi']}"

            cv2.putText(
                frame_copy,
                label,
                (center[0] + 10, center[1]),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )

        return frame_copy

    def reset(self) -> None:
        """
        重置分析器
        """
        self.track_states.clear()
        self.events.clear()
        self.frame_count = 0
