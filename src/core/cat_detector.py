"""
猫检测模块（onnxruntime CPU 推理）

该模块使用 onnxruntime 加载 ONNX 格式的 YOLO 模型进行猫的目标检测，
纯 CPU 推理，无 torch/ultralytics 依赖，提供检测接口和结果封装。

模型约定（YOLO26 端到端导出）：
- 输入: (1, 3, S, S) float32 NCHW，RGB 通道，/255 归一化
  （整帧或检测区域 letterbox 到 S×S，114 灰底居中）
- 输出: (1, 300, 6)，每行 [x1, y1, x2, y2, conf, cls]
  坐标为相对 S×S letterbox 输入的像素坐标，cls 为 COCO 类别 id（15=cat）
- YOLO26 架构端到端输出，自带 top-k 筛选，后处理无需 NMS，
  只需按置信度和类别过滤
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
import onnxruntime as ort
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
    猫检测器类（onnxruntime CPU 推理）

    使用 onnxruntime 加载 ONNX 格式的 YOLO 模型进行猫的目标检测。

    Attributes:
        model_path: ONNX模型路径
        confidence_threshold: 置信度阈值
        iou_threshold: IOU阈值（兼容保留，端到端模型无NMS，不再使用）
        target_class: 目标类别ID（COCO数据集中cat是15）
        input_size: 模型输入尺寸
        detect_region: 检测区域 (x1, y1, x2, y2)，仅在该区域内检测，None 表示整帧
        session: onnxruntime InferenceSession
        input_name: 模型输入节点名
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
        model_path: str = 'yolo26n.onnx',
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        target_class: int = 15,
        input_size: int = 640,
        use_gpu: bool = True,
        half: bool = False,
        detect_region: Optional[Tuple[int, int, int, int]] = None
    ):
        """
        初始化猫检测器

        Args:
            model_path: ONNX模型路径
            confidence_threshold: 置信度阈值
            iou_threshold: IOU阈值（兼容保留参数，端到端模型无NMS，不再使用）
            target_class: 目标类别ID（COCO数据集中cat是15）
            input_size: 模型输入尺寸
            use_gpu: 兼容保留参数，onnxruntime 纯 CPU 推理，不再使用
            half: 兼容保留参数，CPU 推理使用 float32，不再使用
            detect_region: 检测区域 (x1, y1, x2, y2)，None 表示整帧检测
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold  # 兼容保留：端到端模型无 NMS，不使用
        self.target_class = target_class
        self.input_size = input_size
        self.use_gpu = use_gpu              # 兼容保留：纯 CPU 推理，不使用
        self.half = half                    # 兼容保留：CPU 推理使用 float32，不使用
        self.detect_region = detect_region

        # 加载模型
        self.session = None
        self.input_name = None
        self._load_model()

    def _load_model(self) -> None:
        """
        加载 ONNX 模型（CPU 推理）
        """
        try:
            # 小模型小图：限制线程数，避免默认线程池（=物理核数）自旋空转烧 CPU
            so = ort.SessionOptions()
            so.intra_op_num_threads = 2
            so.inter_op_num_threads = 1
            self.session = ort.InferenceSession(
                self.model_path,
                sess_options=so,
                providers=['CPUExecutionProvider']
            )
            self.input_name = self.session.get_inputs()[0].name
            input_shape = self.session.get_inputs()[0].shape
            output_shape = self.session.get_outputs()[0].shape
            logger.info(f"✓ ONNX 模型已加载（CPU 推理）: {self.model_path}")
            logger.info(f"✓ 模型输入: {self.input_name} {input_shape}, 输出: {output_shape}")
        except Exception as e:
            raise RuntimeError(f"加载模型失败: {e}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        检测帧中的猫

        若设置了 detect_region，则仅在该区域内检测（裁剪后 letterbox 推理，
        结果坐标映射回全帧坐标系）；否则整帧检测。

        Args:
            frame: 输入帧（BGR 格式）

        Returns:
            检测结果列表（坐标为全帧坐标系）
        """
        if self.session is None:
            return []

        frame_h, frame_w = frame.shape[:2]

        # 1. 裁剪检测区域（或使用整帧），记录偏移量
        crop_x_offset = 0
        crop_y_offset = 0
        if self.detect_region is not None:
            rx1, ry1, rx2, ry2 = self.detect_region
            # clamp 到帧边界
            x1 = max(0, min(int(rx1), frame_w - 1))
            y1 = max(0, min(int(ry1), frame_h - 1))
            x2 = max(x1 + 1, min(int(rx2), frame_w))
            y2 = max(y1 + 1, min(int(ry2), frame_h))
            region = frame[y1:y2, x1:x2]
            crop_x_offset = x1
            crop_y_offset = y1
        else:
            region = frame

        region_h, region_w = region.shape[:2]

        # 2. letterbox 到 input_size（保持宽高比，114 灰底居中）
        scale = min(self.input_size / region_w, self.input_size / region_h)
        new_w = int(round(region_w * scale))
        new_h = int(round(region_h * scale))
        resized = cv2.resize(region, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        canvas = np.full(
            (self.input_size, self.input_size, 3),
            114,
            dtype=np.uint8
        )
        left = (self.input_size - new_w) // 2
        top = (self.input_size - new_h) // 2
        canvas[top:top + new_h, left:left + new_w] = resized

        # BGR->RGB，HWC->CHW，/255 归一化，float32，加 batch 维
        blob = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = blob[np.newaxis, ...]

        # 3. 推理，输出 (1, 300, 6)
        outputs = self.session.run(None, {self.input_name: blob})
        predictions = outputs[0][0]

        # 4. 过滤 + 5. 坐标映射回全帧坐标系 + 6. 组装结果
        detections = []
        for pred in predictions:
            box_x1, box_y1, box_x2, box_y2, conf, cls = pred
            confidence = float(conf)
            class_id = int(cls)

            # 置信度和类别过滤（端到端模型无需 NMS）
            if confidence < self.confidence_threshold:
                continue
            if class_id != self.target_class:
                continue

            # letterbox 坐标 -> 裁剪区域坐标 -> 全帧坐标
            fx1 = (float(box_x1) - left) / scale + crop_x_offset
            fy1 = (float(box_y1) - top) / scale + crop_y_offset
            fx2 = (float(box_x2) - left) / scale + crop_x_offset
            fy2 = (float(box_y2) - top) / scale + crop_y_offset

            detections.append(Detection(
                bbox=[fx1, fy1, fx2, fy2],
                confidence=confidence,
                class_id=class_id,
                class_name=self.COCO_CLASSES.get(class_id, 'unknown')
            ))

        return detections

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
        return (
            f"CatDetector(model={self.model_path}, provider=CPUExecutionProvider, "
            f"input_size={self.input_size}, detect_region={self.detect_region})"
        )
