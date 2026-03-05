# 追踪器改进说明

## 修改日期
2026-03-06

## 修改内容

### 1. 算法替换
- **原算法**: DeepSORT（基于马氏距离 + ReID特征）
- **新算法**: 基于IOU的简化追踪算法

### 2. 修改的文件

#### `D:\AgentWorkspace\cat-litter-monitor\src\core\object_tracker.py`
主要改进：
- 移除了复杂的特征提取和马氏距离计算
- 使用匈牙利算法进行最优IOU匹配
- 添加边界框平滑（指数移动平均，alpha=0.3）
- 改进匹配策略：对未匹配的track使用降低的IOU阈值再次尝试匹配
- 优化track状态管理：TENTATIVE状态给3次机会
- 添加调试信息输出

#### `D:\AgentWorkspace\cat-litter-monitor\config\default.yaml`
配置调整：
- `max_distance: 0.7 → 0.2`（IOU阈值，20%重叠即可匹配）
- 保留 `max_iou_distance` 参数（不使用，保持兼容性）

### 3. 技术细节

#### IOU匹配算法
```python
# 1. 计算所有检测和tracks的IOU矩阵
iou_matrix = compute_iou_matrix(detection_boxes, track_boxes)

# 2. 使用匈牙利算法找最优匹配
cost_matrix = 1.0 - iou_matrix
row_indices, col_indices = linear_sum_assignment(cost_matrix)

# 3. 根据IOU阈值过滤匹配
if iou >= iou_threshold:
    matches.append((track_idx, detection_idx))
```

#### 边界框平滑
```python
# 使用指数移动平均减少抖动
alpha = 0.3
self.bbox = alpha * new_bbox + (1 - alpha) * self.bbox
```

#### 两阶段匹配
1. **第一阶段**: 使用标准IOU阈值（0.2）匹配
2. **第二阶段**: 对未匹配的track使用降低的阈值（0.1）再次尝试

### 4. 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_distance` | 0.2 | IOU匹配阈值（20%重叠） |
| `max_disappeared` | 30 | 最大消失帧数 |
| `min_confidence` | 0.3 | 最小置信度 |

### 5. 测试方法

#### 方法1：运行测试脚本
```bash
python scripts/test_tracker.py
```

#### 方法2：查看运行日志
重启服务后，观察日志中的调试信息：
```
[ObjectTracker] 活跃Track数: X, 检测数: Y, 匹配数: Z, 新Track: W, IOU阈值: 0.20
```

**成功指标**：
- 活跃Track数应该稳定在1-2个
- 新Track数量应该很少
- 同一只猫的Track ID应该保持不变

### 6. 预期效果

**改进前**：
- 每次检测都创建新track（ID 1-17）
- 无法稳定追踪同一只猫

**改进后**：
- 同一只猫保持1个稳定的track ID
- 即使猫伸展/蜷缩也能正确追踪
- 多只猫能正确区分

### 7. 已知限制

1. **快速移动**: 如果猫移动非常快（>30px/帧），可能创建临时track
2. **长时间遮挡**: 超过30帧未检测到会删除track
3. **IOU阈值**: 0.2的阈值是经验值，可能需要根据实际情况调整

### 8. 调优建议

如果追踪效果不理想，可以调整以下参数：

```yaml
tracking:
  max_distance: 0.2  # 降低阈值（如0.15）更严格，提高阈值（如0.3）更宽松
  max_disappeared: 30  # 增加此值可以让track存活更长时间
  min_confidence: 0.3  # 提高此值可以过滤低质量检测
```

## 验证步骤

1. **运行测试脚本**
   ```bash
   python scripts/test_tracker.py
   ```
   预期结果：所有测试通过（✓）

2. **重启监控系统**
   ```bash
   python src/main.py
   ```

3. **观察日志**
   - 查看track ID数量是否稳定
   - 确认没有大量创建新track

4. **验证实际效果**
   - 同一只猫应该保持相同track ID
   - 猫伸展/蜷缩时track ID不变
   - 多只猫有不同track ID

## 总结

这次改进将复杂的DeepSORT算法替换为简单但更稳定的IOU匹配算法，更适合猫厕所监控这种场景。新算法：
- ✅ 更简单（无需ReID特征）
- ✅ 更稳定（IOU匹配对形状变化更鲁棒）
- ✅ 更高效（计算量更小）
- ✅ 可维护（代码更清晰）
