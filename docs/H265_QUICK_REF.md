# H265 解码器配置快速参考

## 快速配置

### 1. 配置文件设置

在 `config/default.yaml` 中设置：

```yaml
go2rtc:
  # ... 其他配置 ...
  decoder: auto  # 推荐使用 auto
```

### 2. 可选的解码器值

| 值 | 说明 | 推荐场景 |
|---|---|---|
| `auto` | 自动选择（默认） | **大多数情况** |
| `hevc` | 软件解码 | 兼容性问题、无硬件加速 |
| `hevc_qsv` | Intel QuickSync | Intel CPU |
| `hevc_cuvid` | NVIDIA CUDA | NVIDIA GPU |
| `hevc_amf` | AMD AMF | AMD GPU |

## 测试命令

### 测试自动解码器
```bash
python test_h265_decode.py --decoder auto
```

### 测试所有解码器
```bash
python test_h265_decode.py --all
```

### 测试特定解码器
```bash
python test_h265_decode.py --decoder hevc_qsv
```

### 自定义测试时长
```bash
python test_h265_decode.py --decoder auto --duration 20
```

## 故障排除

### 问题：解码器不可用
```
No such device
```
**解决**：使用 `decoder: hevc` 回退到软件解码

### 问题：仍然有解码错误
```
Could not find ref with POC 0
```
**解决**：
1. 检查网络连接
2. 尝试不同解码器
3. 查看详细日志

### 问题：启动失败
**解决**：
1. 检查 `ffmpeg_path` 配置
2. 确认 go2rtc 正在运行
3. 验证 RTSP 流地址

## 性能对比

| 解码器 | CPU | GPU | 延迟 | 兼容性 |
|---|---|---|---|---|
| hevc | 高 | 无 | 中 | ⭐⭐⭐⭐⭐ |
| hevc_qsv | 低 | 中 | 低 | ⭐⭐⭐⭐ |
| hevc_cuvid | 低 | 中 | 低 | ⭐⭐⭐⭐ |
| hevc_amf | 低 | 中 | 低 | ⭐⭐⭐⭐ |

## 关键改进

✅ 硬件加速支持
✅ 自动回退机制
✅ 错误恢复标志
✅ 降低延迟
✅ 提高稳定性

## 推荐配置

**Windows + Intel CPU**
```yaml
decoder: auto  # 或 hevc_qsv
```

**Windows + NVIDIA GPU**
```yaml
decoder: auto  # 或 hevc_cuvid
```

**未知硬件**
```yaml
decoder: auto  # 自动回退到软件解码
```

## 详细文档

查看 `docs/H265_DECODE_FIX.md` 了解完整的技术细节。
