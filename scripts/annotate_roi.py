"""
ROI标注工具

该脚本用于标注猫砂盆的ROI区域。
"""

import sys
import cv2
import numpy as np
import yaml
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ROIAnnotator:
    """
    ROI标注工具类

    用于交互式标注ROI区域。
    """

    def __init__(self, camera_id=0):
        """
        初始化标注工具

        Args:
            camera_id: 摄像头ID
        """
        self.camera_id = camera_id
        self.points = []
        self.drawing = False
        self.roi_type = 'rectangle'  # rectangle 或 polygon

    def start(self):
        """
        启动标注工具
        """
        print("ROI标注工具")
        print("按键说明:")
        print("  r: 切换到矩形模式")
        print("  p: 切换到多边形模式")
        print("  c: 清除标注")
        print("  s: 保存并退出")
        print("  q: 退出不保存")
        print("  鼠标左键: 绘制ROI")
        print("  鼠标右键: 完成多边形")

        # 打开摄像头
        cap = cv2.VideoCapture(self.camera_id)
        if not cap.isOpened():
            print("无法打开摄像头")
            return

        # 读取一帧作为背景
        ret, frame = cap.read()
        if not ret:
            print("无法读取帧")
            cap.release()
            return

        cap.release()

        # 创建窗口
        cv2.namedWindow('ROI Annotation')
        cv2.setMouseCallback('ROI Annotation', self.mouse_callback)

        display_frame = frame.copy()

        while True:
            # 绘制当前ROI
            temp_frame = display_frame.copy()

            if self.roi_type == 'rectangle' and len(self.points) >= 2:
                # 绘制矩形
                pt1 = tuple(self.points[0])
                pt2 = tuple(self.points[1])
                cv2.rectangle(temp_frame, pt1, pt2, (0, 255, 0), 2)

            elif self.roi_type == 'polygon' and len(self.points) >= 2:
                # 绘制多边形
                pts = np.array(self.points, np.int32)
                pts = pts.reshape((-1, 1, 2))
                cv2.polylines(temp_frame, [pts], True, (0, 255, 0), 2)

            # 显示模式
            mode_text = f"Mode: {self.roi_type}"
            cv2.putText(temp_frame, mode_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # 显示帧
            cv2.imshow('ROI Annotation', temp_frame)

            # 处理按键
            key = cv2.waitKey(1) & 0xFF

            if key == ord('r'):
                self.roi_type = 'rectangle'
                self.points = []
                print("切换到矩形模式")
            elif key == ord('p'):
                self.roi_type = 'polygon'
                self.points = []
                print("切换到多边形模式")
            elif key == ord('c'):
                self.points = []
                print("清除标注")
            elif key == ord('s'):
                self.save_roi()
                break
            elif key == ord('q'):
                print("退出不保存")
                break

        cv2.destroyAllWindows()

    def mouse_callback(self, event, x, y, flags, param):
        """
        鼠标回调函数

        Args:
            event: 鼠标事件
            x: X坐标
            y: Y坐标
            flags: 标志
            param: 参数
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.roi_type == 'rectangle':
                # 矩形模式：记录两个点
                if len(self.points) >= 2:
                    self.points = []
                self.points.append([x, y])
            else:
                # 多边形模式：记录顶点
                self.points.append([x, y])

        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.roi_type == 'polygon':
                # 完成多边形
                pass

    def save_roi(self):
        """
        保存ROI配置
        """
        if not self.points:
            print("没有标注ROI")
            return

        # 加载现有配置
        config_path = project_root / 'config' / 'default.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 更新ROI配置
        if self.roi_type == 'rectangle':
            if len(self.points) >= 2:
                pt1 = self.points[0]
                pt2 = self.points[1]
                x = min(pt1[0], pt2[0])
                y = min(pt1[1], pt2[1])
                w = abs(pt2[0] - pt1[0])
                h = abs(pt2[1] - pt1[1])

                config['roi']['type'] = 'rectangle'
                config['roi']['rectangle'] = {'x': x, 'y': y, 'width': w, 'height': h}
                print(f"保存矩形ROI: x={x}, y={y}, width={w}, height={h}")

        elif self.roi_type == 'polygon':
            if len(self.points) >= 3:
                config['roi']['type'] = 'polygon'
                config['roi']['polygon'] = self.points
                print(f"保存多边形ROI: {len(self.points)} 个顶点")

        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        print(f"ROI配置已保存到: {config_path}")


def main():
    """
    主函数
    """
    import argparse

    parser = argparse.ArgumentParser(description='ROI标注工具')
    parser.add_argument(
        '--camera-id',
        type=int,
        default=0,
        help='摄像头ID'
    )

    args = parser.parse_args()

    # 创建标注工具
    annotator = ROIAnnotator(camera_id=args.camera_id)
    annotator.start()


if __name__ == '__main__':
    main()
