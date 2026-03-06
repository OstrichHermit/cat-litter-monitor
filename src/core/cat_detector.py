"""
猫检测模块

该模块使用YOLOv8进行猫的目标检测，提供检测接口和结果封装。
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from ultralytics import YOLO
import torch
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            # 启用 cuDNN 优化
            torch.backends.cudnn.enabled = True
            torch.backends.cudnn.benchmark = True  # 固定输入尺寸时可加速
            logger.info("✓ GPU 优化已启用: cuDNN benchmark=True")
        else:
            self.device = 'cpu'
            self.half = False  # CPU不支持half
            logger.info("✓ 使用 CPU 模式")

        # CUDA Stream 用于异步处理（仅 GPU）
        self.cuda_stream = None
        if self.device == 'cuda':
            self.cuda_stream = torch.cuda.Stream()
            logger.info(f"✓ CUDA Stream 已创建")

        # 预分配 GPU 内存缓冲（仅 GPU）
        self.input_buffer = None
        if self.device == 'cuda' and self.input_size == 640:
            # 预分配输入张量 (3, 640, 640)
            self.input_buffer = torch.empty(
                (1, 3, self.input_size, self.input_size),
                dtype=torch.float32,
                device='cuda'
            )
            logger.info(f"✓ GPU 内存缓冲已预分配: {self.input_buffer.shape}")

        # 加载模型
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """
        加载YOLO模型
        """
        try:
            self.model = YOLO(self.model_path)

            if self.device == 'cuda':
                # 确保模型在GPU上
                self.model.to('cuda')
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                logger.info(f"✓ YOLO模型已加载到GPU: {gpu_name} ({gpu_memory:.2f}GB)")

                # 预热 GPU（第一次推理会慢，提前执行）
                logger.info("✓ 正在预热 GPU...")
                dummy_input = torch.zeros((1, 3, self.input_size, self.input_size), device='cuda')
                with torch.no_grad():
                    _ = self.model.predict(
                        source=dummy_input,
                        imgsz=self.input_size,
                        conf=0.25,
                        iou=0.45,
                        device='cuda',
                        half=self.half,
                        verbose=False
                    )
                torch.cuda.synchronize()  # 等待预热完成
                logger.info("✓ GPU 预热完成")
            else:
                logger.info("✓ YOLO模型已加载到CPU")

            # 打印 GPU 内存使用情况（仅 GPU）
            if self.device == 'cuda':
                self._print_gpu_memory()

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

        # 使用 CUDA Stream 进行异步推理（仅 GPU）
        if self.device == 'cuda' and self.cuda_stream is not None:
            with torch.cuda.stream(self.cuda_stream):
                results = self._inference(frame)
            # 等待 CUDA 操作完成
            torch.cuda.synchronize()
        else:
            results = self._inference(frame)

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

                # 获取边界框（已在 GPU 上，直接转换）
                xyxy = box.xyxy[0]
                if self.device == 'cuda':
                    # GPU 模式：先移到 CPU 再转换
                    xyxy = xyxy.cpu().numpy()
                else:
                    xyxy = xyxy.numpy()

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

    def _inference(self, frame: np.ndarray):
        """
        执行推理

        Args:
            frame: 输入帧

        Returns:
            推理结果
        """
        return self.model(
            frame,
            imgsz=self.input_size,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            device=self.device,
            half=self.half,
            verbose=False
        )

    def _print_gpu_memory(self) -> None:
        """
        打印 GPU 内存使用情况
        """
        if self.device != 'cuda':
            return

        allocated = torch.cuda.memory_allocated() / 1024**2  # MB
        reserved = torch.cuda.memory_reserved() / 1024**2  # MB
        total = torch.cuda.get_device_properties(0).total_memory / 1024**2  # MB

        logger.info(
            f"📊 GPU 内存使用: {allocated:.2f}MB 已分配 / "
            f"{reserved:.2f}MB 已保留 / {total:.2f}MB 总计 "
            f"({allocated/total*100:.1f}%)"
        )

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

    def get_gpu_memory_info(self) -> Dict[str, float]:
        """
        获取 GPU 内存使用信息

        Returns:
            包含 GPU 内存信息的字典
        """
        if self.device != 'cuda':
            return {
                'allocated_mb': 0,
                'reserved_mb': 0,
                'total_mb': 0,
                'usage_percent': 0
            }

        allocated = torch.cuda.memory_allocated() / 1024**2
        reserved = torch.cuda.memory_reserved() / 1024**2
        total = torch.cuda.get_device_properties(0).total_memory / 1024**2

        return {
            'allocated_mb': allocated,
            'reserved_mb': reserved,
            'total_mb': total,
            'usage_percent': (allocated / total) * 100
        }

    def cleanup_gpu_memory(self) -> None:
        """
        清理 GPU 缓存内存

        当检测到 GPU 内存不足时，可以调用此方法释放缓存
        """
        if self.device == 'cuda':
            torch.cuda.empty_cache()
            logger.info("✓ GPU 缓存已清理")
            self._print_gpu_memory()
