"""
ROI（感兴趣区域）模块

定义猫砂盆的感兴趣区域，用于检测猫是否进入猫砂盆区域。
"""

import cv2
import numpy as np
from typing import List, Optional, Tuple


class MultiROI:
    """
    多ROI区域管理类

    管理多个猫砂盆的ROI区域，支持矩形和多边形两种类型。

    Attributes:
        rois: ROI列表，每项为 dict，包含 type、rectangle/polygon、name 等字段
    """

    def __init__(
        self,
        rois: Optional[List[dict]] = None,
        # 以下参数用于创建单个默认ROI（向后兼容）
        roi_type: str = 'rectangle',
        rectangle: Optional[List[int]] = None,
        polygon: Optional[List[List[int]]] = None
    ):
        """
        初始化多ROI管理器

        Args:
            rois: ROI列表，每项为 dict，包含:
                - type: 'rectangle' 或 'polygon'
                - rectangle: [x, y, w, h]（矩形时）
                - polygon: [[x1,y1], [x2,y2], ...]（多边形时）
                - name: 名称（可选）
                - id: ID（可选）
            roi_type: 单ROI模式时的类型
            rectangle: 单ROI模式时的矩形参数 [x, y, w, h]
            polygon: 单ROI模式时的多边形顶点列表
        """
        if rois is not None:
            self.rois = rois
        else:
            # 向后兼容：创建单个默认ROI
            if roi_type == 'rectangle':
                self.rois = [{
                    'type': 'rectangle',
                    'rectangle': rectangle or [100, 100, 300, 300],
                    'name': 'ROI 1',
                    'id': 1
                }]
            else:
                self.rois = [{
                    'type': 'polygon',
                    'polygon': polygon or [[100, 100], [400, 100], [400, 400], [100, 400]],
                    'name': 'ROI 1',
                    'id': 1
                }]

    def _contains_point_in_rect(self, rect: List[int], point: Tuple[float, float]) -> bool:
        """判断点是否在矩形内"""
        x, y, w, h = rect
        px, py = point
        return x <= px <= x + w and y <= py <= y + h

    def _contains_point_in_polygon(self, polygon: List[List[int]], point: Tuple[float, float]) -> bool:
        """判断点是否在多边形内（射线法）"""
        poly = np.array(polygon, dtype=np.int32)
        return cv2.pointPolygonTest(poly, point, False) >= 0

    def contains_point(self, point: Tuple[float, float], roi_index: int) -> bool:
        """
        判断点是否在指定ROI内

        Args:
            point: 点坐标 (x, y)
            roi_index: ROI索引（从1开始）

        Returns:
            是否在ROI内
        """
        if roi_index < 1 or roi_index > len(self.rois):
            return False
        roi = self.rois[roi_index - 1]
        if roi['type'] == 'rectangle':
            return self._contains_point_in_rect(roi['rectangle'], point)
        else:
            return self._contains_point_in_polygon(roi['polygon'], point)

    def contains_any(self, point: Tuple[float, float]) -> bool:
        """判断点是否在任一ROI内"""
        for roi in self.rois:
            if roi['type'] == 'rectangle':
                if self._contains_point_in_rect(roi['rectangle'], point):
                    return True
            else:
                if self._contains_point_in_polygon(roi['polygon'], point):
                    return True
        return False

    def get_roi_id(self, point: Tuple[float, float]) -> Optional[int]:
        """
        获取点所在的ROI ID

        Returns:
            ROI ID（从1开始），如果不在任何ROI内则返回None
        """
        for i, roi in enumerate(self.rois, start=1):
            if roi['type'] == 'rectangle':
                if self._contains_point_in_rect(roi['rectangle'], point):
                    return i
            else:
                if self._contains_point_in_polygon(roi['polygon'], point):
                    return i
        return None

    def get_roi_by_id(self, roi_id: int) -> Optional[dict]:
        """根据ID获取ROI数据"""
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
        colors = [
            (0, 255, 0),    # 绿色
            (255, 0, 0),    # 蓝色
            (0, 0, 255),    # 红色
            (255, 255, 0),  # 青色
            (255, 0, 255),  # 品红色
        ]

        for i, roi in enumerate(self.rois):
            color = colors[i % len(colors)]
            name = roi.get('name', f'ROI {i + 1}')

            if roi['type'] == 'rectangle':
                x, y, w, h = roi['rectangle']
                cv2.rectangle(frame_copy, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame_copy, name, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            else:
                poly = np.array(roi['polygon'], dtype=np.int32)
                cv2.polylines(frame_copy, [poly], True, color, 2)
                center = np.mean(roi['polygon'], axis=0).astype(int)
                cv2.putText(frame_copy, name, tuple(center),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        return frame_copy