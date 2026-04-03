# Cat Litter Monitor

An intelligent cat litter box monitoring system based on YOLO object detection. Detects cat entry/exit behaviors in real-time via IP camera, automatically captures photos, and provides data query and management through a Web interface and MCP server.

基于 YOLO 目标检测的智能猫砂盆使用监控系统。通过 IP 摄像头实时检测猫咪进出猫砂盆的行为，自动拍照记录，并通过 Web 界面和 MCP 服务器提供数据查询和管理功能。

[English](README_EN.md) | [简体中文](README.md)

---

## ✨ Features

**💡 Intelligent Detection**
- Real-time cat detection based on YOLOv8 deep learning model
- IOU tracking algorithm for cat movement trajectory
- Multi-object tracking support (up to 4 cats by default)
- Configurable confidence threshold and NMS IOU threshold

**📷 Auto Photo Capture**
- Support for multiple litter box areas (ROI) configuration
- Auto capture photo when cat stays in ROI for specified duration
- Independent photo interval control per ROI
- Photos automatically organized by date

**🌐 Web Management Interface**
- Responsive layout for desktop and mobile
- Light/Dark theme toggle
- Real-time video stream (WebSocket push)
- Daily statistics charts
- Unidentified photo notification and management
- Service monitoring panel (real-time process status and logs)

**🤖 MCP Server Integration**
- 5 tools exposed via MCP protocol
- Supports both stdio and HTTP transport modes
- Callable by AI agents like OpenClaw, Claude Code
- Real-time MCP Server status monitoring via Web interface

**📋 Notification System**
- Real-time web interface notifications for unidentified photos
- Cat identification and tagging support
- Photos automatically classified by identification status

**📊 Service Monitoring**
- 5 independent processes running and monitored
- Manager watchdog for automatic restart of abnormal processes
- Real-time log panels integrated in Web interface
- One-click restart/stop all services


## 🏗️ System Architecture

The system consists of 5 concurrent processes, communicating via file system (JSON state files, SQLite database) and WebSocket.

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   go2rtc    │  │    Main     │  │   Manager   │
│  Stream Relay│  │ Core Monitor│  │  Watchdog  │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       │         ┌──────┴──────┐         │
       │         │ WebSocket   │         │
       │         │   Server    │         │
       │         └──────┬──────┘         │
       │                │                │
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│    Web      │  │ MCP Server  │  │             │
│   Web UI    │  │ External API│  │             │
│   Client    │  │ HTTP/Stdio │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
       │                │                │
       └────────────────┴────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  SQLite Database  │
                    │  JSON State Files │
                    │  Photo File System│
                    └───────────────────┘
```

**Process Responsibilities**:

| Process | Module | Responsibility |
|---------|--------|----------------|
| go2rtc | Video Stream Relay | RTSP stream reception and forwarding |
| Main | `src/main.py` | YOLO detection, object tracking, photo capture, internal WebSocket API |
| Web | `src/web/app.py` | Web interface (FastAPI + WebSocket), real-time data receiver |
| Manager | `src/manager.py` | Process health check, automatic restart on failure |
| MCP Server | `src/mcp/server.py` | External tool interface (HTTP/Stdio) |

## 🚀 Quick Start

### 1. Prerequisites

- Windows system
- Python 3.10+
- IP camera (supporting RTSP protocol)
- [go2rtc](https://github.com/AlexxIT/go2rtc) (video stream relay service)
- NVIDIA GPU (optional but recommended, significantly improves inference speed)

### 2. Installation

```bash
# Clone the project
git clone <repo-url>
cd cat-litter-monitor

# Install dependencies
pip install -r requirements.txt
```

### 3. Install and Configure go2rtc

1. Download [go2rtc](https://github.com/AlexxIT/go2rtc/releases) executable
2. Create go2rtc config file (default path: `../go2rtc/go2rtc.yaml` in project sibling directory)
3. Configure RTSP camera connection:

```yaml
# go2rtc.yaml example, Xiaomi Camera 4 recommended
streams:
  my_camera: rtsp://username:password@192.168.1.100:554/stream1
```

> 💡 **Tip**: go2rtc path can be modified via `GO2RTC_PATH` and `GO2RTC_CONFIG` variables at the top of `start.bat`.

### 4. Download YOLO Model

Download [YOLO26](https://docs.ultralytics.com/models/yolo26/) pre-trained model (recommended `yolo26x.pt`), place in specified directory:

```bash
# Model file path
data/models/yolo26x.pt
```

> 💡 **Tip**: YOLO26 is the latest model series released by ultralytics in January 2026. You can also train your own more accurate cat detection model. The `target_class: 15` in config corresponds to the cat class in the YOLO model dataset.

### 5. Configuration

```bash
# Copy config template
cp config/default.yaml.example config/default.yaml
# Edit configuration file
```

Main configuration items (see [Configuration Options](#⚙️-configuration-options) for details):
- Camera connection (go2rtc address and name)
- YOLO model path
- ROI area coordinates
- Cat name list
- Web port

### 6. Annotate ROI Areas

Run ROI annotation tool to draw litter box positions on camera feed:

```bash
python scripts/annotate_roi_go2rtc.py
```

> 💡 **Tip**: Run this after starting go2rtc and ensuring camera connection is normal. The annotation tool will automatically read camera feed, use mouse to draw ROIs, press `s` to save after completing all areas, coordinates will be automatically written to `roi.rois` in `config/default.yaml`.

Controls:
- Left mouse button: Draw ROI area (rectangle mode: two diagonal points, polygon mode: click points one by one)
- Right mouse button: Complete polygon
- `n`: Complete current ROI, start drawing next (multiple litter boxes supported)
- `r` / `p`: Switch rectangle/polygon mode
- `c`: Clear current ROI
- `a`: Clear all ROIs
- `s`: Save and exit
- `q`: Exit without saving

### 7. Start Service

**One-click start** (recommended):
```bash
start.bat
```

After startup, 5 background processes run:

1. **go2rtc** - Video stream relay
2. **Main** - Core monitoring (detection, tracking, photo capture)
3. **Web** - Web management interface
4. **Manager** - Watchdog (auto monitor and restart abnormal processes)
5. **MCP Server** - MCP tool interface

After starting, visit **Web Management Interface**: http://localhost:5000

In the Web interface you can:
- View real-time video stream and detection results
- View component running status and PID
- View real-time log output (independent panels for each component)
- Toggle light/dark theme
- Process unidentified photos
- View daily usage statistics charts
- One-click restart/stop all services

**Stop Service**:
```bash
stop.bat
```

**Restart Service**:
```bash
restart.bat
```

### 8. LAN Access Configuration (Optional)

If you need to access the Web interface from other devices on the LAN (phone, tablet, etc.), configure firewall to allow the port:

```bash
# Run as administrator
scripts\setup_lan_access.bat
```

This script will automatically:
1. Add firewall inbound rule, allow TCP port 5000
2. Detect local LAN IP address and display access link
3. Start monitoring system after configuration

> ⚠️ **Warning**: Must run as administrator, otherwise firewall rule addition will fail.

## 🔌 MCP Server Integration

MCP server is based on FastMCP framework, providing 5 tools for Claude / AI agent calls.

**HTTP Mode** (recommended, auto-started with `start.bat`):

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

### MCP Tools

| Tool | Description |
|------|-------------|
| **add_litter_records** | Batch add litter box usage records, auto handle photo move/copy |
| **get_litter_records** | Query usage records by conditions (support date range and cat filter) |
| **get_daily_statistics** | Get daily statistics (usage count per cat) |
| **get_unidentified_photos** | Get list of unidentified photos |
| **mark_unidentifiable** | Mark unidentifiable photos as Unidentifiable |

## ⚙️ Configuration Options

### config/default.yaml Main Settings

```yaml
# Camera configuration (via go2rtc)
camera:
  buffer_size: 1                    # Buffer frame count

# Database configuration
database:
  path: data/litter_monitor.db      # SQLite database path

# Detection configuration
detection:
  confidence_threshold: 0.25        # Detection confidence threshold
  half: true                        # FP16 half-precision inference (requires GPU)
  input_size: 320                   # Model input size
  iou_threshold: 0.6                # NMS IOU threshold
  model_path: data/models/yolo26x.pt  # YOLO model path
  target_class: 15                  # COCO class ID (15=cat)
  use_gpu: true                     # Use GPU acceleration

# Go2rtc configuration
go2rtc:
  api_port: 1984                    # Go2rtc API port
  camera_name: my_camera            # Camera name (must match go2rtc.yaml)
  config_path: ../go2rtc/go2rtc.yaml
  exe_path: ../go2rtc/go2rtc.exe
  host: localhost
  rtsp_port: 8554                   # RTSP port

# Logging configuration
logging:
  console: true                     # Output to console
  file: logs/litter_monitor.log     # Log file path
  level: INFO                       # Log level
  max_lines: 2000                   # Max log lines

# Manager configuration
manager:
  check_interval: 5                 # Health check interval (seconds)
  max_frame_failures: 500           # Max consecutive frame failures before restart

# Photo capture configuration
photo:
  min_stay_seconds: 1               # Minimum stay duration (seconds)
  photo_base_dir: photo             # Photo storage directory
  photo_interval:                   # Photo interval per ROI (seconds)
    - 90.0
    - 90.0

# ROI configuration (multi-area support)
roi:
  rois:                             # Generated by ROI annotation tool
    # - id: 1
    #   name: Litter Box 1
    #   polygon:
    #     - [x1, y1]
    #     - [x2, y2]
    #     - [x3, y3]
    #     - [x4, y4]
    #   type: polygon

# System configuration
system:
  process_every_n_frames: 1         # Process every N frames (1=every frame)

# Object tracking configuration
tracking:
  max_disappeared: 60               # Frames before removing lost track
  max_distance: 0.2                 # Max tracking distance (normalized)
  max_tracks: 4                     # Max simultaneous tracked objects
  min_confidence: 0.1               # Min tracking confidence

# MCP server configuration
mcp:
  host: 127.0.0.1                    # MCP listening address
  port: 5001                         # MCP listening port
  transport: http                    # Transport mode (http / stdio)

# Web interface configuration
web:
  debug: false                      # Debug mode
  host: 0.0.0.0                     # Listening address
  port: 5000                        # Listening port

# Main process configuration (internal API for Web server connection)
main:
  host: 127.0.0.1                    # Internal API listening address (localhost only)
  port: 5002                         # Internal API listening port

# Cat names example
cats:
  - name: Cat1
  - name: Cat2
  - name: Cat3
  - name: Cat4
```

## 📁 Directory Structure

```
cat-litter-monitor/
├── config/
│   ├── default.yaml                # Config file (copied from .example)
│   └── default.yaml.example        # Config template
├── data/
│   ├── litter_monitor.db           # SQLite database
│   ├── manager_state.json          # Manager state file
│   └── models/
│       └── yolo_cat.pt             # YOLO model file
├── logs/
│   ├── go2rtc.log                 # go2rtc log
│   ├── main.log                   # Main process log
│   ├── manager.log                # Manager log
│   ├── mcp.log                    # MCP Server log
│   ├── web.log                    # Web server log
│   └── litter_monitor.log         # System log
├── photo/
│   └── YYYY-MM-DD/
│       ├── Unidentified/          # Unidentified photos (pending)
│       ├── Identified/
│       │   ├── Cat1/              # Identified photos (organized by cat name)
│       │   ├── Cat2/
│       │   ├── Cat3/
│       │   └── Cat4/
│       └── Unidentifiable/        # Unidentifiable photos (manual processing required)
├── scripts/
│   ├── annotate_roi_go2rtc.py     # ROI area annotation tool
│   └── setup_lan_access.bat       # LAN access configuration script
├── src/
│   ├── main.py                    # Main program entry (monitoring core)
│   ├── internal_api.py            # Internal WebSocket API (for Web server connection)
│   ├── manager.py                 # Watchdog process
│   ├── config.py                  # Configuration management
│   ├── core/
│   │   ├── camera.py              # Camera module
│   │   ├── cat_detector.py        # Cat detector (YOLO)
│   │   ├── object_tracker.py      # Object tracker (IOU)
│   │   ├── roi.py                # ROI area management
│   │   └── photo_capture.py      # Photo capture management
│   ├── storage/
│   │   ├── database.py            # Database operations
│   │   └── photo_manager.py       # Photo file management
│   ├── web/
│   │   └── app.py                # Web server (standalone process, FastAPI + WebSocket)
│   ├── mcp/
│   │   └── server.py             # MCP server
│   └── utils/
│       ├── logger.py              # Logging utility
│       └── log_writer.py         # Log redirection
├── start.bat                      # One-click start script
├── stop.bat                       # Stop script
├── restart.bat                    # Restart script
└── requirements.txt               # Python dependencies
```

## 🔧 Troubleshooting

### Camera Cannot Connect

1. Check if RTSP address is correct (in go2rtc.yaml)
2. Confirm camera network is reachable
3. Check if go2rtc is running: visit http://localhost:1984
4. Check `logs/go2rtc.log` for troubleshooting

### Web Interface Not Accessible

1. Check if Web process is running (Web and Main are independent processes)
2. Confirm port 5000 is not occupied
3. Check `logs/web.log` for troubleshooting
4. Check process status in service monitoring panel

### Cat Not Detected

1. Confirm YOLO model file exists and path is correct
2. Check if `detection.confidence_threshold` is too high, try lowering to 0.15
3. Confirm ROI area coordinates are correctly configured (`roi.rois` cannot be empty)
4. If using GPU, confirm `detection.use_gpu: true` and CUDA is correctly installed

### Process Frequent Restarts

1. Check `logs/manager.log` to understand restart reason
2. Check if `manager.max_frame_failures` is set too low
3. Confirm camera video stream is stable

### MCP Server Cannot Connect

1. Check if MCP Server process is running
2. Confirm port is not occupied
3. Check `logs/mcp.log` for troubleshooting

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Object Detection | YOLOv8 (ultralytics) |
| Video Processing | OpenCV |
| Web Backend | FastAPI + WebSocket |
| Video Stream Relay | go2rtc |
| Data Storage | SQLite |
| MCP Framework | FastMCP |
| Frontend | Pure HTML/CSS/JS (no framework) |
| Runtime | Python 3.10+, Windows |

## 📄 License

AGPL-3.0
