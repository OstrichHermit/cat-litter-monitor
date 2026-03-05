# 追踪器修复快速参考

## 一句话总结
**通过缩短track生命周期（30→10帧）和添加智能去重机制（IOU>0.7），解决了一猫多ID交替的问题。**

## 关键修改
```python
# 1. 缩短track生命周期
max_disappeared: 30 → 10

# 2. 添加重复检测
if IOU > 0.7:
    删除hits更少的track

# 3. 完善日志
print → logger
```

## 验证方法
```bash
# 运行测试
python test_tracking_fix.py

# 观察日志
python src/main.py
grep "移除重复track" logs/litter_monitor.log
```

## 预期效果
✓ 只有一个稳定的Track ID
✓ 不再出现ID交替
✓ 日志显示去重操作

## 参数调整
```yaml
tracking:
  max_disappeared: 5-15    # 推荐10
  max_distance: 0.2-0.5    # 推荐0.2
```

## 关键日志
```
✓ 正常: "匹配=[1(IOU=0.85)]"
⚠ 去重: "移除重复track 6 (与track 1 IOU=0.75)"
❌ 异常: "检测到多个已确认track: ID=1, ID=6, ID=18"
```

## 问题排查
| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 仍有多个ID | max_distance太低 | 调整到0.3 |
| 频繁去重 | 检测不稳定 | 检查检测器 |
| ID频繁切换 | max_disappeared太长 | 降到5 |

## 文件清单
- `src/core/object_tracker.py` - 核心修复
- `config/default.yaml` - 配置更新
- `test_tracking_fix.py` - 测试脚本
- `TRACKING_FIX_SUMMARY.md` - 详细说明

---
**状态**: ✅ 已完成并测试通过
