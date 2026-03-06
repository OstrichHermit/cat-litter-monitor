# 多ROI功能使用说明

## 概述

猫咪监控系统现在支持多个ROI（感兴趣区域）检测，可以同时监控多个猫砂盆。

## 主要变化

### 1. 配置文件格式

**旧格式（单个ROI）：**
```yaml
roi:
  type: rectangle
  rectangle:
    x: 369
    y: 122
    width: 168
    height: 303
  min_frames_in_roi: 15
  exit_delay_frames: 30
```

**新格式（多个ROI）：**
```yaml
roi:
  rois:
    - id: 1
      name: "猫砂盆1"
      type: "rectangle"
      rectangle:
        x: 369
        y: 122
        width: 168
        height: 303
    - id: 2
      name: "猫砂盆2"
      type: "rectangle"
      rectangle:
        x: 100
        y: 100
        width: 200
        height: 200
  min_frames_in_roi: 15
  exit_delay_frames: 30
```

### 2. 向后兼容

系统自动支持旧格式的配置文件。如果使用旧格式，系统会将其转换为单ROI的MultiROI对象。

## 使用方法

### 1. 标注多个ROI

运行标注脚本：
```bash
python scripts/annotate_roi_go2rtc.py
```

**按键操作：**
- `n`: 完成当前ROI，开始绘制下一个ROI
- `r`: 切换到矩形模式（应用到当前正在绘制的ROI）
- `p`: 切换到多边形模式（应用到当前正在绘制的ROI）
- `c`: 清除当前ROI
- `a`: 清除所有ROI
- `s`: 保存所有ROI并退出
- `q`: 退出不保存

### 2. 测试ROI配置

运行测试脚本验证配置：
```bash
python scripts/test_multi_roi.py
```

### 3. 启动监控系统

```bash
python src/main.py
```

## 技术细节

### 代码变更

1. **behavior_analyzer.py**
   - 添加了 `MultiROI` 类来管理多个ROI区域
   - `LitterEvent` 添加了 `roi_id` 字段
   - `BehaviorAnalyzer` 使用 `MultiROI` 替代单个 `ROI`

2. **database.py**
   - `litter_records` 表添加了 `roi_id` 字段
   - `insert_litter_record` 添加了 `roi_id` 参数

3. **main.py**
   - 支持新旧两种配置格式的加载
   - 自动将旧格式转换为MultiROI对象

4. **annotate_roi_go2rtc.py**
   - 完全重写以支持多个ROI的标注
   - 可以连续标注多个ROI区域

### 检测逻辑

- 使用检测框的中心点判断是否在ROI内
- 点在任一ROI内即触发检测
- 每个ROI独立检测和计数
- 事件记录包含 `roi_id` 字段，标识是哪个猫砂盆

### 可视化

不同的ROI会使用不同的颜色显示：
- ROI 1: 绿色
- ROI 2: 蓝色
- ROI 3: 红色
- ROI 4: 青色
- ROI 5: 品红色

## 数据库结构

`litter_records` 表新增字段：
```sql
ALTER TABLE litter_records ADD COLUMN roi_id INTEGER DEFAULT 1;
```

## 常见问题

### Q: 如何从旧版本升级？

A: 直接运行新版本即可。系统会自动读取旧格式的配置并转换。如需使用多ROI功能，请运行标注工具重新配置。

### Q: 可以混合使用矩形和多边形ROI吗？

A: 可以。每个ROI可以独立选择矩形或多边形类型。

### Q: 如何查看某个猫砂盆的使用记录？

A: 在数据库查询时添加 `roi_id` 过滤条件即可。

### Q: 最多支持多少个ROI？

A: 理论上没有限制，但建议不超过5个以保证系统性能。

## 注意事项

1. 确保每个ROI区域之间有足够的间隔，避免误检
2. 标注时请确保摄像头位置固定
3. 修改ROI配置后需要重启监控系统才能生效
4. 数据库中的历史记录不会自动更新ROI ID
