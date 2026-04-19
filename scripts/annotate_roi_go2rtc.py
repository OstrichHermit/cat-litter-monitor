"""
ROI标注工具 - go2rtc版本

该脚本用于标注猫砂盆的ROI区域，支持go2rtc网络摄像头。
现在支持标注多个ROI区域（多个猫砂盆）。
"""

import sys
import cv2
import numpy as np
import yaml
from pathlib import Path
from typing import List, Dict, Optional

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.camera import Go2RTCConfig, Go2RTCCamera
from src.config import get_config

# 窗口最大尺寸限制
MAX_DISPLAY_WIDTH = 1280
MAX_DISPLAY_HEIGHT = 720


class SingleROI:
    """单个ROI区域的数据结构"""

    def __init__(self, roi_id: int, name: str, roi_type: str = 'rectangle'):
        self.id = roi_id
        self.name = name
        self.type = roi_type
        self.points = []
        self.rectangle = None
        self.polygon = None


class ROIAnnotatorGo2RTC:
    """
    ROI标注工具类 - go2rtc版本

    用于交互式标注多个ROI区域。
    """

    def __init__(self):
        """
        初始化标注工具
        """
        self.rois: List[SingleROI] = []
        self.current_roi_index = 0
        self.drawing = False
        self.display_scale = 1.0  # 显示缩放比例

        # 加载配置
        self.config = get_config()
        go2rtc_config = self.config.get('go2rtc', {})
        camera_config = self.config.get('camera', {})

        # 创建go2rtc摄像头配置
        self.go2rtc_cfg = Go2RTCConfig(
            host=go2rtc_config.get('host', 'localhost'),
            rtsp_port=go2rtc_config.get('rtsp_port', 8554),
            api_port=go2rtc_config.get('api_port', 1984),
            camera_name=go2rtc_config.get('camera_name', 'micam1')
        )

        # 创建摄像头实例
        self.camera = Go2RTCCamera(
            config=self.go2rtc_cfg,
            width=camera_config.get('width', 1280),
            height=camera_config.get('height', 720),
            fps=camera_config.get('fps', 30)
        )

        # 加载现有的ROI配置
        self.load_existing_rois()

    def load_existing_rois(self):
        """加载现有的ROI配置"""
        roi_config = self.config.get('roi', {})

        # 检查是否是新的多ROI格式
        if 'rois' in roi_config:
            # 新格式
            for roi_data in roi_config['rois']:
                roi = SingleROI(
                    roi_id=roi_data['id'],
                    name=roi_data['name'],
                    roi_type=roi_data['type']
                )
                if roi_data['type'] == 'rectangle' and 'rectangle' in roi_data:
                    rect = roi_data['rectangle']
                    roi.rectangle = rect
                    roi.points = [
                        [rect['x'], rect['y']],
                        [rect['x'] + rect['width'], rect['y'] + rect['height']]
                    ]
                elif roi_data['type'] == 'polygon' and 'polygon' in roi_data:
                    roi.polygon = roi_data['polygon']
                    roi.points = roi_data['polygon']
                self.rois.append(roi)
        elif roi_config:
            # 旧格式（单个ROI），转换为新格式
            roi_type = roi_config.get('type', 'rectangle')
            roi = SingleROI(roi_id=1, name="猫砂盆1", roi_type=roi_type)

            if roi_type == 'rectangle' and 'rectangle' in roi_config:
                rect = roi_config['rectangle']
                roi.rectangle = rect
                roi.points = [
                    [rect['x'], rect['y']],
                    [rect['x'] + rect['width'], rect['y'] + rect['height']]
                ]
            elif roi_type == 'polygon' and 'polygon' in roi_config:
                roi.polygon = roi_config['polygon']
                roi.points = roi_config['polygon']

            self.rois.append(roi)

        # 如果没有ROI，创建第一个
        if not self.rois:
            self.rois.append(SingleROI(roi_id=1, name="猫砂盆1", roi_type='rectangle'))

    def start(self):
        """
        启动标注工具
        """
        print("=" * 50)
        print("ROI 标注工具 - go2rtc 版本（多ROI支持）")
        print("=" * 50)
        print("按键说明:")
        print("  n: 完成当前ROI，开始绘制下一个ROI")
        print("  r: 切换到矩形模式（应用到当前ROI）")
        print("  p: 切换到多边形模式（应用到当前ROI）")
        print("  c: 清除当前ROI的标注")
        print("  a: 清除所有ROI")
        print("  s: 保存所有ROI并退出")
        print("  q: 退出不保存")
        print("  鼠标左键: 绘制当前ROI")
        print("  鼠标右键: 完成多边形")
        print("=" * 50)

        # 启动摄像头
        if not self.camera.start():
            print("无法启动摄像头")
            print("\n可能的原因：")
            print("  1. go2rtc 服务未启动")
            print("  2. 网络摄像头未连接")
            print("  3. 配置文件中的摄像头名称不正确")
            print("\n请检查 go2rtc 服务状态和配置")
            return

        print("摄像头已启动")

        import time

        # 丢弃脏帧：go2rtc RTSP 转发不保证从 I 帧（关键帧）开始，
        # OpenCV HEVC 解码器收到 P/B 帧时会因缺少参考帧而报错。
        # 解码器做错误掩盖时会产生低细节的灰色帧，用标准差过滤：
        #   - 正常摄像头画面 std 通常 > 15（有物体、纹理、光影变化）
        #   - HEVC 错误掩盖帧 std 接近 0（均匀灰色，无画面细节）
        print("等待视频流稳定，丢弃脏帧...")
        valid_count = 0
        required_consecutive = 5
        max_warmup = 300
        warmup_count = 0
        frame = None

        while valid_count < required_consecutive and warmup_count < max_warmup:
            ret, f = self.camera.read()
            warmup_count += 1

            if ret and f is not None and f.shape[0] > 0 and f.shape[1] > 0:
                frame_std = np.std(f)
                frame_mean = np.mean(f)
                if frame_mean > 10 and frame_std > 15:
                    valid_count += 1
                    frame = f
                    if valid_count == 1:
                        print(f"  找到有效帧（经 {warmup_count} 帧预热，std={frame_std:.1f}）")
                else:
                    valid_count = 0
                    frame = None
            else:
                valid_count = 0
                frame = None

            time.sleep(0.05)

        if frame is None or valid_count < required_consecutive:
            print("无法获取有效视频帧（流可能未正确解码）")
            print("\n可能的原因：")
            print("  1. go2rtc 服务未正常运行")
            print("  2. 摄像头离线或流不可用")
            print("  3. HEVC 解码持续失败，尝试重启摄像头")
            self.camera.stop()
            return

        print(f"视频帧已获取 ({frame.shape[1]}x{frame.shape[0]})")

        print("开始标注...")

        # 计算缩放比例
        h, w = frame.shape[:2]
        self.display_scale = 1.0
        if w > MAX_DISPLAY_WIDTH or h > MAX_DISPLAY_HEIGHT:
            self.display_scale = min(MAX_DISPLAY_WIDTH / w, MAX_DISPLAY_HEIGHT / h)
            display_w = int(w * self.display_scale)
            display_h = int(h * self.display_scale)
        else:
            display_w, display_h = w, h

        # 创建窗口并设置大小
        # WINDOW_NORMAL 模式允许调整窗口大小，WINDOW_AUTOSIZE 会自动适应图像大小
        cv2.namedWindow('ROI Annotation', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('ROI Annotation', display_w, display_h)
        print(f"显示窗口大小: {display_w}x{display_h}（原始 {w}x{h}，缩放比例 {self.display_scale:.2f}）")

        cv2.setMouseCallback('ROI Annotation', self.mouse_callback)

        display_frame = frame.copy()

        while True:
            # 如果需要缩放，先创建缩放后的显示帧
            if self.display_scale < 1.0:
                temp_frame = cv2.resize(display_frame, (display_w, display_h))
                scale = self.display_scale
            else:
                temp_frame = display_frame.copy()
                scale = 1.0

            # 绘制所有ROI（坐标已缩放）
            self.draw_all_rois(temp_frame, scale)

            # 绘制当前正在编辑的ROI
            if self.current_roi_index < len(self.rois):
                current_roi = self.rois[self.current_roi_index]
                self.draw_current_roi(temp_frame, current_roi, scale)

            # 根据缩放比例调整文字大小
            font_scale = 0.8 * scale if scale < 1.0 else 0.8
            text_thickness = max(1, int(2 * scale)) if scale < 1.0 else 2

            # 显示当前ROI信息
            roi_info = f"Current: ROI {self.current_roi_index + 1}/{len(self.rois)}"
            cv2.putText(temp_frame, roi_info, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), text_thickness)

            # 显示当前模式
            current_roi = self.rois[self.current_roi_index]
            mode_text = f"Mode: {current_roi.type} | Points: {len(current_roi.points)}"
            cv2.putText(temp_frame, mode_text, (10, int(60 * scale)),
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.9, (0, 255, 0), text_thickness)

            # 显示提示
            help_text = "Press 'n' for new ROI, 's' to save, 'q' to quit"
            cv2.putText(temp_frame, help_text, (10, int(90 * scale)),
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.75, (0, 255, 0), text_thickness)

            # 显示帧（确保窗口大小始终正确）
            cv2.imshow('ROI Annotation', temp_frame)
            # 重新设置窗口大小，防止窗口关闭后重新打开时变大
            if display_w > 0 and display_h > 0:
                cv2.resizeWindow('ROI Annotation', display_w, display_h)

            # 处理按键
            key = cv2.waitKey(1) & 0xFF

            if key == ord('n'):
                # 完成当前ROI，开始下一个
                self.current_roi_index += 1
                if self.current_roi_index >= len(self.rois):
                    # 创建新ROI
                    new_id = len(self.rois) + 1
                    new_roi = SingleROI(roi_id=new_id, name=f"猫砂盆{new_id}", roi_type='rectangle')
                    self.rois.append(new_roi)
                print(f"切换到 ROI {self.current_roi_index + 1}/{len(self.rois)}")
            elif key == ord('r'):
                # 切换当前ROI到矩形模式
                if self.current_roi_index < len(self.rois):
                    self.rois[self.current_roi_index].type = 'rectangle'
                    self.rois[self.current_roi_index].points = []
                print("切换到矩形模式")
            elif key == ord('p'):
                # 切换当前ROI到多边形模式
                if self.current_roi_index < len(self.rois):
                    self.rois[self.current_roi_index].type = 'polygon'
                    self.rois[self.current_roi_index].points = []
                print("切换到多边形模式")
            elif key == ord('c'):
                # 清除当前ROI
                if self.current_roi_index < len(self.rois):
                    self.rois[self.current_roi_index].points = []
                    self.rois[self.current_roi_index].rectangle = None
                    self.rois[self.current_roi_index].polygon = None
                print("清除当前ROI标注")
            elif key == ord('a'):
                # 清除所有ROI
                self.rois = [SingleROI(roi_id=1, name="猫砂盆1", roi_type='rectangle')]
                self.current_roi_index = 0
                print("清除所有ROI")
            elif key == ord('s'):
                self.save_rois()
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
        if self.current_roi_index >= len(self.rois):
            return

        current_roi = self.rois[self.current_roi_index]

        if event == cv2.EVENT_LBUTTONDOWN:
            # 将窗口坐标转换为原始帧坐标
            orig_x = int(x / self.display_scale)
            orig_y = int(y / self.display_scale)
            if current_roi.type == 'rectangle':
                # 矩形模式：记录两个点
                if len(current_roi.points) >= 2:
                    current_roi.points = []
                current_roi.points.append([orig_x, orig_y])
                print(f"ROI {current_roi.id}: 添加点 ({orig_x}, {orig_y})")
            else:
                # 多边形模式：记录顶点
                current_roi.points.append([orig_x, orig_y])
                print(f"ROI {current_roi.id}: 添加顶点 ({orig_x}, {orig_y})")

        elif event == cv2.EVENT_RBUTTONDOWN:
            if current_roi.type == 'polygon':
                # 完成多边形
                pass

    def draw_current_roi(self, frame: np.ndarray, roi: SingleROI, scale: float = 1.0):
        """绘制当前正在编辑的ROI"""
        if roi.type == 'rectangle' and len(roi.points) >= 1:
            # 绘制矩形预览（坐标已缩放）
            pt = tuple([int(p * scale) for p in roi.points[0]])
            cv2.circle(frame, pt, max(3, int(5 * scale)), (0, 255, 255), -1)
            if len(roi.points) >= 2:
                pt2 = tuple([int(p * scale) for p in roi.points[1]])
                cv2.rectangle(frame, pt, pt2, (0, 255, 255), max(1, int(2 * scale)))

        elif roi.type == 'polygon' and len(roi.points) >= 1:
            # 绘制多边形预览（坐标已缩放）
            for i, point in enumerate(roi.points):
                pt = tuple([int(p * scale) for p in point])
                cv2.circle(frame, pt, max(3, int(5 * scale)), (0, 255, 255), -1)
                if i > 0:
                    prev_pt = tuple([int(p * scale) for p in roi.points[i - 1]])
                    cv2.line(frame, prev_pt, pt, (0, 255, 255), max(1, int(2 * scale)))
            if len(roi.points) >= 3:
                # 闭合多边形
                last_pt = tuple([int(p * scale) for p in roi.points[-1]])
                first_pt = tuple([int(p * scale) for p in roi.points[0]])
                cv2.line(frame, last_pt, first_pt, (0, 255, 255), max(1, int(2 * scale)))

    def draw_all_rois(self, frame: np.ndarray, scale: float = 1.0):
        """绘制所有已完成的ROI"""
        colors = [
            (0, 255, 0),    # 绿色
            (255, 0, 0),    # 蓝色
            (0, 0, 255),    # 红色
            (255, 255, 0),  # 青色
            (255, 0, 255),  # 品红色
        ]

        line_thickness = max(1, int(2 * scale))
        font_scale = 0.7 * scale if scale < 1.0 else 0.7

        for i, roi in enumerate(self.rois):
            # 跳过当前正在编辑的ROI
            if i == self.current_roi_index:
                continue

            color = colors[i % len(colors)]

            if roi.type == 'rectangle' and roi.rectangle:
                x = int(roi.rectangle['x'] * scale)
                y = int(roi.rectangle['y'] * scale)
                w = int(roi.rectangle['width'] * scale)
                h = int(roi.rectangle['height'] * scale)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, line_thickness)
                cv2.putText(frame, f"ROI {roi.id}", (x, y - int(10 * scale)),
                           cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, line_thickness)

            elif roi.type == 'polygon' and roi.polygon and len(roi.polygon) >= 3:
                polygon = np.array([[int(p * scale) for p in pt] for pt in roi.polygon], dtype=np.int32)
                cv2.polylines(frame, [polygon], True, color, line_thickness)
                center = np.mean([[p * scale for p in pt] for pt in roi.polygon], axis=0)
                cv2.putText(frame, f"ROI {roi.id}", tuple(center.astype(int)),
                           cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, line_thickness)

    def save_rois(self):
        """
        保存所有ROI配置
        """
        if not self.rois:
            print("没有ROI可保存")
            return

        # 加载现有配置
        config_path = project_root / 'config' / 'default.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 处理每个ROI
        rois_data = []
        for roi in self.rois:
            if not roi.points:
                continue

            roi_dict = {
                'id': roi.id,
                'name': roi.name,
                'type': roi.type
            }

            if roi.type == 'rectangle':
                if len(roi.points) < 2:
                    print(f"ROI {roi.id}: 矩形需要两个点")
                    continue

                pt1 = roi.points[0]
                pt2 = roi.points[1]

                # 计算矩形参数
                x = min(pt1[0], pt2[0])
                y = min(pt1[1], pt2[1])
                width = abs(pt2[0] - pt1[0])
                height = abs(pt2[1] - pt1[1])

                roi_dict['rectangle'] = {
                    'x': int(x),
                    'y': int(y),
                    'width': int(width),
                    'height': int(height)
                }
                roi.rectangle = roi_dict['rectangle']

                print(f"保存矩形ROI {roi.id}: x={x}, y={y}, width={width}, height={height}")

            else:  # polygon
                if len(roi.points) < 3:
                    print(f"ROI {roi.id}: 多边形至少需要三个点")
                    continue

                roi_dict['polygon'] = roi.points
                roi.polygon = roi.points

                print(f"保存多边形ROI {roi.id}: {len(roi.points)} 个顶点")

            rois_data.append(roi_dict)

        # 更新配置
        if 'roi' not in config:
            config['roi'] = {}

        config['roi']['rois'] = rois_data

        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        print(f"已保存 {len(rois_data)} 个ROI配置到: {config_path}")


if __name__ == '__main__':
    annotator = ROIAnnotatorGo2RTC()
    annotator.start()
