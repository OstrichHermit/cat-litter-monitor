"""
数据收集脚本

该脚本用于收集猫的训练数据，用户可以手动标注每张图片对应的猫。
"""

import sys
from pathlib import Path
import cv2
import time

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.core.camera import Camera
from src.core.cat_detector import CatDetector
from src.utils.logger import get_logger


class DataCollector:
    """
    数据收集器类

    用于收集猫的训练数据。
    """

    def __init__(self, config_file: str = None):
        """
        初始化数据收集器

        Args:
            config_file: 配置文件路径
        """
        # 加载配置
        self.config = get_config(config_file)
        self.logger = get_logger()

        # 获取类别名称
        self.cat_names = self.config.get_cat_names()
        self.logger.info(f"猫类别: {self.cat_names}")

        # 数据保存目录
        self.save_dir = Path(project_root) / 'data' / 'raw' / 'training'
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # 为每个类别创建目录
        for cat_name in self.cat_names:
            (self.save_dir / cat_name).mkdir(exist_ok=True)

        # 计数器
        self.counters = {name: 0 for name in self.cat_names}

        # 初始化摄像头和检测器
        self._init_modules()

        # 当前选择的类别
        self.current_class = 0

    def _init_modules(self):
        """
        初始化摄像头和检测器
        """
        # 初始化摄像头
        camera_config = self.config.get_camera_config()
        self.camera = Camera(
            camera_type=camera_config.get('type', 'usb'),
            device_id=camera_config.get('device_id', 0),
            width=camera_config.get('width', 1280),
            height=camera_config.get('height', 720),
            fps=camera_config.get('fps', 30)
        )

        # 初始化检测器
        detection_config = self.config.get_detection_config()
        model_path = self.config.get_absolute_path(detection_config.get('model_path', 'data/models/yolov8n.pt'))
        self.detector = CatDetector(
            model_path=model_path,
            confidence_threshold=0.5,
            use_gpu=detection_config.get('use_gpu', True)
        )

    def collect(self):
        """
        开始收集数据
        """
        self.logger.info("启动数据收集...")
        self.logger.info("按键说明:")
        self.logger.info("  1-4: 选择当前标注的猫")
        self.logger.info("  空格: 保存当前帧")
        self.logger.info("  q: 退出")

        # 启动摄像头
        if not self.camera.start():
            self.logger.error("摄像头启动失败")
            return

        try:
            while True:
                # 读取帧
                ret, frame = self.camera.read()
                if not ret:
                    continue

                # 检测猫
                detections = self.detector.detect(frame)

                # 绘制检测结果
                display_frame = self.detector.draw_detections(frame, detections)

                # 绘制当前类别
                cat_name = self.cat_names[self.current_class]
                cv2.putText(
                    display_frame,
                    f"当前标注: {cat_name}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2
                )

                # 绘制计数
                y_offset = 60
                for i, name in enumerate(self.cat_names):
                    color = (0, 255, 0) if i == self.current_class else (0, 0, 255)
                    text = f"{i+1}. {name}: {self.counters[name]}"
                    cv2.putText(
                        display_frame,
                        text,
                        (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2
                    )
                    y_offset += 30

                # 显示帧
                cv2.imshow('Data Collection', display_frame)

                # 处理按键
                key = cv2.waitKey(1) & 0xFF

                if key == ord('q'):
                    break
                elif key == ord('1'):
                    self.current_class = 0
                elif key == ord('2'):
                    self.current_class = 1
                elif key == ord('3'):
                    self.current_class = 2
                elif key == ord('4'):
                    self.current_class = 3
                elif key == ord(' '):
                    # 保存当前帧
                    self._save_frame(frame, detections)

        except KeyboardInterrupt:
            pass
        finally:
            self.camera.stop()
            cv2.destroyAllWindows()
            self._print_summary()

    def _save_frame(self, frame, detections):
        """
        保存帧

        Args:
            frame: 视频帧
            detections: 检测结果
        """
        cat_name = self.cat_names[self.current_class]

        # 如果有检测结果，裁剪猫的ROI
        if detections:
            detection = detections[0]  # 使用第一个检测结果
            x1, y1, x2, y2 = [int(coord) for coord in detection.bbox]
            roi = frame[y1:y2, x1:x2]

            if roi.size > 0:
                # 保存ROI
                self.counters[cat_name] += 1
                filename = f"{cat_name}_{self.counters[cat_name]:06d}.jpg"
                filepath = self.save_dir / cat_name / filename
                cv2.imwrite(str(filepath), roi)
                self.logger.info(f"保存: {filepath} (ROI)")
        else:
            # 保存完整帧
            self.counters[cat_name] += 1
            filename = f"{cat_name}_{self.counters[cat_name]:06d}.jpg"
            filepath = self.save_dir / cat_name / filename
            cv2.imwrite(str(filepath), frame)
            self.logger.info(f"保存: {filepath} (完整帧)")

    def _print_summary(self):
        """
        打印收集摘要
        """
        self.logger.info("数据收集完成，统计:")
        total = 0
        for name, count in self.counters.items():
            self.logger.info(f"  {name}: {count}")
            total += count
        self.logger.info(f"总计: {total}")


def main():
    """
    主函数
    """
    import argparse

    parser = argparse.ArgumentParser(description='收集猫的训练数据')
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径'
    )

    args = parser.parse_args()

    # 创建数据收集器
    collector = DataCollector(config_file=args.config)
    collector.collect()


if __name__ == '__main__':
    main()
