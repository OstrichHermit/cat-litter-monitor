#!/bin/bash

# 猫厕所监控系统 - 安装脚本

echo "================================"
echo "猫厕所监控系统 - 安装"
echo "================================"

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "检测到Python版本: $python_version"

# 创建虚拟环境（可选）
read -p "是否创建虚拟环境? (y/n): " create_venv
if [ "$create_venv" = "y" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
    echo "激活虚拟环境..."
    source venv/bin/activate
fi

# 升级pip
echo "升级pip..."
pip install --upgrade pip

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 下载YOLOv8模型
echo "下载YOLOv8模型..."
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# 移动模型到正确位置
mkdir -p data/models
mv yolov8n.pt data/models/ 2>/dev/null || echo "模型已存在或下载失败"

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p data/models
mkdir -p data/raw/training
mkdir -p data/raw/events
mkdir -p data/processed
mkdir -p logs
mkdir -p src/web/templates
mkdir -p src/web/static

# 设置权限
chmod +x scripts/*.sh

echo ""
echo "================================"
echo "安装完成!"
echo "================================"
echo ""
echo "下一步:"
echo "1. 编辑配置文件: config/default.yaml"
echo "2. 运行ROI标注工具: python scripts/annotate_roi.py"
echo "3. 收集训练数据: python scripts/collect_data.py"
echo "4. 训练分类器: python scripts/train_classifier.py"
echo "5. 启动系统: python src/main.py"
echo ""
echo "Web界面将在 http://localhost:5000 可用"
