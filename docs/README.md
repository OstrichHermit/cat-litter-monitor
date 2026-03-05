# 猫厕所监控系统

一个基于计算机视觉的猫厕所监控系统，能够识别个体猫并记录每只猫上厕所的次数和时间。

## 功能特性

- **个体识别**：区分4只不同的猫
- **行为识别**：使用位置法检测猫是否进入猫砂盆区域
- **数据统计**：记录每只猫每天的上厕所次数和时间
- **Web界面**：实时视频流和统计数据展示
- **深度学习**：基于YOLOv8的目标检测和迁移学习分类器

## 系统架构

```
猫厕所监控系统
├── 视频采集模块 (camera.py)
├── 猫检测模块 (cat_detector.py) - YOLOv8
├── 目标追踪模块 (object_tracker.py) - DeepSORT
├── 个体识别模块 (cat_classifier.py) - 迁移学习
├── 行为分析模块 (behavior_analyzer.py) - ROI位置法
├── 数据存储模块 (database.py) - SQLite
└── Web界面模块 (app.py) - Flask
```

## 技术栈

- **编程语言**：Python 3.10+
- **目标检测**：YOLOv8 (Ultralytics)
- **目标追踪**：DeepSORT
- **个体识别**：迁移学习分类器（MobileNet/ResNet/EfficientNet）
- **行为分析**：位置法（ROI区域判断）
- **数据库**：SQLite
- **Web框架**：Flask + Flask-SocketIO

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd cat-litter-monitor
```

### 2. 运行安装脚本

```bash
bash scripts/setup.sh
```

或手动安装：

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 下载YOLOv8模型
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
mkdir -p data/models
mv yolov8n.pt data/models/
```

### 3. 配置系统

编辑配置文件 `config/default.yaml`，根据实际情况修改：

```yaml
camera:
  type: usb  # 或 rtsp
  device_id: 0
  width: 1280
  height: 720

roi:
  type: rectangle
  rectangle:
    x: 100
    y: 100
    width: 300
    height: 300

cats:
  - "猫猫1号"
  - "猫猫2号"
  - "猫猫3号"
  - "猫猫4号"
```

## 使用指南

### 1. 标注ROI区域

运行ROI标注工具，标注猫砂盆区域：

```bash
python scripts/annotate_roi.py --camera-id 0
```

**操作说明**：
- 按 `r` 切换到矩形模式
- 按 `p` 切换到多边形模式
- 鼠标左键绘制ROI
- 按 `s` 保存配置
- 按 `q` 退出

### 2. 收集训练数据

运行数据收集脚本，为每只猫收集训练图片：

```bash
python scripts/collect_data.py
```

**操作说明**：
- 按 `1-4` 选择当前标注的猫
- 按 `空格` 保存当前帧
- 按 `q` 退出

**建议**：每只猫收集至少100张图片，涵盖不同角度和光照条件。

### 3. 训练分类器

使用收集的数据训练猫的个体识别分类器：

```bash
python scripts/train_classifier.py \
    --data-dir data/raw/training \
    --model-type mobilenet \
    --epochs 50 \
    --batch-size 8
```

**参数说明**：
- `--data-dir`: 训练数据目录
- `--model-type`: 模型类型（mobilenet/resnet/efficientnet）
- `--epochs`: 训练轮数
- `--batch-size`: 批处理大小
- `--lr`: 学习率（默认0.001）

### 4. 启动系统

```bash
python src/main.py
```

系统将启动：
- **常驻监控窗口**：显示实时处理画面（关闭窗口自动退出程序）
- 视频监控和处理
- Web界面（http://localhost:5000）
- 数据记录和统计

**窗口控制**：
- 窗口会始终显示处理后的监控画面
- 按 `q` 键或点击窗口的关闭按钮（X）可退出程序

## Web界面

访问 `http://localhost:5000` 查看：

- **实时视频流**：显示检测结果、追踪ID和ROI区域
- **系统状态**：运行状态指示
- **今日统计**：每只猫的上厕所次数和平均时长
- **最近事件**：最近的如厕事件列表

## 配置说明

### 摄像头配置

支持三种摄像头类型：

```yaml
camera:
  type: usb  # usb、rtsp 或 go2rtc
  device_id: 0  # USB摄像头设备号
  rtsp_url: ""  # RTSP流地址
  width: 1280
  height: 720
  fps: 30

# go2rtc配置（当type=go2rtc时使用）
go2rtc:
  host: "localhost"
  camera_name: "xiaomi_cam"
  use_webrtc: false
```

**支持的摄像头类型**：
- `usb`: USB摄像头
- `rtsp`: RTSP网络摄像头
- `go2rtc`: 通过go2rtc流媒体服务器（推荐用于小米摄像头4）

> 💡 **推荐使用go2rtc**：go2rtc提供更好的稳定性和多摄像头管理能力。详见 [go2rtc配置指南](docs/GO2RTC_SETUP.md)

### ROI配置

```yaml
roi:
  type: rectangle  # rectangle 或 polygon
  rectangle:
    x: 100
    y: 100
    width: 300
    height: 300
  polygon:  # 多边形顶点
    - [100, 100]
    - [400, 100]
    - [400, 400]
    - [100, 400]
```

### 行为分析配置

```yaml
behavior:
  min_duration: 5  # 最小持续时间（秒）
  min_interval: 30  # 两次事件最小间隔（秒）
```

## 项目结构

```
cat-litter-monitor/
├── config/
│   └── default.yaml          # 配置文件
├── data/
│   ├── models/               # 模型文件
│   ├── raw/                  # 原始数据
│   │   ├── training/         # 训练数据
│   │   └── events/           # 事件视频片段
│   └── processed/            # 处理后的数据
├── logs/                     # 日志文件
├── scripts/                  # 工具脚本
│   ├── collect_data.py       # 数据收集
│   ├── train_classifier.py   # 模型训练
│   ├── annotate_roi.py       # ROI标注
│   └── setup.sh              # 安装脚本
├── src/
│   ├── core/                 # 核心模块
│   │   ├── camera.py         # 视频采集
│   │   ├── cat_detector.py   # 猫检测
│   │   ├── object_tracker.py # 目标追踪
│   │   ├── cat_classifier.py # 个体识别
│   │   └── behavior_analyzer.py # 行为分析
│   ├── storage/              # 存储模块
│   │   └── database.py       # 数据库
│   ├── utils/                # 工具模块
│   │   └── logger.py         # 日志
│   ├── web/                  # Web模块
│   │   ├── app.py            # Flask应用
│   │   ├── templates/        # HTML模板
│   │   └── static/           # 静态文件
│   ├── config.py             # 配置管理
│   └── main.py               # 主程序
├── tests/                    # 测试文件
├── requirements.txt          # 依赖清单
└── README.md                 # 项目文档
```

## 工作原理

1. **视频采集**：从USB摄像头或RTSP流获取视频帧
2. **目标检测**：使用YOLOv8检测猫的位置
3. **目标追踪**：使用DeepSORT为每只猫分配唯一的追踪ID
4. **个体识别**：使用训练好的分类器识别是哪只猫
5. **行为分析**：判断猫是否进入ROI区域（猫砂盆）
6. **事件记录**：记录进入和离开时间，计算持续时间
7. **数据存储**：将事件保存到SQLite数据库
8. **Web展示**：通过Flask提供实时视频和统计数据

## 常见问题

### Q: 检测不到猫？

A: 检查以下几点：
1. 确认YOLOv8模型文件存在于 `data/models/yolov8n.pt`
2. 调整 `confidence_threshold` 参数（降低阈值）
3. 确保摄像头画面清晰，光照充足

### Q: 追踪ID频繁变化？

A: 可能的原因：
1. 猫移动速度过快
2. 检测置信度不稳定
3. 遮挡严重

解决方法：
1. 增加帧率
2. 调整 `max_disappeared` 参数
3. 改善摄像头角度

### Q: 个体识别不准确？

A: 改进方法：
1. 收集更多训练数据（每只猫至少100张）
2. 确保训练数据涵盖不同角度和光照
3. 增加训练轮数
4. 尝试不同的模型类型

## 依赖项

- numpy>=1.24.0
- opencv-python>=4.8.0
- Pillow>=10.0.0
- torch>=2.0.0
- torchvision>=0.15.0
- ultralytics>=8.0.0
- filterpy>=1.4.5
- scikit-learn>=1.3.0
- pandas>=2.0.0
- sqlalchemy>=2.0.0
- flask>=3.0.0
- flask-cors>=4.0.0
- flask-socketio>=5.3.0
- pyyaml>=6.0
- colorlog>=6.7.0

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

如有问题，请提交Issue。
