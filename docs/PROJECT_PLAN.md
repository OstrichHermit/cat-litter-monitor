# 猫厕所监控系统 - 项目规划文档

## 项目概述

### 项目目标
开发一个基于计算机视觉的猫厕所监控系统，能够：
1. 识别并区分4只不同的猫
2. 检测猫是否进入猫砂盆区域
3. 记录每只猫每天的上厕所次数和时间
4. 提供Web界面实时查看监控和统计数据

### 技术方案
- **编程语言**: Python 3.10+
- **目标检测**: YOLOv8 (Ultralytics)
- **目标追踪**: DeepSORT
- **个体识别**: 迁移学习分类器（MobileNet/ResNet）
- **行为分析**: 位置法（ROI区域判断）
- **数据库**: SQLite
- **Web界面**: Flask + Flask-SocketIO

## 系统架构

### 模块划分
```
系统架构
├── 视频采集模块 (camera.py)
│   └── 支持USB摄像头和RTSP流
├── 猫检测模块 (cat_detector.py)
│   └── YOLOv8目标检测
├── 目标追踪模块 (object_tracker.py)
│   └── DeepSORT追踪算法
├── 个体识别模块 (cat_classifier.py)
│   └── 迁移学习分类器
├── 行为分析模块 (behavior_analyzer.py)
│   └── ROI位置法
├── 数据存储模块 (database.py)
│   └── SQLite数据库
└── Web界面模块 (app.py)
    └── Flask应用
```

### 数据流
```
视频流 → 检测 → 追踪 → 识别 → 行为分析 → 数据存储 → Web展示
```

## 实施计划

### 第一阶段：项目基础搭建 ✅
- [x] 创建完整的目录结构
- [x] 编写 `requirements.txt` 依赖清单
- [x] 创建配置文件模板 `config/default.yaml`
- [x] 编写配置管理模块 `config.py`
- [x] 编写日志模块 `logger.py`
- [x] 创建 `README.md` 项目文档

### 第二阶段：核心模块开发 ✅
- [x] 视频采集模块 `src/core/camera.py`
- [x] 猫检测模块 `src/core/cat_detector.py`
- [x] 目标追踪模块 `src/core/object_tracker.py`
- [x] 个体识别模块 `src/core/cat_classifier.py`
- [x] 行为分析模块 `src/core/behavior_analyzer.py`
- [x] 数据存储模块 `src/storage/database.py`
- [x] Web界面模块 `src/web/app.py`

### 第三阶段：主程序与集成 ✅
- [x] 编写主程序入口 `src/main.py`
- [x] 集成所有模块
- [x] 实现完整的处理流程
- [x] 添加异常处理和日志

### 第四阶段：工具脚本 ✅
- [x] 数据收集脚本 `scripts/collect_data.py`
- [x] 模型训练脚本 `scripts/train_classifier.py`
- [x] ROI标注工具 `scripts/annotate_roi.py`
- [x] 安装脚本 `scripts/setup.sh`

### 第五阶段：文档与部署 ✅
- [x] 编写 README.md 用户文档
- [x] 创建启动脚本 `run.bat` 和 `run.sh`
- [x] 添加 `.gitignore` 文件

## 核心功能实现

### 1. 视频采集 (camera.py)
**功能**:
- 支持USB摄像头和网络摄像头(RTSP)
- 多线程读取，提高性能
- 帧率控制和缓冲区管理

**关键参数**:
```python
camera_type: 'usb' 或 'rtsp'
width, height: 分辨率
fps: 帧率
buffer_size: 缓冲区大小
```

### 2. 猫检测 (cat_detector.py)
**功能**:
- 使用YOLOv8检测猫
- 返回边界框和置信度
- 支持GPU加速

**关键参数**:
```python
model_path: 模型文件路径
confidence_threshold: 置信度阈值
iou_threshold: IOU阈值
target_class: 目标类别（COCO数据集中cat是15）
```

### 3. 目标追踪 (object_tracker.py)
**功能**:
- 使用DeepSORT算法
- 为每只猫分配唯一ID
- 管理追踪状态

**关键参数**:
```python
max_disappeared: 最大消失帧数
max_distance: 最大匹配距离
min_confidence: 最小置信度
```

### 4. 个体识别 (cat_classifier.py)
**功能**:
- 迁移学习分类器
- 支持4只猫分类
- 支持数据收集和模型训练

**模型选择**:
- MobileNet: 轻量级，适合实时应用
- ResNet: 平衡性能和准确率
- EfficientNet: 高准确率

### 5. 行为分析 (behavior_analyzer.py)
**功能**:
- ROI区域判断（位置法）
- 进入/离开事件检测
- 状态机实现

**关键参数**:
```python
roi: 感兴趣区域（矩形或多边形）
min_frames_in_roi: 在ROI中的最小帧数
exit_delay_frames: 离开延迟帧数
min_duration: 最小持续时间（秒）
```

### 6. 数据存储 (database.py)
**功能**:
- SQLite数据库
- CRUD操作
- 统计查询

**数据表**:
- `litter_events`: 事件记录表
- `daily_statistics`: 每日统计表

### 7. Web界面 (app.py)
**功能**:
- 实时视频流
- 统计数据展示
- WebSocket实时更新

## 使用流程

### 1. 安装系统
```bash
bash scripts/setup.sh
```

### 2. 标注ROI区域
```bash
python scripts/annotate_roi.py --camera-id 0
```

### 3. 收集训练数据
```bash
python scripts/collect_data.py
```

### 4. 训练分类器
```bash
python scripts/train_classifier.py --data-dir data/raw/training
```

### 5. 启动系统
```bash
python src/main.py
```

## 配置说明

### 摄像头配置
```yaml
camera:
  type: usb  # usb 或 rtsp
  device_id: 0
  width: 1280
  height: 720
  fps: 30
```

### ROI配置
```yaml
roi:
  type: rectangle  # rectangle 或 polygon
  rectangle:
    x: 100
    y: 100
    width: 300
    height: 300
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
│   └── processed/            # 处理后的数据
├── logs/                     # 日志文件
├── scripts/                  # 工具脚本
├── src/
│   ├── core/                 # 核心模块
│   ├── storage/              # 存储模块
│   ├── utils/                # 工具模块
│   ├── web/                  # Web模块
│   ├── config.py             # 配置管理
│   └── main.py               # 主程序
├── tests/                    # 测试文件
├── requirements.txt          # 依赖清单
├── README.md                 # 项目文档
└── run.sh / run.bat          # 启动脚本
```

## 技术要点

### YOLOv8检测
- 使用预训练的YOLOv8模型
- COCO数据集类别15为猫
- 支持GPU加速

### DeepSORT追踪
- 基于卡尔曼滤波和匈牙利算法
- 结合外观特征和运动信息
- 处理目标遮挡和消失

### 迁移学习
- 使用预训练的ImageNet模型
- 微调最后一层用于猫分类
- 支持数据增强

### ROI位置法
- 简单高效的行为检测方法
- 判断目标中心点是否在ROI内
- 使用状态机管理进入/离开事件

## 未来改进

1. **性能优化**
   - 模型量化
   - 多进程处理
   - 边缘计算

2. **功能扩展**
   - 多摄像头支持
   - 健康监测（体重、活动量）
   - 异常行为检测

3. **用户体验**
   - 移动端App
   - 数据导出功能
   - 图表可视化

## 许可证

MIT License

## 联系方式

如有问题或建议，请提交Issue。
