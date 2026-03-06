# 猫咪监控项目 - 内存优化方案

## 问题分析

### 当前内存占用
- 视频帧：848×480×3 = 1.2MB/帧
- 帧率：20 fps
- 每秒帧数据：24MB
- YOLO 模型：~200-500MB（GPU）
- 总计：**可能 1-2GB+**

### 根本原因
1. **持续帧复制** - `update_frame()` 每帧都 `copy()`
2. **无连接时仍在复制** - 没有客户端也在更新帧
3. **高分辨率** - 848×480 对猫检测来说过高
4. **无跳帧** - `process_every_n_frames: 1` 每帧都处理

---

## 优化方案

### 方案 1: 条件性帧更新 ⭐ 推荐优先
**修改文件**: `src/web/app.py`

只在有客户端连接时更新帧：

```python
class WebApp:
    def __init__(self, ...):
        self.active_clients = 0  # 添加客户端计数

    def _generate_frames(self):
        self.active_clients += 1  # 客户端连接
        try:
            while True:
                if self.system_state['frame'] is not None:
                    ret, buffer = cv2.imencode('.jpg', self.system_state['frame'],
                                             [cv2.IMWRITE_JPEG_QUALITY, 70])  # 降低质量
                    if ret:
                        frame = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        finally:
            self.active_clients -= 1  # 客户端断开

    def update_frame(self, frame: np.ndarray) -> None:
        # 只在有客户端时更新
        if self.active_clients > 0:
            self.system_state['frame'] = frame.copy()
```

**效果**: 无客户端时内存占用减少 ~1.2MB×20fps = 24MB/s

---

### 方案 2: 降低分辨率
**修改文件**: `config/default.yaml`

```yaml
camera:
  width: 640    # 从 848 降到 640
  height: 360   # 从 480 降到 360
```

**效果**:
- 帧大小：640×360×3 = 691KB ≈ **减少 43%**
- 推理速度提升 ~40%
- 对猫检测精度影响很小

---

### 方案 3: 增加跳帧
**修改文件**: `config/default.yaml`

```yaml
system:
  process_every_n_frames: 3  # 从 1 改为 3
```

**效果**: CPU/内存占用减少 66%

---

### 方案 4: 降低帧率
**修改文件**: `config/default.yaml`

```yaml
camera:
  fps: 10  # 从 20 降到 10
```

**效果**: 数据量减少 50%

---

## 组合优化效果预估

| 方案 | 内存减少 | CPU减少 | 实施难度 |
|------|---------|---------|---------|
| 方案1（条件更新）| ~50%* | ~30% | 中（需改代码）|
| 方案2（降分辨率）| ~43% | ~40% | 低（改配置）|
| 方案3（跳帧）| ~66% | ~66% | 低（改配置）|
| 方案4（降帧率）| ~50% | ~50% | 低（改配置）|

*仅在无客户端连接时

---

## 推荐实施顺序

1. **先做简单配置优化**（方案2+3+4）- 立即见效
2. **再做代码优化**（方案1）- 进一步优化

预期总效果：**内存占用降低 70-80%**

---

## 验证方法

```bash
# 运行前监控内存
nvidia-smi -l 1  # GPU显存
tasklist /fi "imagename eq python.exe"  # 进程内存

# 运行后对比
```
