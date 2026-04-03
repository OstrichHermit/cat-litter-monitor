# 猫砂盆监控

基于 YOLO 目标检测的智能猫砂盆使用监控系统。通过 IP 摄像头实时检测猫咪进出猫砂盆的行为，自动拍照记录，并通过 Web 界面和 MCP 服务器提供数据查询和管理功能。

An intelligent cat litter box monitoring system based on YOLO object detection. Detects cat entry/exit behaviors in real-time via IP camera, automatically captures photos, and provides data query and management through a Web interface and MCP server.

[English](README_EN.md) | [简体中文](README.md)

---

## ✨ 核心功能

**💡 智能检测**
- 基于 YOLOv8 深度学习模型实时检测猫咪
- IOU 追踪算法跟踪猫咪运动轨迹
- 支持多目标同时追踪（默认最多 4 只猫）
- 可配置置信度阈值和 NMS IOU 阈值

**📷 自动拍照**
- 支持多猫砂盆区域（ROI）配置
- 猫咪进入猫砂盆区域（ROI）并停留指定时间后自动拍照
- 每个猫砂盆区域（ROI）独立拍照间隔控制
- 照片按日期自动归档存储

**🌐 Web 管理界面**
- 桌面端和移动端自适应布局
- 亮色/暗色主题切换
- 实时视频流（WebSocket 推送）
- 每日统计图表
- 未识别照片通知和管理
- 服务监控面板（实时进程状态和日志）

**🤖 MCP 服务器集成**
- 通过 MCP 协议暴露 5 个工具
- 支持 stdio 和 HTTP 两种传输模式
- 可被 OpenClaw、Claude Code 等 AI 代理调用
- Web 界面实时监控 MCP Server 状态

**📋 通知系统**
- Web 界面实时通知未识别照片
- 支持猫咪识别和标记
- 照片自动按识别状态分类存储

**📊 服务监控**
- 5 个进程独立运行和监控
- Manager 看门狗自动重启异常进程
- Web 界面集成实时日志面板
- 一键重启/停止所有服务


## 🏗️ 系统架构

系统由 5 个并发进程组成，通过文件系统（JSON 状态文件、SQLite 数据库）和 WebSocket 进行进程间通信。

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   go2rtc    │  │    Main     │  │   Manager   │
│  视频流中转  │  │  核心监控    │  │   看门狗    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       │         ┌──────┴──────┐         │
       │         │ WebSocket   │         │
       │         │  服务端     │         │
       │         └──────┬──────┘         │
       │                │                │
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│    Web      │  │ MCP Server  │  │             │
│  Web 界面   │  │  外部接口   │  │             │
│  客户端     │  │ HTTP/Stdio │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
       │                │                │
       └────────────────┴────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  SQLite 数据库     │
                    │  JSON 状态文件     │
                    │  照片文件系统      │
                    └───────────────────┘
```

**进程职责**：

| 进程 | 模块 | 职责 |
|------|------|------|
| go2rtc | 视频流中转 | RTSP 视频流接收和转发 |
| Main | `src/main.py` | YOLO 检测、目标追踪、拍照、内部 WebSocket API |
| Web | `src/web/app.py` | Web 界面（FastAPI + WebSocket）、实时数据接收 |
| Manager | `src/manager.py` | 进程健康检查、异常自动重启 |
| MCP Server | `src/mcp/server.py` | 对外暴露工具接口（HTTP/Stdio） |

## 🚀 快速开始

### 1. 前置要求

- Windows 系统
- Python 3.10+
- IP 摄像头（支持 RTSP 协议）
- [go2rtc](https://github.com/AlexxIT/go2rtc)（视频流中转服务）
- NVIDIA GPU（可选但推荐，大幅提升推理速度）

### 2. 安装

```bash
# 克隆项目
git clone <repo-url>
cd cat-litter-monitor

# 安装依赖
pip install -r requirements.txt
```

### 3. 安装配置 go2rtc

1. 下载 [go2rtc](https://github.com/AlexxIT/go2rtc/releases) 可执行文件
2. 创建 go2rtc 配置文件（默认路径为项目同级目录 `../go2rtc/go2rtc.yaml`）
3. 配置 RTSP 摄像头连接：

```yaml
# go2rtc.yaml 示例，推荐使用小米摄像头 4
streams:
  my_camera: rtsp://username:password@192.168.1.100:554/stream1
```

> 💡 **提示**：go2rtc 路径可在 `start.bat` 顶部的 `GO2RTC_PATH` 和 `GO2RTC_CONFIG` 变量中修改。

### 4. 下载 YOLO 模型

下载 [YOLO26](https://docs.ultralytics.com/models/yolo26/) 预训练模型（推荐 `yolo26x.pt`），放到指定目录：

```bash
# 模型文件路径
data/models/yolo26x.pt
```

> 💡 **提示**：YOLO26 是 ultralytics 于 2026 年 1 月发布的最新模型系列，也可自行训练使用更精准的猫咪检测模型。配置文件中 `target_class: 15` 对应 YOLO 模型数据集中的 cat 类别。

### 5. 配置

```bash
# 复制配置模板
cp config/default.yaml.example config/default.yaml
# 编辑配置文件
```

配置文件主要配置项（详见下方 [配置选项](#⚙️-配置选项) 章节）：
- 摄像头连接（go2rtc 地址和名称）
- YOLO 模型路径
- ROI 区域坐标
- 猫咪名字列表
- Web 端口

### 6. 标注 ROI 区域

运行 ROI 标注工具，在摄像头画面上框选猫砂盆的位置：

```bash
python scripts/annotate_roi_go2rtc.py
```

> 💡 **提示**：运行前需要先启动 go2rtc 并确保摄像头连接正常。标注工具会自动读取摄像头画面，用鼠标逐次点击，成功框选完猫砂盆区域后按 `s` 保存，坐标会自动写入 `config/default.yaml` 的 `roi.rois` 配置项。

操作方式：
- 鼠标左键：绘制 ROI 区域（矩形模式点两个对角点，多边形模式逐点绘制）
- 鼠标右键：完成多边形
- `n`：完成当前 ROI，开始绘制下一个（支持多个猫砂盆）
- `r` / `p`：切换矩形/多边形模式
- `c`：清除当前 ROI
- `a`：清除所有 ROI
- `s`：保存并退出
- `q`：退出不保存

### 7. 启动服务

**一键启动**（推荐）：
```bash
start.bat
```

启动后包含 5 个后台进程：

1. **go2rtc** - 视频流中转
2. **Main** - 核心监控（检测、追踪、拍照）
3. **Web** - Web 管理界面
4. **Manager** - 看门狗（自动监控和重启异常进程）
5. **MCP Server** - MCP 工具接口

启动后访问 **Web 管理界面**：http://localhost:5000

在 Web 界面中你可以：
- 查看实时视频流和检测结果
- 查看各组件运行状态和 PID
- 查看实时日志输出（各组件独立面板）
- 切换亮色/暗色主题
- 处理未识别照片
- 查看每日使用统计图表
- 一键重启/停止所有服务

**停止服务**：
```bash
stop.bat
```

**重启服务**：
```bash
restart.bat
```

### 8. 局域网访问配置（可选）

如果需要从局域网内其他设备（手机、平板等）访问 Web 管理界面，需要配置防火墙放行端口：

```bash
# 以管理员身份运行
scripts\setup_lan_access.bat
```

该脚本会自动完成以下操作：
1. 添加防火墙入站规则，放行 TCP 5000 端口
2. 检测本机局域网 IP 地址并显示访问链接
3. 配置完成后按任意键启动监控系统

> ⚠️ **注意**：必须以管理员身份运行此脚本，否则防火墙规则添加会失败。

## 🔌 MCP 服务器集成

MCP 服务器基于 FastMCP 框架，提供 5 个工具供 Claude / AI 代理调用。

**HTTP 模式**（推荐，随 `start.bat` 自动启动）：

```json
{
  "mcpServers": {
    "cat-litter-monitor": {
      "type": "http",
      "url": "http://127.0.0.1:5001/mcp"
    }
  }
}
```

### MCP 工具列表

| 工具名 | 说明 |
|--------|------|
| **add_litter_records** | 批量添加猫砂盆使用记录，自动处理照片移动/复制 |
| **get_litter_records** | 按条件查询使用记录（支持日期范围和猫咪过滤） |
| **get_daily_statistics** | 获取每日统计数据（各猫咪使用次数） |
| **get_unidentified_photos** | 获取未识别的照片列表 |
| **mark_unidentifiable** | 将无法识别的照片标记为 Unidentifiable |

## ⚙️ 配置选项

### config/default.yaml 主要配置

```yaml
# 摄像头配置（通过 go2rtc 获取视频流）
camera:
  buffer_size: 1                    # 缓冲帧数

# 数据库配置
database:
  path: data/litter_monitor.db      # SQLite 数据库路径

# 检测配置
detection:
  confidence_threshold: 0.25        # 检测置信度阈值
  half: true                        # FP16 半精度推理（需要 GPU）
  input_size: 320                   # 模型输入尺寸
  iou_threshold: 0.6                # NMS IOU 阈值
  model_path: data/models/yolo26x.pt  # YOLO 模型路径
  target_class: 15                  # COCO 类别 ID（15=cat）
  use_gpu: true                     # 使用 GPU 加速

# Go2rtc 配置
go2rtc:
  api_port: 1984                    # Go2rtc API 端口
  camera_name: my_camera            # 摄像头名称（需与 go2rtc.yaml 一致）
  config_path: ../go2rtc/go2rtc.yaml
  exe_path: ../go2rtc/go2rtc.exe
  host: localhost
  rtsp_port: 8554                   # RTSP 端口

# 日志配置
logging:
  console: true                     # 是否输出到控制台
  file: logs/litter_monitor.log     # 日志文件路径
  level: INFO                       # 日志级别
  max_lines: 2000                   # 日志最大行数

# 管理器配置
manager:
  check_interval: 5                 # 健康检查间隔（秒）
  max_frame_failures: 500           # 连续帧失败上限，超过后重启主进程

# 拍照配置
photo:
  min_stay_seconds: 1               # 最短停留时间（秒）
  photo_base_dir: photo             # 照片存储目录
  photo_interval:                   # 各 ROI 拍照间隔（秒）
    - 90.0
    - 90.0

# ROI 配置（多区域支持）
roi:
  rois:                             # 使用 ROI 标注工具生成
    # - id: 1
    #   name: 猫砂盆1
    #   polygon:
    #     - [x1, y1]
    #     - [x2, y2]
    #     - [x3, y3]
    #     - [x4, y4]
    #   type: polygon

# 系统配置
system:
  process_every_n_frames: 1         # 每N帧处理一次（1=每帧）

# 目标追踪配置
tracking:
  max_disappeared: 60               # 目标消失多少帧后删除追踪
  max_distance: 0.2                 # 最大追踪距离（归一化）
  max_tracks: 4                     # 最大同时追踪目标数
  min_confidence: 0.1               # 最小追踪置信度

# MCP 服务器配置
mcp:
  host: 127.0.0.1                    # MCP 监听地址
  port: 5001                         # MCP 监听端口
  transport: http                    # 传输模式（http / stdio）

# Web 界面配置
web:
  debug: false                      # 调试模式
  host: 0.0.0.0                     # 监听地址
  port: 5000                        # 监听端口

# Main 进程配置（内部 API，供 Web 服务器连接）
main:
  host: 127.0.0.1                    # 内部 API 监听地址（仅本地）
  port: 5002                         # 内部 API 监听端口

# 猫咪名字配置示例
cats:
  - name: 猫咪1
  - name: 猫咪2
  - name: 猫咪3
  - name: 猫咪4
```

## 📁 目录结构

```
cat-litter-monitor/
├── config/
│   ├── default.yaml                # 配置文件（从 .example 复制）
│   └── default.yaml.example        # 配置模板
├── data/
│   ├── litter_monitor.db           # SQLite 数据库
│   ├── manager_state.json          # Manager 状态文件
│   └── models/
│       └── yolo_cat.pt             # YOLO 模型文件
├── logs/
│   ├── go2rtc.log                  # go2rtc 日志
│   ├── main.log                    # 主进程日志
│   ├── manager.log                 # Manager 日志
│   ├── mcp.log                     # MCP Server 日志
│   ├── web.log                     # Web 服务器日志
│   └── litter_monitor.log          # 系统日志
├── photo/
│   └── YYYY-MM-DD/
│       ├── Unidentified/           # 未识别照片（待处理）
│       ├── Identified/
│       │   ├── 猫咪1/               # 已识别照片（按猫咪名归档）
│       │   ├── 猫咪2/
│       │   ├── 猫咪3/
│       │   └── 猫咪4/
│       └── Unidentifiable/         # 无法识别照片（需手动处理）
├── scripts/
│   ├── annotate_roi_go2rtc.py      # ROI 区域标注工具
│   └── setup_lan_access.bat        # 局域网访问配置脚本
├── src/
│   ├── main.py                     # 主程序入口（监控核心）
│   ├── internal_api.py             # 内部 WebSocket API（供 Web 连接）
│   ├── manager.py                  # 看门狗进程
│   ├── config.py                   # 配置管理
│   ├── core/
│   │   ├── camera.py               # 摄像头模块
│   │   ├── cat_detector.py         # 猫咪检测器（YOLO）
│   │   ├── object_tracker.py       # 目标追踪器（IOU）
│   │   ├── roi.py                  # ROI 区域管理
│   │   └── photo_capture.py        # 拍照管理
│   ├── storage/
│   │   ├── database.py             # 数据库操作
│   │   └── photo_manager.py        # 照片文件管理
│   ├── web/
│   │   └── app.py                  # Web 服务器（独立进程，FastAPI + WebSocket）
│   ├── mcp/
│   │   └── server.py               # MCP 服务器
│   └── utils/
│       ├── logger.py               # 日志工具
│       └── log_writer.py           # 日志重定向
├── start.bat                       # 一键启动脚本
├── stop.bat                        # 停止脚本
├── restart.bat                     # 重启脚本
└── requirements.txt                # Python 依赖
```

## 🔧 故障排查

### 摄像头无法连接

1. 检查 RTSP 地址是否正确（在 go2rtc.yaml 中）
2. 确认摄像头网络是否可达
3. 检查 go2rtc 是否正常运行：访问 http://localhost:1984
4. 查看 `logs/go2rtc.log` 排查问题

### Web 界面无法访问

1. 检查 Web 进程是否运行（Web 和 Main 是独立进程）
2. 确认端口 5000 未被占用
3. 查看 `logs/web.log` 排查问题
4. 在服务监控面板检查各进程状态

### 检测不到猫咪

1. 确认 YOLO 模型文件存在且路径正确
2. 检查 `detection.confidence_threshold` 是否过高，尝试降低到 0.15
3. 确认 ROI 区域坐标已正确配置（配置文件中 `roi.rois` 不能为空）
4. 如使用 GPU，确认 `detection.use_gpu: true` 且 CUDA 已正确安装

### 进程频繁重启

1. 查看 `logs/manager.log` 了解重启原因
2. 检查 `manager.max_frame_failures` 配置是否过低
3. 确认摄像头视频流稳定

### MCP Server 无法连接

1. 检查 MCP Server 进程是否运行
2. 确认端口未被占用
3. 查看 `logs/mcp.log` 排查问题

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 目标检测 | YOLOv8 (ultralytics) |
| 视频处理 | OpenCV |
| Web 后端 | FastAPI + WebSocket |
| 视频流中转 | go2rtc |
| 数据存储 | SQLite |
| MCP 框架 | FastMCP |
| 前端 | 纯 HTML/CSS/JS（无框架） |
| 运行环境 | Python 3.10+, Windows |

## 📄 许可证

AGPL-3.0
