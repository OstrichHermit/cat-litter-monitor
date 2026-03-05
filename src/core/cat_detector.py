"""
猫检测模块

该模块使用YOLOv8进行猫的目标检测，提供检测接口和结果封装。
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from ultralytics import YOLO
import torch


class Detection:
    """
    检测结果类

    封装单个检测结果，包括边界框、置信度和类别。

    Attributes:
        bbox: 边界框 [x1, y1, x2, y2]
        confidence: 置信度
        class_id: 类别ID
        class_name: 类别名称
    """

    def __init__(
        self,
        bbox: List[float],
        confidence: float,
        class_id: int,
        class_name: str = 'cat'
    ):
        """
        初始化检测结果

        Args:
            bbox: 边界框 [x1, y1, x2, y2]
            confidence: 置信度
            class_id: 类别ID
            class_name: 类别名称
        """
        self.bbox = bbox
        self.confidence = confidence
        self.class_id = class_id
        self.class_name = class_name

    @property
    def center(self) -> Tuple[float, float]:
        """
        获取边界框中心点

        Returns:
            (x, y) 中心点坐标
        """
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @property
    def area(self) -> float:
        """
        获取边界框面积

        Returns:
            面积
        """
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)

    def to_dict(self) -> Dict:
        """
        转换为字典

        Returns:
            检测结果字典
        """
        return {
            'bbox': self.bbox,
            'confidence': self.confidence,
            'class_id': self.class_id,
            'class_name': self.class_name,
            'center': self.center,
            'area': self.area
        }

    def __repr__(self) -> str:
        """
        字符串表示
        """
        return f"Detection(class={self.class_name}, confidence={self.confidence:.2f}, bbox={self.bbox})"


class CatDetector:
    """
    猫检测器类

    使用YOLOv8进行猫的目标检测。

    Attributes:
        model: YOLO模型
        confidence_threshold: 置信度阈值
        iou_threshold: IOU阈值（NMS）
        target_class: 目标类别ID（COCO数据集中cat是15）
        input_size: 模型输入尺寸
        device: 运行设备
    """

    # COCO数据集类别
    COCO_CLASSES = {
        0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
        5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
        10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench',
        14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow'
    }

    def __init__(
        self,
        model_path: str = 'yolov8n.pt',
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        target_class: int = 15,
        input_size: int = 640,
        use_gpu: bool = True,
        half: bool = False  # FP16精度加速
    ):
        """
        初始化猫检测器

        Args:
            model_path: YOLO模型路径
            confidence_threshold: 置信度阈值
            iou_threshold: IOU阈值（NMS）
            target_class: 目标类别ID（COCO数据集中cat是15）
            input_size: 模型输入尺寸
            use_gpu: 是否使用GPU
            half: 是否使用FP16精度（GPU加速）
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.target_class = target_class
        self.input_size = input_size
        self.half = half and use_gpu  # 只有GPU才能使用half

        # 设置设备
        if use_gpu and torch.cuda.is_available():
            self.device = 'cuda'
        else:
            self.device = 'cpu'
            self.half = False  # CPU不支持half

        # 加载模型
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """
        加载YOLO模型
        """
        try:
            self.model = YOLO(self.model_path)
            # YOLO模型需要显式指定设备
            import torch
            if self.device == 'cuda':
                # 确保模型在GPU上
                self.model.to('cuda')
                print(f"✓ YOLO模型已加载到GPU: {torch.cuda.get_device_name(0)}")
            else:
                print(f"✓ YOLO模型已加载到CPU")
        except Exception as e:
            raise RuntimeError(f"加载模型失败: {e}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        检测帧中的猫

        Args:
            frame: 输入帧

        Returns:
            检测结果列表
        """
        if self.model is None:
            return []

        # 运行推理
        results = self.model(
            frame,
            imgsz=self.input_size,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            device=self.device,
            half=self.half,
            verbose=False
        )

        detections = []

        # 解析结果
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                # 获取类别ID
                class_id = int(box.cls[0])

                # 只保留猫的检测结果
                if class_id != self.target_class:
                    continue

                # 获取边界框
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])

                # 获取置信度
                confidence = float(box.conf[0])

                # 创建检测结果
                detection = Detection(
                    bbox=[x1, y1, x2, y2],
                    confidence=confidence,
                    class_id=class_id,
                    class_name=self.COCO_CLASSES.get(class_id, 'unknown')
                )
                detections.append(detection)

        return detections

    def detect_with_features(
        self,
        frame: np.ndarray
    ) -> Tuple[List[Detection], np.ndarray]:
        """
        检测猫并提取特征

        Args:
            frame: 输入帧

        Returns:
            (检测结果列表, 特征向量)
        """
        detections = self.detect(frame)
        features = self._extract_features(frame, detections)
        return detections, features

    def _extract_features(
        self,
        frame: np.ndarray,
        detections: List[Detection]
    ) -> np.ndarray:
        """
        从检测结果中提取特征

        Args:
            frame: 输入帧
            detections: 检测结果列表

        Returns:
            特征向量数组
        """
        features = []

        for detection in detections:
            # 获取边界框
            x1, y1, x2, y2 = [int(coord) for coord in detection.bbox]

            # 提取ROI
            roi = frame[y1:y2, x1:x2]

            if roi.size == 0:
                features.append(np.zeros(128))
                continue

            # 调整大小
            roi = cv2.resize(roi, (64, 64))

            # 提取简单的特征（这里使用像素值，实际可以使用更复杂的特征）
            feature = roi.flatten()
            features.append(feature)

        return np.array(features)

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Detection]
    ) -> np.ndarray:
        """
        在帧上绘制检测结果

        Args:
            frame: 输入帧
            detections: 检测结果列表

        Returns:
            绘制后的帧
        """
        frame_copy = frame.copy()

        for detection in detections:
            x1, y1, x2, y2 = [int(coord) for coord in detection.bbox]

            # 绘制边界框
            cv2.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # 绘制标签
            label = f"{detection.class_name}: {detection.confidence:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(
                frame_copy,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                (0, 255, 0),
                -1
            )
            cv2.putText(
                frame_copy,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                2
            )

        return frame_copy

    def set_confidence_threshold(self, threshold: float) -> None:
        """
        设置置信度阈值

        Args:
            threshold: 置信度阈值
        """
        self.confidence_threshold = max(0.0, min(1.0, threshold))

    def set_iou_threshold(self, threshold: float) -> None:
        """
        设置IOU阈值

        Args:
            threshold: IOU阈值
        """
        self.iou_threshold = max(0.0, min(1.0, threshold))

    def __repr__(self) -> str:
        """
        字符串表示
        """
        return f"CatDetector(model={self.model_path}, device={self.device})"
