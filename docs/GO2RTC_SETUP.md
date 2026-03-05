# go2rtc 配置指南

本文档介绍如何配置go2rtc与小米智能摄像头4配合使用。

## 目录

- [go2rtc简介](#go2rtc简介)
- [安装go2rtc](#安装go2rtc)
- [配置小米摄像头](#配置小米摄像头)
- [项目配置](#项目配置)
- [使用方法](#使用方法)
- [故障排查](#故障排查)

---

## go2rtc简介

go2rtc是一个轻量级的多协议流媒体服务器，支持：
- RTSP、RTMP、HTTP、WebRTC、HLS等多种协议
- 实时协议转换
- 多摄像头管理
- 低延迟传输（200-500ms）
- Web管理界面

### 为什么使用go2rtc？

| 特性 | go2rtc | 直接RTSP |
|------|--------|----------|
| 多摄像头管理 | ✅ | ❌ |
| 自动重连 | ✅ | 需自己实现 |
| 协议转换 | ✅ | ❌ |
| Web界面 | ✅ | ❌ |
| 延迟 | 200-500ms | 100-300ms |
| 稳定性 | 高 | 中等 |

---

## 安装go2rtc

### 方法一：Docker安装（推荐）

#### Windows
```bash
# 拉取镜像
docker pull aler/go2rtc:latest

# 运行容器
docker run -d ^
  --name go2rtc ^
  --restart always ^
  -p 1984:1984 ^
  -p 8554:8554 ^
  -p 8888:8888 ^
  -v %CD%\go2rtc-config:/config ^
  aler/go2rtc:latest
```

#### Linux/Mac
```bash
# 拉取镜像
docker pull aler/go2rtc:latest

# 运行容器
docker run -d \
  --name go2rtc \
  --restart always \
  -p 1984:1984 \
  -p 8554:8554 \
  -p 8888:8888 \
  -v $(pwd)/go2rtc-config:/config \
  aler/go2rtc:latest
```

### 方法二：二进制文件安装

#### Windows
1. 下载最新版本：https://github.com/AlexxIT/go2rtc/releases
2. 解压到目标目录（如 `C:\go2rtc`）
3. 创建配置文件 `go2rtc.yaml`

#### Linux
```bash
# 下载
wget https://github.com/AlexxIT/go2rtc/releases/download/v1.7.0/go2rtc_linux_amd64
chmod +x go2rtc_linux_amd64
sudo mv go2rtc_linux_amd64 /usr/local/bin/go2rtc

# 创建服务
sudo tee /etc/systemd/system/go2rtc.service > /dev/null <<EOF
[Unit]
Description=go2rtc Streaming Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/go2rtc -c /etc/go2rtc.yaml
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl enable go2rtc
sudo systemctl start go2rtc
```

### 验证安装

访问Web管理界面：
```
http://localhost:1984
```

---

## 配置小米摄像头

### 1. 获取小米摄像头RTSP地址

#### 方法一：通过米家APP
1. 打开米家APP
2. 选择摄像头设备
3. 进入"设置" → "高级设置"
4. 开启"RTSP协议"
5. 设置用户名和密码
6. 记录RTSP地址

#### 方法二：通过局域网扫描
```bash
# 使用nmap扫描设备
nmap -p 554 192.168.1.0/24
```

#### RTSP地址格式
```
rtsp://用户名:密码@IP地址:554/stream
```

示例：
```
rtsp://admin:123456@192.168.1.100:554/stream
```

### 2. 配置go2rtc

创建或编辑 `go2rtc.yaml` 配置文件：

```yaml
# go2rtc 配置文件

# API设置
api:
  # 启用API
  listen: ":1984"

# RTSP服务
rtsp:
  # RTSP监听地址
  listen: ":8554"

# WebRTC服务
webrtc:
  # WebRTC监听地址
  listen: ":8888"

# 摄像头源配置
sources:
  # 小米摄像头4 - 主码流（高清）
  xiaomi_cam_main:
    - url: rtsp://admin:password@192.168.1.100:554/stream
      # 使用硬件加速
      hw: true

  # 小米摄像头4 - 子码流（流畅）
  xiaomi_cam_sub:
    - url: rtsp://admin:password@192.168.1.100:554/substream

# 流输出配置
streams:
  # 默认流（供Python使用）
  xiaomi_cam:
    - source: xiaomi_cam_main

# 录制配置（可选）
record:
  # 录制目录
  directory: "./recordings"
  # 每个文件最大时长（秒）
  duration: 300
```

### 3. 重启go2rtc

#### Docker
```bash
docker restart go2rtc
```

#### 系统服务
```bash
sudo systemctl restart go2rtc
```

#### 二进制
```bash
# 停止旧进程
pkill go2rtc

# 启动新进程
go2rtc -c /path/to/go2rtc.yaml
```

---

## 项目配置

### 1. 修改项目配置文件

编辑 `config/default.yaml`：

```yaml
# 摄像头配置
camera:
  # 摄像头类型：usb、rtsp 或 go2rtc
  type: go2rtc
  # 视频分辨率（小米摄像头4支持2K）
  width: 1920
  height: 1080
  # 帧率
  fps: 30
  # 缓冲区大小
  buffer_size: 1

# go2rtc配置
go2rtc:
  # go2rtc服务器地址
  host: "localhost"
  # RTSP端口（默认8554）
  rtsp_port: 8554
  # API端口（默认1984）
  api_port: 1984
  # WebRTC端口（默认8888）
  webrtc_port: 8888
  # 摄像头名称（在go2rtc.yaml中配置的stream名称）
  camera_name: "xiaomi_cam"
  # 使用WebRTC流（更低延迟）还是RTSP流
  use_webrtc: false
  # RTSP认证信息（如果需要）
  username: null
  password: null
```

### 2. 配置说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `host` | go2rtc服务器地址 | localhost |
| `rtsp_port` | RTSP服务端口 | 8554 |
| `api_port` | API管理端口 | 1984 |
| `camera_name` | 在go2rtc中配置的流名称 | xiaomi_cam |
| `use_webrtc` | 是否使用WebRTC流（实验性） | false |

---

## 使用方法

### 方法一：使用工厂函数创建摄像头

```python
from src.config import load_config
from src.core.camera import create_camera_from_config

# 加载配置
config = load_config()

# 创建摄像头实例
camera = create_camera_from_config(config)

# 启动摄像头
if camera.start():
    print("摄像头启动成功！")
    print(f"配置信息: {camera.get_config_info()}")

    # 读取帧
    while True:
        ret, frame = camera.read()
        if ret:
            cv2.imshow('go2rtc Camera', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    camera.stop()
    cv2.destroyAllWindows()
```

### 方法二：直接创建Go2RTCCamera

```python
from src.core.camera import Go2RTCCamera, Go2RTCConfig

# 创建配置
config = Go2RTCConfig(
    host="localhost",
    camera_name="xiaomi_cam",
    use_webrtc=False
)

# 创建摄像头
camera = Go2RTCCamera(
    config=config,
    width=1920,
    height=1080,
    fps=30
)

# 启动摄像头
if camera.start():
    print("摄像头启动成功！")

    # 检查连接状态
    status = camera.get_stream_status()
    print(f"流状态: {status}")

    # 读取帧
    while True:
        ret, frame = camera.read()
        if ret:
            cv2.imshow('go2rtc Camera', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    camera.stop()
    cv2.destroyAllWindows()
```

### 方法三：使用主程序

```bash
# 使用默认配置启动
python src/main.py

# 指定配置文件启动
python src/main.py --config config/custom_config.yaml
```

---

## 故障排查

### 问题1：无法连接到go2rtc服务器

**症状**：
```
警告: 无法连接到go2rtc服务器 localhost
```

**解决方案**：
1. 检查go2rtc是否运行
   ```bash
   # 检查Docker容器
   docker ps | grep go2rtc

   # 或检查进程
   ps aux | grep go2rtc
   ```

2. 检查端口是否被占用
   ```bash
   # Windows
   netstat -an | findstr "1984"

   # Linux/Mac
   lsof -i :1984
   ```

3. 测试Web界面
   ```
   http://localhost:1984
   ```

### 问题2：摄像头流无法打开

**症状**：
```
无法打开流: rtsp://localhost:8554/xiaomi_cam
```

**解决方案**：
1. 检查go2rtc配置中的摄像头名称是否正确

2. 在go2rtc Web界面查看流状态
   ```
   http://localhost:1984
   ```

3. 测试原始RTSP流
   ```bash
   ffplay -rtsp_transport tcp rtsp://admin:password@192.168.1.100:554/stream
   ```

4. 检查网络连接
   ```bash
   ping 192.168.1.100
   ```

### 问题3：帧率低或延迟高

**症状**：视频卡顿、延迟明显

**解决方案**：
1. 使用子码流（降低分辨率）
   ```yaml
   sources:
     xiaomi_cam:
       - url: rtsp://admin:password@192.168.1.100:554/substream
   ```

2. 减小缓冲区
   ```yaml
   camera:
     buffer_size: 1
   ```

3. 使用TCP传输
   ```python
   import os
   os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
   ```

### 问题4：认证失败

**症状**：
```
无法打开流: rtsp://username:password@localhost:8554/xiaomi_cam
```

**解决方案**：
1. 在配置文件中添加认证信息
   ```yaml
   go2rtc:
     username: "admin"
     password: "123456"
   ```

2. 或在go2rtc.yaml中配置认证
   ```yaml
   sources:
     xiaomi_cam:
       - url: rtsp://admin:password@192.168.1.100:554/stream
   ```

---

## 性能优化建议

### 1. 选择合适的码流

| 码流类型 | 分辨率 | 帧率 | 适用场景 |
|---------|-------|------|----------|
| 主码流 | 2K/1080p | 20-30fps | AI检测、录制 |
| 子码流 | 720p/480p | 15-25fps | 实时预览、远程查看 |

### 2. 调整缓冲区

```yaml
camera:
  # 实时场景（低延迟）
  buffer_size: 1

  # 录制场景（更流畅）
  buffer_size: 3
```

### 3. 使用硬件加速

```yaml
# go2rtc.yaml
sources:
  xiaomi_cam:
    - url: rtsp://admin:password@192.168.1.100:554/stream
      hw: true  # 启用硬件加速
```

---

## 多摄像头配置

如果有多只猫需要监控，可以配置多个摄像头：

### go2rtc配置
```yaml
sources:
  # 猫厕所1
  litter_box_1:
    - url: rtsp://admin:password@192.168.1.100:554/stream

  # 猫厕所2
  litter_box_2:
    - url: rtsp://admin:password@192.168.1.101:554/stream

streams:
  litter_box_1:
    - source: litter_box_1
  litter_box_2:
    - source: litter_box_2
```

### Python代码
```python
from src.core.camera import Go2RTCCamera, Go2RTCConfig

# 创建多个摄像头
cameras = []

for i in range(1, 3):
    config = Go2RTCConfig(
        host="localhost",
        camera_name=f"litter_box_{i}"
    )
    camera = Go2RTCCamera(config=config)
    camera.start()
    cameras.append(camera)

# 同时读取多个摄像头
while True:
    for i, camera in enumerate(cameras):
        ret, frame = camera.read()
        if ret:
            cv2.imshow(f'Camera {i+1}', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

for camera in cameras:
    camera.stop()
```

---

## 参考资源

- go2rtc GitHub: https://github.com/AlexxIT/go2rtc
- go2rtc Wiki: https://github.com/AlexxIT/go2rtc/wiki
- 小米摄像头RTSP配置: [米家APP帮助文档]

---

## 更新日志

- 2026-03-04: 初始版本，支持小米摄像头4通过go2rtc接入
