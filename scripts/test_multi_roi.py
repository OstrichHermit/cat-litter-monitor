"""
多ROI配置测试脚本

用于测试多ROI功能是否正常工作。
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.behavior_analyzer import ROI, MultiROI
from src.config import get_config


def test_multi_roi():
    """测试多ROI功能"""
    print("=" * 50)
    print("多ROI配置测试")
    print("=" * 50)

    # 加载配置
    config = get_config()
    roi_config = config.get('roi', {})

    # 检查配置格式
    if 'rois' in roi_config:
        print(f"\n✅ 新格式：发现 {len(roi_config['rois'])} 个ROI区域")

        for i, roi_data in enumerate(roi_config['rois'], 1):
            print(f"\nROI {i}:")
            print(f"  ID: {roi_data['id']}")
            print(f"  名称: {roi_data['name']}")
            print(f"  类型: {roi_data['type']}")

            if roi_data['type'] == 'rectangle':
                rect = roi_data['rectangle']
                print(f"  矩形: x={rect['x']}, y={rect['y']}, "
                      f"width={rect['width']}, height={rect['height']}")
            elif roi_data['type'] == 'polygon':
                poly = roi_data['polygon']
                print(f"  多边形顶点数: {len(poly)}")

        # 创建MultiROI对象
        rois_list = []
        for roi_data in roi_config['rois']:
            if roi_data['type'] == 'rectangle':
                rect = roi_data['rectangle']
                roi = ROI(
                    roi_type='rectangle',
                    rectangle=[rect['x'], rect['y'], rect['width'], rect['height']]
                )
            else:
                roi = ROI(
                    roi_type='polygon',
                    polygon=roi_data['polygon']
                )
            rois_list.append(roi)

        multi_roi = MultiROI(rois_list)

        # 测试点是否在ROI内
        print("\n" + "=" * 50)
        print("测试点是否在ROI内:")
        print("=" * 50)

        test_points = [
            (400, 250),
            (200, 200),
            (600, 300)
        ]

        for point in test_points:
            in_any = multi_roi.contains_any(point)
            roi_id = multi_roi.get_roi_id(point)
            print(f"点 {point}: 在任一ROI内={in_any}, ROI ID={roi_id}")

    elif roi_config.get('type'):
        print("\n⚠️  旧格式：发现单个ROI配置")
        print(f"  类型: {roi_config['type']}")

        if roi_config['type'] == 'rectangle':
            rect = roi_config['rectangle']
            print(f"  矩形: x={rect['x']}, y={rect['y']}, "
                  f"width={rect['width']}, height={rect['height']}")
        elif roi_config['type'] == 'polygon':
            poly = roi_config['polygon']
            print(f"  多边形顶点数: {len(poly)}")

        print("\n💡 提示：请运行 annotate_roi_go2rtc.py 来标注多个ROI区域")

    else:
        print("\n❌ 未找到ROI配置")

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)


if __name__ == '__main__':
    test_multi_roi()
