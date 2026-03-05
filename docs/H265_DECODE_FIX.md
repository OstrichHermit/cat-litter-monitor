# H265 解码问题修复说明

## 问题描述

在使用小米摄像头 4 通过 go2rtc 获取 H265 视频流时，FFmpeg 的 H265 解码器产生大量解码错误：

```
Could not find ref with POC 0
Error constructing the frame RPS.
Skipping invalid undecodable NALU: 1
```

这些错误导致：
- 视频帧无法正常解码
- 严重卡顿和延迟
- 画面花屏或完全黑屏

## 根本原因

1. **非标准 H265 编码**：小米摄像头的 H265 编码不符合标准规范
2. **关键帧丢失**：I 帧间隔不合理，导致解码器无法建立正确的参考关系
3. **时间戳异常**：PTS/DTS 不连续，解码器无法正确同步
4. **NALU 单元损坏**：网络传输或编码问题导致 NALU 单元损坏

## 解决方案

### 1. 多解码器支持（2026-03-05）

#### 实现的功能

1. **硬件加速解码器支持**
   - Intel QuickSync (hevc_qsv)
   - NVIDIA CUDA (hevc_cuvid)
   - AMD AMF (hevc_amf)

2. **软件解码器回退**
   - 硬件解码失败时自动回退到软件解码
   - 保证兼容性和稳定性

3. **错误恢复机制**
   - 添加 FFmpeg 错误恢复标志
   - 自动跳过损坏的数据包
   - 生成时间戳，忽略 DTS 异常

#### 修改的文件

**D:/AgentWorkspace/cat-litter-monitor/src/core/camera.py**

1. **新增 Go2RTCConfig.decoder 属性**
   ```python
   decoder: str = "auto"  # 解码器配置
   ```

2. **重写 _build_ffmpeg_command() 方法**
   - 支持多种解码器参数
   - 添加错误恢复标志：
     - `-err_detect ignore_err`
     - `-fflags +genpts+igndts`
     - `-fflags +discardcorrupt`
     - `-max_delay 0`

3. **添加解码器回退机制**
   - 自动尝试多种解码器
   - 监控解码错误数量
   - 自动切换到下一个解码器

4. **更新配置文件**
   - `config/default.yaml` 添加 `decoder` 配置项

### 2. 配置选项

#### decoder 参数说明

| 值 | 说明 | 适用场景 |
|---|---|---|
| `auto` | 自动选择（默认） | 系统自动选择最佳解码器 |
| `hevc` | 软件 H265 解码 | 兼容性最好，CPU 占用高 |
| `hevc_qsv` | Intel QuickSync | Intel CPU，低 CPU 占用 |
| `hevc_cuvid` | NVIDIA CUDA | NVIDIA GPU，低 CPU 占用 |
| `hevc_amf` | AMD AMF | AMD GPU，低 CPU 占用 |

#### 配置示例

**config/default.yaml**
```yaml
go2rtc:
  # ... 其他配置 ...
  decoder: auto  # 或指定具体解码器
```

### 3. 工作流程

```
启动摄像头
    │
    ├─ use_ffmpeg = True
    │   │
    │   ├─ 尝试解码器 1: hevc_qsv (Intel QuickSync)
    │   │   ├─ 成功 → 启动成功 ✓
    │   │   └─ 失败（硬件不可用/大量错误）
    │   │       └─ 尝试下一个解码器
    │   │
    │   ├─ 尝试解码器 2: hevc (软件解码)
    │   │   ├─ 成功 → 启动成功 ✓
    │   │   └─ 失败
    │   │       └─ 返回失败
    │   │
    │   └─ 监控解码错误
    │       ├─ 错误数量 > 10
    │       │   └─ 尝试下一个解码器
    │       └─ 错误数量正常
    │           └─ 继续运行
    │
    └─ use_ffmpeg = False
        └─ OpenCV 直接读取（需要 H264 编码）
```

### 4. FFmpeg 命令详解

#### 优化后的命令结构

```bash
ffmpeg \
  -rtsp_transport tcp \                    # TCP 传输（更稳定）
  -err_detect ignore_err \                 # 忽略解码错误
  -fflags +genpts+igndts \                 # 生成 PTS，忽略 DTS
  -max_delay 0 \                           # 最小化延迟
  -fflags +discardcorrupt \                # 丢弃损坏数据包
  -avioflags direct \                      # 减少缓冲延迟
  -probesize 32 \                          # 减小探测大小
  -analyzeduration 1000000 \               # 减小分析时间
  -c:v hevc_qsv \                          # 解码器（可变）
  -i rtsp://localhost:8554/micam1 \        # 输入流
  -c:v rawvideo \                          # 不重新编码
  -pix_fmt bgr24 \                         # BGR 格式
  -f rawvideo \                            # 原始视频输出
  -an \                                    # 禁用音频
  -                                        # 输出到 stdout
```

#### 关键参数说明

| 参数 | 作用 | 效果 |
|---|---|---|
| `-err_detect ignore_err` | 忽略解码错误 | 遇到错误继续播放 |
| `-fflags +genpts+igndts` | 生成 PTS，忽略 DTS | 解决时间戳问题 |
| `-fflags +discardcorrupt` | 丢弃损坏数据包 | 提高解码稳定性 |
| `-max_delay 0` | 最小化延迟 | 降低实时流延迟 |
| `-avioflags direct` | 直接 I/O | 减少缓冲延迟 |
| `-probesize 32` | 减小探测大小 | 加快启动速度 |
| `-analyzeduration 1000000` | 减小分析时间 | 加快启动速度 |

### 5. 测试和验证

#### 测试步骤

1. **测试硬件解码器**
   ```bash
   # 检查 Intel QuickSync 可用性
   ffmpeg -hwaccels | grep qsv

   # 检查 NVIDIA CUDA 可用性
   ffmpeg -hwaccels | grep cuda

   # 检查 AMD AMF 可用性
   ffmpeg -hwaccels | grep d3d11va
   ```

2. **测试特定解码器**
   ```bash
   # 测试软件解码
   python test_camera.py --decoder hevc

   # 测试 Intel QuickSync
   python test_camera.py --decoder hevc_qsv

   # 测试 NVIDIA CUDA
   python test_camera.py --decoder hevc_cuvid
   ```

3. **监控解码质量**
   - 观察 FFmpeg 日志输出
   - 检查错误数量
   - 监控 CPU/GPU 占用率

#### 性能对比

| 解码器 | CPU 占用 | GPU 占用 | 延迟 | 兼容性 |
|---|---|---|---|---|
| hevc (软件) | 高 | 无 | 中 | 最好 |
| hevc_qsv | 低 | 中 | 低 | 好（Intel） |
| hevc_cuvid | 低 | 中 | 低 | 好（NVIDIA） |
| hevc_amf | 低 | 中 | 低 | 好（AMD） |

### 6. 故障排除

#### 问题 1：硬件解码器不可用

**症状**：
```
No such device
Could not find codec parameters for stream
```

**解决**：
- 检查硬件驱动是否安装
- 使用 `decoder: hevc` 回退到软件解码
- 更新 FFmpeg 到最新版本

#### 问题 2：仍然有解码错误

**症状**：
```
Could not find ref with POC 0
```

**解决**：
- 确认配置了错误恢复标志
- 尝试不同的解码器
- 检查网络连接稳定性
- 考虑使用 go2rtc 的转码功能（H265 → H264）

#### 问题 3：启动失败

**症状**：
```
FFmpeg进程启动失败
```

**解决**：
- 检查 `ffmpeg_path` 配置
- 确认 FFmpeg 可执行文件存在
- 检查 RTSP 流地址是否正确
- 查看 go2rtc 日志

### 7. 未来改进方向

1. **动态解码器切换**
   - 运行时根据错误率自动切换解码器
   - 无需重启摄像头

2. **go2rtc 端转码**
   - 在 go2rtc 配置 H265 → H264 转码
   - 减少客户端解码负担

3. **性能优化**
   - 使用 zero-copy 技术减少内存拷贝
   - 优化帧缓冲区管理

4. **更智能的错误处理**
   - 关键帧检测和请求
   - 动态调整缓冲区大小

## 总结

这次修复通过以下方式解决了 H265 解码问题：

1. ✅ 添加硬件加速支持，降低 CPU 占用
2. ✅ 实现解码器自动回退，提高稳定性
3. ✅ 添加错误恢复标志，增强容错性
4. ✅ 优化 FFmpeg 参数，减少延迟
5. ✅ 保持向后兼容，支持配置选择

**推荐配置**：
- Windows + Intel CPU：使用 `decoder: auto` 或 `decoder: hevc_qsv`
- Windows + NVIDIA GPU：使用 `decoder: auto` 或 `decoder: hevc_cuvid`
- 未知硬件：使用 `decoder: auto`（自动回退）

## 更新日志

- **2026-03-05**: 初始版本，实现多解码器支持和错误恢复机制
