"""
模型训练脚本

该脚本用于训练猫的个体识别分类器。
"""

import sys
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
import numpy as np

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.cat_classifier import CatClassifier
from src.config import get_config
from src.utils.logger import get_logger


class CatDataset(Dataset):
    """
    猫数据集类
    """

    def __init__(self, data_dir, transform=None):
        """
        初始化数据集

        Args:
            data_dir: 数据目录
            transform: 数据变换
        """
        self.data_dir = Path(data_dir)
        self.transform = transform

        # 加载数据
        self.samples = []
        self.classes = []

        # 获取所有类别
        for class_dir in sorted(self.data_dir.iterdir()):
            if class_dir.is_dir():
                class_name = class_dir.name
                self.classes.append(class_name)

                # 加载该类别的所有图片
                for img_path in class_dir.glob('*.jpg'):
                    self.samples.append((str(img_path), self.classes.index(class_name)))

        self.logger = get_logger()
        self.logger.info(f"加载数据集: {len(self.samples)} 张图片, {len(self.classes)} 个类别")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        """
        获取样本

        Args:
            idx: 索引

        Returns:
            (图片, 类别ID)
        """
        img_path, class_id = self.samples[idx]

        # 加载图片
        image = Image.open(img_path).convert('RGB')

        if self.transform:
            image = self.transform(image)

        return image, class_id


def train_classifier(
    data_dir,
    model_type='mobilenet',
    num_epochs=50,
    batch_size=8,
    learning_rate=0.001,
    output_path='data/models/cat_classifier.pth'
):
    """
    训练分类器

    Args:
        data_dir: 数据目录
        model_type: 模型类型
        num_epochs: 训练轮数
        batch_size: 批处理大小
        learning_rate: 学习率
        output_path: 模型保存路径
    """
    logger = get_logger()
    logger.info("开始训练分类器...")

    # 检查GPU
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"使用设备: {device}")

    # 数据变换
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    # 加载数据集
    dataset = CatDataset(data_dir, transform=transform)

    if len(dataset) == 0:
        logger.error("数据集为空，请先收集数据")
        return

    # 划分训练集和验证集
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

    # 创建数据加载器
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    logger.info(f"训练集: {len(train_dataset)}, 验证集: {len(val_dataset)}")

    # 创建模型
    model = CatClassifier(
        model_type=model_type,
        num_classes=len(dataset.classes),
        pretrained=True
    )
    model = model.to(device)

    # 损失函数和优化器
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.1)

    # 训练循环
    best_val_acc = 0.0

    for epoch in range(num_epochs):
        # 训练阶段
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)

            # 前向传播
            outputs = model(images)
            loss = criterion(outputs, labels)

            # 反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            # 统计
            train_loss += loss.item()
            _, predicted = outputs.max(1)
            train_total += labels.size(0)
            train_correct += predicted.eq(labels).sum().item()

        train_loss = train_loss / len(train_loader)
        train_acc = 100. * train_correct / train_total

        # 验证阶段
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)

                outputs = model(images)
                loss = criterion(outputs, labels)

                val_loss += loss.item()
                _, predicted = outputs.max(1)
                val_total += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()

        val_loss = val_loss / len(val_loader)
        val_acc = 100. * val_correct / val_total

        # 更新学习率
        scheduler.step()

        # 打印进度
        logger.info(
            f"Epoch [{epoch+1}/{num_epochs}] "
            f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.2f}% | "
            f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.2f}%"
        )

        # 保存最佳模型
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_acc': val_acc,
                'model_type': model_type,
                'num_classes': len(dataset.classes),
                'class_names': dataset.classes
            }, output_path)

            logger.info(f"保存最佳模型: {output_path} (验证准确率: {val_acc:.2f}%)")

    logger.info(f"训练完成! 最佳验证准确率: {best_val_acc:.2f}%")


def main():
    """
    主函数
    """
    import argparse

    parser = argparse.ArgumentParser(description='训练猫分类器')
    parser.add_argument(
        '--data-dir',
        type=str,
        default='data/raw/training',
        help='训练数据目录'
    )
    parser.add_argument(
        '--model-type',
        type=str,
        default='mobilenet',
        choices=['mobilenet', 'resnet', 'efficientnet'],
        help='模型类型'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=50,
        help='训练轮数'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=8,
        help='批处理大小'
    )
    parser.add_argument(
        '--lr',
        type=float,
        default=0.001,
        help='学习率'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/models/cat_classifier.pth',
        help='模型输出路径'
    )

    args = parser.parse_args()

    # 训练分类器
    train_classifier(
        data_dir=args.data_dir,
        model_type=args.model_type,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        output_path=args.output
    )


if __name__ == '__main__':
    main()
