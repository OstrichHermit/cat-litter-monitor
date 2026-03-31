"""
目标追踪模块

该模块使用基于IOU的简化追踪算法，适合处理猫厕所监控场景。
相比DeepSORT，更简单且更稳定，不依赖复杂的特征匹配。
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from scipy.optimize import linear_sum_assignment
from src.utils.logger import get_logger

# 获取logger实例
logger = get_logger(__name__)


class TrackState(Enum):
    """
    追踪状态枚举

    Attributes:
        TENTATIVE: 暂定状态（刚开始追踪）
        CONFIRMED: 确认状态（稳定追踪）
        DELETED: 删除状态（追踪丢失）
    """
    TENTATIVE = 1
    CONFIRMED = 2
    DELETED = 3


@dataclass
class Track:
    """
    追踪对象类

    表示一个被追踪的目标。

    Attributes:
        track_id: 追踪ID
        state: 追踪状态
        age: 追踪帧数
        time_since_update: 自上次更新的帧数
        hits: 命中次数
        hit_streak: 连续命中次数
        bbox: 边界框 [x, y, w, h] (左上角+宽高格式)
        confidence: 置信度
        smoothed_bbox: 平滑后的边界框（用于稳定追踪）
        in_roi: 是否在ROI内
        roi_entry_confirmed: ROI进入是否已确认
    """
    track_id: int
    state: TrackState = TrackState.TENTATIVE
    age: int = 0
    time_since_update: int = 0
    hits: int = 0
    hit_streak: int = 0
    bbox: np.ndarray = None
    confidence: float = 0.0
    smoothed_bbox: np.ndarray = None
    in_roi: bool = False
    roi_entry_confirmed: bool = False

    def __post_init__(self):
        if self.bbox is None:
            self.bbox = np.zeros(4)
        if self.smoothed_bbox is None:
            self.smoothed_bbox = np.zeros(4)

    @property
    def tlwh(self) -> np.ndarray:
        """
        获取边界框（左上角宽高格式）

        Returns:
            [x, y, w, h]
        """
        return self.bbox.copy()

    @property
    def tlbr(self) -> np.ndarray:
        """
        获取边界框（左上角右下角格式）

        Returns:
            [x1, y1, x2, y2]
        """
        ret = self.tlwh.copy()
        ret[2:] += ret[:2]
        return ret

    def predict(self) -> None:
        """
        预测下一帧位置（简单的速度预测）
        """
        self.age += 1
        self.time_since_update += 1

        # 如果有历史速度信息，可以预测下一帧位置
        # 这里简化处理：不做预测，保持原位置
        # 这样可以增加匹配机会（因为真实位置不会偏离预测太远）

    def update(self, detection: 'Detection') -> None:
        """
        更新追踪信息

        Args:
            detection: 检测结果
        """
        self.hits += 1
        self.hit_streak += 1
        self.time_since_update = 0

        # 更新边界框
        if hasattr(detection, 'bbox'):
            x1, y1, x2, y2 = detection.bbox
            new_bbox = np.array([x1, y1, x2 - x1, y2 - y1])

            # 使用指数移动平均平滑边界框
            if self.hits > 1:
                alpha = 0.3  # 平滑系数
                self.bbox = alpha * new_bbox + (1 - alpha) * self.bbox
            else:
                self.bbox = new_bbox

            self.smoothed_bbox = self.bbox.copy()

        # 更新置信度
        if hasattr(detection, 'confidence'):
            self.confidence = detection.confidence

        # 更新状态（第一次命中就确认）
        if self.state == TrackState.TENTATIVE and self.hits >= 1:
            self.state = TrackState.CONFIRMED

    def set_in_roi(self, in_roi: bool) -> None:
        """
        设置是否在ROI内

        Args:
            in_roi: 是否在ROI内
        """
        self.in_roi = in_roi

    def confirm_roi_entry(self) -> None:
        """
        确认ROI进入

        当确认猫进入ROI后调用此方法，会延长track的存活时间
        """
        self.roi_entry_confirmed = True
        self.in_roi = True

    def exit_roi(self) -> None:
        """
        离开ROI

        当猫离开ROI后调用此方法
        """
        self.in_roi = False
        self.roi_entry_confirmed = False

    def mark_missed(self) -> None:
        """
        标记丢失

        如果确认在ROI内，延长存活时间以应对检测不稳定的情况
        """
        self.hit_streak = 0

        # 确定删除阈值
        if self.roi_entry_confirmed:
            # ROI内已确认：延长存活时间（60帧 ≈ 2秒@30fps）
            delete_threshold = 60
        elif self.in_roi:
            # 在ROI内但未确认：中等存活时间（30帧 ≈ 1秒@30fps）
            delete_threshold = 30
        elif self.state == TrackState.TENTATIVE:
            # 暂定track：快速删除（2帧）
            delete_threshold = 2
        else:
            # 普通确认track：正常存活时间（10帧）
            delete_threshold = 10

        if self.time_since_update > delete_threshold:
            self.state = TrackState.DELETED

    def is_confirmed(self) -> bool:
        """
        是否已确认

        Returns:
            是否已确认
        """
        return self.state == TrackState.CONFIRMED

    def is_deleted(self) -> bool:
        """
        是否已删除

        Returns:
            是否已删除
        """
        return self.state == TrackState.DELETED

    def is_tentative(self) -> bool:
        """
        是否暂定

        Returns:
            是否暂定
        """
        return self.state == TrackState.TENTATIVE


class ObjectTracker:
    """
    目标追踪器类

    使用基于IOU的简化追踪算法，适合猫厕所监控场景。

    Attributes:
        max_disappeared: 最大消失帧数
        iou_threshold: IOU匹配阈值
        min_confidence: 最小置信度
        next_id: 下一个追踪ID
        tracks: 追踪列表
    """

    def __init__(
        self,
        max_disappeared: int = 10,  # 缩短到10帧，更快删除旧track
        max_distance: float = 0.3,  # 这个参数改名为 iou_threshold
        min_confidence: float = 0.3,
        nn_budget: int = 100,  # 保留参数但不使用，保持接口兼容
        max_tracks: int = 4  # 最大追踪ID数量（适合家中只有4只猫的场景）
    ):
        """
        初始化目标追踪器

        Args:
            max_disappeared: 最大消失帧数（默认10帧，更快删除旧track）
            max_distance: IOU匹配阈值（建议0.3-0.5）
                         0.3 = 30%重叠即可匹配（更宽松，适合形状变化）
                         0.5 = 50%重叠（更严格）
            min_confidence: 最小置信度
            nn_budget: 保留参数，不使用
            max_tracks: 最大追踪ID数量，超过时会删除最不稳定的track
        """
        self.max_disappeared = max_disappeared

        # 如果配置的 max_distance > 0.5，可能是旧配置，自动调整
        if max_distance > 0.5:
            self.iou_threshold = 0.2  # 使用更宽松的阈值以适应快速移动
            logger.warning(f"max_distance={max_distance} 太高，已调整为 0.2")
        else:
            # 使用配置的阈值，但不低于0.2
            self.iou_threshold = max(max_distance, 0.2)

        self.min_confidence = min_confidence
        self.max_tracks = max_tracks

        self.next_id = 1
        self.tracks: List[Track] = []

        logger.info(f"ObjectTracker初始化: IOU阈值={self.iou_threshold:.2f}, "
                   f"最大消失帧数={self.max_disappeared}, 最小置信度={self.min_confidence}, "
                   f"最大追踪数={self.max_tracks}")

    def update(self, detections: List) -> List[Track]:
        """
        更新追踪器

        Args:
            detections: 检测结果列表

        Returns:
            已确认的追踪列表
        """
        # 过滤低置信度检测
        detections = [d for d in detections if d.confidence >= self.min_confidence]

        # 如果没有检测，更新所有追踪
        if len(detections) == 0:
            for track in self.tracks:
                track.predict()
                track.mark_missed()

            # 清理已删除的追踪
            self.tracks = [t for t in self.tracks if not t.is_deleted()]

            confirmed_tracks = [t for t in self.tracks if t.is_confirmed()]
            if len(confirmed_tracks) > 1:
                logger.debug(f"无检测更新，当前有{len(confirmed_tracks)}个已确认track")

            return confirmed_tracks

        # 提取检测边界框
        detection_boxes = np.array([self._tlwh(d) for d in detections])

        # 匹配检测和追踪
        matches, unmatched_detections, unmatched_tracks = self._match_detections_to_tracks(
            detections, detection_boxes, None
        )

        # 更新匹配的追踪
        for track_idx, detection_idx in matches:
            matched_track = self.tracks[track_idx]
            detection_box = detection_boxes[detection_idx]

            # 检查是否有其他track也与这个检测有很高的IOU（>0.7）
            # 如果有，说明是重复的track，应该删除旧的
            for other_track_idx in [i for i in range(len(self.tracks)) if i != track_idx]:
                other_track = self.tracks[other_track_idx]
                if not other_track.is_deleted():
                    iou = self._compute_iou(detection_box, other_track.bbox)
                    if iou > 0.7:  # IOU > 0.7 认为是同一个目标
                        # 删除hits更少的track（保留更稳定的）
                        if other_track.hits < matched_track.hits:
                            logger.debug(f"删除重复track {other_track.track_id} (IOU={iou:.2f}, "
                                       f"hits={other_track.hits}), 保留track {matched_track.track_id} (hits={matched_track.hits})")
                            other_track.state = TrackState.DELETED
                        elif matched_track.hits < other_track.hits:
                            logger.debug(f"删除重复track {matched_track.track_id} (IOU={iou:.2f}, "
                                       f"hits={matched_track.hits}), 保留track {other_track.track_id} (hits={other_track.hits})")
                            matched_track.state = TrackState.DELETED
                            break
                        else:
                            # hits相同，删除time_since_update更大的（更久未更新）
                            if other_track.time_since_update > matched_track.time_since_update:
                                logger.debug(f"删除重复track {other_track.track_id} (IOU={iou:.2f}, "
                                          f"未更新帧数={other_track.time_since_update}), "
                                          f"保留track {matched_track.track_id} (未更新帧数={matched_track.time_since_update})")
                                other_track.state = TrackState.DELETED
                            else:
                                logger.debug(f"删除重复track {matched_track.track_id} (IOU={iou:.2f}), "
                                          f"保留track {other_track.track_id}")
                                matched_track.state = TrackState.DELETED
                                break

            # 只有未删除的track才更新
            if not matched_track.is_deleted():
                self.tracks[track_idx].update(detections[detection_idx])

        # 对于未匹配的检测，先尝试与刚创建的TENTATIVE tracks匹配
        # （可能是因为IOU阈值设置过于严格）
        if len(unmatched_detections) > 0 and len(unmatched_tracks) > 0:
            # 计算未匹配检测和未匹配tracks的IOU
            unmatched_detection_boxes = detection_boxes[unmatched_detections]
            unmatched_track_boxes = np.array([self.tracks[i].bbox for i in unmatched_tracks])

            iou_matrix = self._compute_iou_matrix(unmatched_detection_boxes, unmatched_track_boxes)

            # 尝试用更低的阈值匹配
            lower_threshold = self.iou_threshold * 0.5  # 使用一半的阈值
            for i, det_idx in enumerate(unmatched_detections):
                for j, track_idx in enumerate(unmatched_tracks):
                    if iou_matrix[i, j] >= lower_threshold:
                        # 找到了匹配
                        matches.append((track_idx, det_idx))
                        unmatched_detections.remove(det_idx)
                        unmatched_tracks.remove(track_idx)
                        logger.debug(f"低阈值匹配: track {self.tracks[track_idx].track_id} 与检测 {det_idx} "
                                   f"(IOU={iou_matrix[i, j]:.2f}, 阈值={lower_threshold:.2f})")
                        break

        # 创建新的追踪（仍然未匹配的检测）
        for detection_idx in unmatched_detections:
            new_track_id = self.next_id
            self._initiate_track(detections[detection_idx])
            logger.debug(f"创建新track {new_track_id}")

        # 更新未匹配的追踪
        for track_idx in unmatched_tracks:
            self.tracks[track_idx].predict()
            self.tracks[track_idx].mark_missed()

        # 清理已删除的追踪
        before_cleanup = len(self.tracks)
        self.tracks = [t for t in self.tracks if not t.is_deleted()]
        after_cleanup = len(self.tracks)
        if before_cleanup != after_cleanup:
            logger.debug(f"清理了{before_cleanup - after_cleanup}个已删除的track")

        # 限制最大追踪数量（适合家中固定数量的猫）
        # 按稳定性排序：hits多的优先保留，time_since_update小的优先保留
        confirmed_tracks = [t for t in self.tracks if t.is_confirmed()]
        tentative_tracks = [t for t in self.tracks if t.is_tentative()]

        if len(confirmed_tracks) > self.max_tracks:
            # 按hits和time_since_update排序
            confirmed_tracks.sort(key=lambda t: (t.hits, -t.time_since_update), reverse=True)

            # 删除多余的track
            tracks_to_delete = confirmed_tracks[self.max_tracks:]
            for track in tracks_to_delete:
                logger.debug(f"超过最大追踪数({self.max_tracks})，删除track {track.track_id} "
                           f"(hits={track.hits}, age={track.age})")
                track.state = TrackState.DELETED

            # 再次清理
            self.tracks = [t for t in self.tracks if not t.is_deleted()]

        # 如果已确认track数量已达上限，删除暂定track以避免ID混乱
        if len(confirmed_tracks) >= self.max_tracks and len(tentative_tracks) > 0:
            for track in tentative_tracks:
                logger.debug(f"已确认track已达上限({self.max_tracks})，删除暂定track {track.track_id}")
                track.state = TrackState.DELETED
            self.tracks = [t for t in self.tracks if not t.is_deleted()]

        # 返回确认和暂定的track
        result_tracks = [t for t in self.tracks if t.is_confirmed() or t.is_tentative()]
        confirmed_tracks = [t for t in result_tracks if t.is_confirmed()]

        # 全局去重：检查所有确认track之间是否有高IOU
        if len(confirmed_tracks) > 1:
            self._remove_duplicate_tracks(confirmed_tracks)

        return result_tracks

    def _match_detections_to_tracks(
        self,
        detections: List,
        detection_boxes: np.ndarray,
        detection_features: np.ndarray
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        使用匈牙利算法基于IOU匹配检测和追踪

        Args:
            detections: 检测列表
            detection_boxes: 检测边界框
            detection_features: 检测特征（不使用）

        Returns:
            (匹配对, 未匹配检测索引, 未匹配追踪索引)
        """
        # 获取所有未删除的追踪（包括 TENTATIVE 和 CONFIRMED）
        active_tracks = [i for i, t in enumerate(self.tracks) if not t.is_deleted()]

        # 如果没有活跃的追踪，直接返回
        if len(active_tracks) == 0:
            return [], list(range(len(detections))), []

        # 计算IOU矩阵
        track_boxes = np.array([self.tracks[i].bbox for i in active_tracks])
        iou_matrix = self._compute_iou_matrix(detection_boxes, track_boxes)

        # 将IOU转换为代价矩阵（1 - IOU）
        cost_matrix = 1.0 - iou_matrix

        # 使用匈牙利算法进行最优匹配
        row_indices, col_indices = linear_sum_assignment(cost_matrix)

        # 根据IOU阈值过滤匹配结果
        matches = []
        unmatched_detections = list(range(len(detections)))
        unmatched_tracks = active_tracks.copy()

        for detection_idx, track_local_idx in zip(row_indices, col_indices):
            track_idx = active_tracks[track_local_idx]
            iou = iou_matrix[detection_idx, track_local_idx]

            if iou >= self.iou_threshold:
                matches.append((track_idx, detection_idx))
                if detection_idx in unmatched_detections:
                    unmatched_detections.remove(detection_idx)
                if track_idx in unmatched_tracks:
                    unmatched_tracks.remove(track_idx)

        # 调试信息：输出匹配详情
        if len(matches) > 0 or len(unmatched_detections) > 0:
            match_info = []
            for track_idx, det_idx in matches:
                track = self.tracks[track_idx]
                iou = iou_matrix[det_idx, active_tracks.index(track_idx)]
                match_info.append(f"{track.track_id}(IOU={iou:.2f})")

            logger.debug(f"匹配结果: Track数={len(active_tracks)}, 检测数={len(detections)}, "
                        f"匹配=[{', '.join(match_info)}], 未匹配检测={len(unmatched_detections)}, "
                        f"未匹配track={len(unmatched_tracks)}, IOU阈值={self.iou_threshold:.2f}")

        return matches, unmatched_detections, unmatched_tracks

    def _compute_iou_matrix(
        self,
        boxes_a: np.ndarray,
        boxes_b: np.ndarray
    ) -> np.ndarray:
        """
        计算IOU矩阵

        Args:
            boxes_a: 边界框A [N, 4] (x, y, w, h)
            boxes_b: 边界框B [M, 4] (x, y, w, h)

        Returns:
            IOU矩阵 [N, M]
        """
        iou_matrix = np.zeros((len(boxes_a), len(boxes_b)))

        for i, box_a in enumerate(boxes_a):
            for j, box_b in enumerate(boxes_b):
                iou_matrix[i, j] = self._compute_iou(box_a, box_b)

        return iou_matrix

    def _compute_iou(self, box_a: np.ndarray, box_b: np.ndarray) -> float:
        """
        计算两个边界框的IOU

        Args:
            box_a: 边界框A [x, y, w, h]
            box_b: 边界框B [x, y, w, h]

        Returns:
            IOU值
        """
        x_a_min, y_a_min, w_a, h_a = box_a
        x_b_min, y_b_min, w_b, h_b = box_b

        x_a_max = x_a_min + w_a
        y_a_max = y_a_min + h_a
        x_b_max = x_b_min + w_b
        y_b_max = y_b_min + h_b

        # 计算交集
        inter_x_min = max(x_a_min, x_b_min)
        inter_y_min = max(y_a_min, y_b_min)
        inter_x_max = min(x_a_max, x_b_max)
        inter_y_max = min(y_a_max, y_b_max)

        if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
            return 0.0

        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)

        # 计算并集
        area_a = w_a * h_a
        area_b = w_b * h_b
        union_area = area_a + area_b - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def _initiate_track(self, detection) -> None:
        """
        初始化新的追踪

        Args:
            detection: 检测结果
        """
        # 创建新追踪
        bbox = self._tlwh(detection)
        track = Track(
            track_id=self.next_id,
            state=TrackState.TENTATIVE,
            age=1,
            time_since_update=0,
            hits=1,
            hit_streak=1,
            bbox=bbox,
            smoothed_bbox=bbox.copy(),
            confidence=detection.confidence
        )

        self.tracks.append(track)
        self.next_id += 1

    def _tlwh(self, detection) -> np.ndarray:
        """
        将检测结果转换为左上角宽高格式

        Args:
            detection: 检测结果

        Returns:
            [x, y, w, h]
        """
        x1, y1, x2, y2 = detection.bbox
        return np.array([x1, y1, x2 - x1, y2 - y1])

    def get_track_by_id(self, track_id: int) -> Optional[Track]:
        """
        根据ID获取追踪

        Args:
            track_id: 追踪ID

        Returns:
            追踪对象，如果不存在则返回None
        """
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        return None

    def get_all_tracks(self) -> List[Track]:
        """
        获取所有追踪

        Returns:
            所有追踪列表
        """
        return self.tracks.copy()

    def get_confirmed_tracks(self) -> List[Track]:
        """
        获取已确认的追踪

        Returns:
            已确认的追踪列表
        """
        return [t for t in self.tracks if t.is_confirmed()]

    def reset(self) -> None:
        """
        重置追踪器
        """
        self.next_id = 1
        self.tracks = []
        logger.info("追踪器已重置")

    def _remove_duplicate_tracks(self, confirmed_tracks: List[Track]) -> None:
        """
        移除重复的track（高IOU）

        Args:
            confirmed_tracks: 已确认的track列表
        """
        to_delete = []

        # 两两比较所有track
        for i in range(len(confirmed_tracks)):
            for j in range(i + 1, len(confirmed_tracks)):
                track_a = confirmed_tracks[i]
                track_b = confirmed_tracks[j]

                # 如果已经有track被标记删除，跳过
                if track_a.is_deleted() or track_b.is_deleted():
                    continue

                # 计算IOU
                iou = self._compute_iou(track_a.bbox, track_b.bbox)

                # IOU > 0.7 认为是重复的
                if iou > 0.7:
                    # 保留hits更多的track（更稳定）
                    if track_a.hits > track_b.hits:
                        logger.warning(f"移除重复track {track_b.track_id} (与track {track_a.track_id} IOU={iou:.2f}, "
                                     f"hits: {track_a.hits} vs {track_b.hits})")
                        track_b.state = TrackState.DELETED
                    elif track_b.hits > track_a.hits:
                        logger.warning(f"移除重复track {track_a.track_id} (与track {track_b.track_id} IOU={iou:.2f}, "
                                     f"hits: {track_a.hits} vs {track_b.hits})")
                        track_a.state = TrackState.DELETED
                    else:
                        # hits相同，保留更新的（更近时间更新）
                        if track_a.time_since_update < track_b.time_since_update:
                            logger.warning(f"移除重复track {track_b.track_id} (与track {track_a.track_id} IOU={iou:.2f}, "
                                         f"未更新帧数: {track_a.time_since_update} vs {track_b.time_since_update})")
                            track_b.state = TrackState.DELETED
                        else:
                            logger.warning(f"移除重复track {track_a.track_id} (与track {track_b.track_id} IOU={iou:.2f})")
                            track_a.state = TrackState.DELETED
