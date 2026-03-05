# 快速开始指南

## 环境要求

- Python 3.10+
- 摄像头（USB摄像头或网络摄像头）
- 4GB+ RAM（推荐使用GPU）

## 5分钟快速启动

### 1. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 下载YOLOv8模型

```python
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
mkdir -p data/models
mv yolov8n.pt data/models/
```

### 3. 基本配置

编辑 `config/default.yaml`，修改以下参数：

```yaml
camera:
  type: usb        # 或 rtsp
  device_id: 0     # 摄像头设备号

cats:
  - "小白"         # 修改为你的猫的名字
  - "小黑"
  - "小花"
  - "小灰"
```

### 4. 启动系统（测试模式）

```bash
python src/main.py --config config/default.yaml
```

系统将在以下地址可用：
- Web界面: http://localhost:5000
- 视频流: http://localhost:5000/video_feed

## 完整部署流程

### 第1步：标注ROI区域

运行ROI标注工具，标记猫砂盆位置：

```bash
python scripts/annotate_roi.py --camera-id 0
```

**操作说明**：
- 按 `r` 切换到矩形模式
- 鼠标左键拖动绘制矩形
- 按 `s` 保存配置
- 按 `q` 退出

### 第2步：收集训练数据

为每只猫收集训练图片（每只猫至少100张）：

```bash
python scripts/collect_data.py
```

**操作说明**：
- 按 `1-4` 选择当前标注的猫
- 按 `空格键` 保存当前帧
- 按 `q` 退出

**提示**：
- 从不同角度拍摄
- 不同光照条件
- 确保猫的脸部清晰可见

### 第3步：训练分类器

```bash
python scripts/train_classifier.py \
    --data-dir data/raw/training \
    --model-type mobilenet \
    --epochs 50 \
    --batch-size 8
```

**训练时间**：
- CPU: 约30-60分钟
- GPU: 约5-10分钟

### 第4步：启动系统

```bash
# Windows
run.bat

# Linux/Mac
./run.sh

# 或直接运行
python src/main.py
```

### 第5步：访问Web界面

打开浏览器访问：http://localhost:5000

你将看到：
- 实时视频流
- 检测结果和追踪ID
- 今日统计数据
- 最近事件列表

## 常见问题解决

### 问题1：摄像头无法打开

**解决方案**：
1. 检查摄像头是否被其他程序占用
2. 尝试不同的device_id（0, 1, 2...）
3. 如果是USB摄像头，确保驱动已安装

### 问题2：检测不到猫

**解决方案**：
1. 降低置信度阈值：`confidence_threshold: 0.3`
2. 确保光线充足
3. 调整摄像头角度，避免遮挡

### 问题3：分类器识别错误

**解决方案**：
1. 收集更多训练数据
2. 确保数据质量（清晰、多样）
3. 增加训练轮数：`--epochs 100`
4. 尝试更大的模型：`--model-type resnet`

### 问题4：系统占用资源过高

**解决方案**：
1. 跳帧处理：`process_every_n_frames: 3`
2. 使用更小的模型：`yolov8n.pt`
3. 降低分辨率：`width: 640, height: 480`
4. 禁用GPU：`use_gpu: false`

## 配置优化建议

### 实时性优先

```yaml
system:
  process_every_n_frames: 1

detection:
  input_size: 320  # 降低输入尺寸

tracking:
  max_disappeared: 10  # 快速丢失追踪
```

### 准确性优先

```yaml
system:
  process_every_n_frames: 1

detection:
  confidence_threshold: 0.7
  input_size: 640

tracking:
  max_disappeared: 50
```

### 资源受限

```yaml
system:
  process_every_n_frames: 3

detection:
  confidence_threshold: 0.4
  input_size: 320

classifier:
  model_type: mobilenet  # 使用轻量级模型
```

## 维护建议

### 定期任务

1. **每周**：检查日志文件大小
2. **每月**：清理旧的事件记录
3. **每季度**：重新训练分类器（如果有新猫）

### 数据备份

```bash
# 备份数据库
cp data/litter_monitor.db data/litter_monitor.db.backup

# 备份训练数据
tar -czf training_data_backup.tar.gz data/raw/training/
```

### 性能监控

查看系统资源使用：

```bash
# 查看数据库大小
ls -lh data/litter_monitor.db

# 查看日志
tail -f logs/litter_monitor.log

# 查看事件数量
sqlite3 data/litter_monitor.db "SELECT COUNT(*) FROM litter_events;"
```

## 下一步

- 查看 [README.md](README.md) 了解详细信息
- 查看 [PROJECT_PLAN.md](PROJECT_PLAN.md) 了解技术细节
- 提交Issue报告问题或建议

祝你使用愉快！
