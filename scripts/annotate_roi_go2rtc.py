"""
ROI标注工具 - go2rtc版本

该脚本用于标注猫砂盆的ROI区域，支持go2rtc网络摄像头。
"""

import sys
import cv2
import numpy as np
import yaml
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.camera import Go2RTCConfig, Go2RTCCamera
from src.config import get_config


class ROIAnnotatorGo2RTC:
    """
    ROI标注工具类 - go2rtc版本

    用于交互式标注ROI区域。
    """

    def __init__(self):
        """
        初始化标注工具
        """
        self.points = []
        self.drawing = False
        self.roi_type = 'rectangle'  # rectangle 或 polygon

        # 加载配置
        self.config = get_config()
        go2rtc_config = self.config.get('go2rtc', {})
        camera_config = self.config.get('camera', {})

        # 创建go2rtc摄像头配置
        self.go2rtc_cfg = Go2RTCConfig(
            host=go2rtc_config.get('host', 'localhost'),
            rtsp_port=go2rtc_config.get('rtsp_port', 8554),
            api_port=go2rtc_config.get('api_port', 1984),
            webrtc_port=go2rtc_config.get('webrtc_port', 8888),
            camera_name=go2rtc_config.get('camera_name', 'micam1'),
            use_webrtc=go2rtc_config.get('use_webrtc', False)
        )

        # 创建摄像头实例
        self.camera = Go2RTCCamera(
            config=self.go2rtc_cfg,
            width=camera_config.get('width', 1280),
            height=camera_config.get('height', 720),
            fps=camera_config.get('fps', 30)
        )

    def start(self):
        """
        启动标注工具
        """
        print("=" * 50)
        print("ROI 标注工具 - go2rtc 版本")
        print("=" * 50)
        print("按键说明:")
        print("  r: 切换到矩形模式")
        print("  p: 切换到多边形模式")
        print("  c: 清除标注")
        print("  s: 保存并退出")
        print("  q: 退出不保存")
        print("  鼠标左键: 绘制ROI")
        print("  鼠标右键: 完成多边形")
        print("=" * 50)

        # 启动摄像头
        if not self.camera.start():
            print("无法启动摄像头")
            return

        print("摄像头已启动，正在获取视频流...")

        # 读取一帧作为背景
        ret, frame = self.camera.read_blocking(timeout=10)
        if not ret:
            print("无法读取帧")
            self.camera.stop()
            return

        print("视频帧已获取，开始标注...")

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
            mode_text = f"Mode: {self.roi_type} | Points: {len(self.points)}"
            cv2.putText(temp_frame, mode_text, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # 显示提示
            help_text = "Press 's' to save, 'q' to quit"
            cv2.putText(temp_frame, help_text, (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

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
        self.camera.stop()

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
                print(f"添加点: ({x}, {y})")
            else:
                # 多边形模式：记录顶点
                self.points.append([x, y])
                print(f"添加顶点: ({x}, {y})")

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
            if len(self.points) < 2:
                print("矩形需要两个点")
                return

            pt1 = self.points[0]
            pt2 = self.points[1]

            # 计算矩形参数
            x = min(pt1[0], pt2[0])
            y = min(pt1[1], pt2[1])
            width = abs(pt2[0] - pt1[0])
            height = abs(pt2[1] - pt1[1])

            config['roi']['type'] = 'rectangle'
            config['roi']['rectangle'] = {
                'x': x,
                'y': y,
                'width': width,
                'height': height
            }

            print(f"\n保存矩形ROI: x={x}, y={y}, width={width}, height={height}")

        else:  # polygon
            if len(self.points) < 3:
                print("多边形至少需要三个点")
                return

            config['roi']['type'] = 'polygon'
            config['roi']['polygon'] = self.points

            print(f"\n保存多边形ROI: {len(self.points)} 个顶点")

        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        print(f"ROI配置已保存到: {config_path}")


if __name__ == '__main__':
    annotator = ROIAnnotatorGo2RTC()
    annotator.start()
