"""
个体识别模块

该模块使用深度学习分类器识别不同的猫，支持迁移学习和数据收集。
"""

import cv2
import numpy as np
import torch
import torch.nn as nn
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class CatClassifier(nn.Module):
    """
    猫分类器模型类

    基于迁移学习的猫个体识别模型。

    Attributes:
        model_type: 模型类型
        num_classes: 类别数量
        input_size: 输入尺寸
        feature_extractor: 特征提取器
        classifier: 分类器
    """

    def __init__(
        self,
        model_type: str = 'mobilenet',
        num_classes: int = 4,
        input_size: int = 224,
        pretrained: bool = True
    ):
        """
        初始化分类器

        Args:
            model_type: 模型类型（'resnet', 'mobilenet', 'efficientnet'）
            num_classes: 类别数量
            input_size: 输入尺寸
            pretrained: 是否使用预训练权重
        """
        super(CatClassifier, self).__init__()

        self.model_type = model_type
        self.num_classes = num_classes
        self.input_size = input_size

        # 创建特征提取器
        if model_type == 'mobilenet':
            from torchvision.models import mobilenet_v3_small
            backbone = mobilenet_v3_small(pretrained=pretrained)
            self.feature_extractor = nn.Sequential(*list(backbone.children())[:-1])
            num_features = 576
        elif model_type == 'resnet':
            from torchvision.models import resnet18
            backbone = resnet18(pretrained=pretrained)
            self.feature_extractor = nn.Sequential(*list(backbone.children())[:-1])
            num_features = 512
        elif model_type == 'efficientnet':
            from torchvision.models import efficientnet_v2_s
            backbone = efficientnet_v2_s(pretrained=pretrained)
            self.feature_extractor = nn.Sequential(*list(backbone.children())[:-1])
            num_features = 1280
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")

        # 创建分类器
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.2),
            nn.Linear(num_features, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_classes)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播

        Args:
            x: 输入张量 [batch_size, 3, H, W]

        Returns:
            输出张量 [batch_size, num_classes]
        """
        features = self.feature_extractor(x)
        output = self.classifier(features)
        return output


class CatIdentifier:
    """
    猫个体识别器类

    负责加载和使用分类器模型进行猫的个体识别。

    Attributes:
        model: 分类器模型
        device: 运行设备
        input_size: 输入尺寸
        class_names: 类别名称列表
        confidence_threshold: 置信度阈值
    """

    def __init__(
        self,
        model_path: str,
        num_classes: int = 4,
        class_names: Optional[List[str]] = None,
        input_size: int = 224,
        confidence_threshold: float = 0.5,
        use_gpu: bool = True
    ):
        """
        初始化猫个体识别器

        Args:
            model_path: 模型文件路径
            num_classes: 类别数量
            class_names: 类别名称列表
            input_size: 输入尺寸
            confidence_threshold: 置信度阈值
            use_gpu: 是否使用GPU
        """
        self.model_path = model_path
        self.num_classes = num_classes
        self.input_size = input_size
        self.confidence_threshold = confidence_threshold

        # 设置设备
        if use_gpu and torch.cuda.is_available():
            self.device = torch.device('cuda')
        else:
            self.device = torch.device('cpu')

        # 设置类别名称
        if class_names is None:
            self.class_names = [f"猫{i+1}号" for i in range(num_classes)]
        else:
            self.class_names = class_names

        # 加载模型
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """
        加载模型
        """
        model_path = Path(self.model_path)

        if not model_path.exists():
            # 模型不存在，创建新模型
            self.model = CatClassifier(
                model_type='mobilenet',
                num_classes=self.num_classes,
                input_size=self.input_size
            )
            self.model.to(self.device)
            return

        try:
            # 加载模型权重
            checkpoint = torch.load(model_path, map_location=self.device)

            # 创建模型
            model_type = checkpoint.get('model_type', 'mobilenet')
            self.model = CatClassifier(
                model_type=model_type,
                num_classes=checkpoint.get('num_classes', self.num_classes),
                input_size=self.input_size
            )

            # 加载权重
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.to(self.device)
            self.model.eval()

        except Exception as e:
            raise RuntimeError(f"加载模型失败: {e}")

    def preprocess(self, image: np.ndarray) -> torch.Tensor:
        """
        预处理图像

        Args:
            image: 输入图像 (BGR格式)

        Returns:
            预处理后的张量 [1, 3, H, W]
        """
        # 转换为RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # 调整大小
        image_resized = cv2.resize(image_rgb, (self.input_size, self.input_size))

        # 归一化
        image_normalized = image_resized.astype(np.float32) / 255.0

        # 转换为张量
        image_tensor = torch.from_numpy(image_normalized).permute(2, 0, 1).unsqueeze(0)

        return image_tensor.to(self.device)

    def predict(self, image: np.ndarray) -> Dict:
        """
        预测图像中的猫

        Args:
            image: 输入图像 (BGR格式)

        Returns:
            预测结果字典：
            {
                'class_id': 类别ID,
                'class_name': 类别名称,
                'confidence': 置信度,
                'probabilities': 所有类别的概率
            }
        """
        if self.model is None:
            return {
                'class_id': -1,
                'class_name': '未知',
                'confidence': 0.0,
                'probabilities': [0.0] * self.num_classes
            }

        # 预处理
        input_tensor = self.preprocess(image)

        # 推理
        with torch.no_grad():
            output = self.model(input_tensor)
            probabilities = torch.softmax(output, dim=1)[0]

        # 获取预测结果
        confidence, class_id = torch.max(probabilities, 0)
        class_id = class_id.item()
        confidence = confidence.item()

        # 转换为numpy
        probabilities = probabilities.cpu().numpy()

        return {
            'class_id': class_id,
            'class_name': self.class_names[class_id] if class_id < len(self.class_names) else '未知',
            'confidence': confidence,
            'probabilities': probabilities.tolist()
        }

    def predict_batch(self, images: List[np.ndarray]) -> List[Dict]:
        """
        批量预测

        Args:
            images: 图像列表

        Returns:
            预测结果列表
        """
        results = []

        for image in images:
            result = self.predict(image)
            results.append(result)

        return results

    def is_trained(self) -> bool:
        """
        检查模型是否已训练

        Returns:
            是否已训练
        """
        model_path = Path(self.model_path)
        return model_path.exists()

    def get_class_names(self) -> List[str]:
        """
        获取类别名称列表

        Returns:
            类别名称列表
        """
        return self.class_names.copy()

    def set_class_names(self, class_names: List[str]) -> None:
        """
        设置类别名称

        Args:
            class_names: 类别名称列表
        """
        if len(class_names) != self.num_classes:
            raise ValueError(f"类别名称数量({len(class_names)})与模型类别数({self.num_classes})不匹配")

        self.class_names = class_names


class DataCollector:
    """
    数据收集器类

    用于收集猫的训练数据。

    Attributes:
        save_dir: 保存目录
        class_names: 类别名称列表
        current_class: 当前类别
        frame_count: 帧计数
    """

    def __init__(
        self,
        save_dir: str = 'data/raw/training',
        class_names: Optional[List[str]] = None
    ):
        """
        初始化数据收集器

        Args:
            save_dir: 保存目录
            class_names: 类别名称列表
        """
        self.save_dir = Path(save_dir)
        self.class_names = class_names or ['猫1号', '猫2号', '猫3号', '猫4号']
        self.current_class = 0
        self.frame_count = {name: 0 for name in self.class_names}

        # 创建目录
        for class_name in self.class_names:
            class_dir = self.save_dir / class_name
            class_dir.mkdir(parents=True, exist_ok=True)

    def collect(
        self,
        image: np.ndarray,
        class_id: int,
        bbox: Optional[List[int]] = None
    ) -> str:
        """
        收集数据

        Args:
            image: 输入图像
            class_id: 类别ID
            bbox: 边界框 [x1, y1, x2, y2]，如果提供则裁剪

        Returns:
            保存的文件路径
        """
        if class_id >= len(self.class_names):
            raise ValueError(f"类别ID {class_id} 超出范围")

        class_name = self.class_names[class_id]

        # 裁剪ROI
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            image = image[y1:y2, x1:x2]

        # 生成文件名
        self.frame_count[class_name] += 1
        filename = f"{class_name}_{self.frame_count[class_name]:06d}.jpg"
        filepath = self.save_dir / class_name / filename

        # 保存图像
        cv2.imwrite(str(filepath), image)

        return str(filepath)

    def get_class_dirs(self) -> Dict[str, str]:
        """
        获取各类别的数据目录

        Returns:
            类别名到目录路径的映射
        """
        return {
            class_name: str(self.save_dir / class_name)
            for class_name in self.class_names
        }

    def get_sample_count(self, class_name: Optional[str] = None) -> Dict[str, int]:
        """
        获取样本数量

        Args:
            class_name: 类别名称，如果为None则返回所有类别的数量

        Returns:
            类别到样本数量的映射
        """
        if class_name is not None:
            return {class_name: self.frame_count.get(class_name, 0)}
        return self.frame_count.copy()

    def reset(self) -> None:
        """
        重置计数器
        """
        self.frame_count = {name: 0 for name in self.class_names}
