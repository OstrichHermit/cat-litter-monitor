"""
猫厕所监控系统 - 主程序

该程序是系统的入口，负责初始化所有模块并协调它们的工作。
"""

import sys
import signal
import time
import threading
from pathlib import Path
from typing import Optional

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.utils.logger import get_logger, setup_logger_from_config
from src.core.camera import Camera, create_camera_from_config
from src.core.cat_detector import CatDetector
from src.core.object_tracker import ObjectTracker
from src.core.cat_classifier import CatIdentifier
from src.core.behavior_analyzer import BehaviorAnalyzer, ROI
from src.storage.database import Database
from src.web.app import WebApp, create_templates_directory
import cv2
import numpy as np


class LitterMonitorSystem:
    """
    猫厕所监控系统类

    协调所有模块的工作，实现完整的监控流程。

    Attributes:
        config: 配置对象
        logger: 日志对象
        camera: 摄像头对象
        detector: 猫检测器
        tracker: 目标追踪器
        classifier: 猫分类器
        analyzer: 行为分析器
        database: 数据库对象
        web_app: Web应用对象
        running: 运行标志
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化系统

        Args:
            config_file: 配置文件路径
        """
        # 加载配置
        self.config = get_config(config_file)

        # 初始化日志
        logging_config = self.config.get_logging_config()
        self.logger = setup_logger_from_config(logging_config)
        self.logger.info("系统初始化中...")

        # 初始化模块
        self._init_modules()

        # 运行标志
        self.running = False
        self.frame_count = 0

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_modules(self) -> None:
        """
        初始化所有模块
        """
        # 初始化摄像头
        self.camera = create_camera_from_config(self.config.config)
        camera_type = self.config.config.get('camera', {}).get('type', 'usb')
        self.logger.info(f"摄像头初始化完成: {camera_type}")

        # 初始化猫检测器
        detection_config = self.config.get_detection_config()
        model_path = self.config.get_absolute_path(detection_config.get('model_path', 'data/models/yolov8n.pt'))
        self.detector = CatDetector(
            model_path=model_path,
            confidence_threshold=detection_config.get('confidence_threshold', 0.5),
            iou_threshold=detection_config.get('iou_threshold', 0.45),
            target_class=detection_config.get('target_class', 15),
            input_size=detection_config.get('input_size', 640),
            use_gpu=detection_config.get('use_gpu', True),
            half=detection_config.get('half', False)
        )
        self.logger.info(f"猫检测器初始化完成: {model_path}")

        # 初始化目标追踪器
        tracking_config = self.config.get_tracking_config()
        self.tracker = ObjectTracker(
            max_disappeared=tracking_config.get('max_disappeared', 30),
            max_distance=tracking_config.get('max_distance', 0.3),
            min_confidence=tracking_config.get('min_confidence', 0.3),
            max_tracks=tracking_config.get('max_tracks', 4)  # 默认最大4个追踪ID
        )
        self.logger.info("目标追踪器初始化完成")

        # 初始化猫分类器
        classifier_config = self.config.get_classifier_config()
        model_path = self.config.get_absolute_path(classifier_config.get('model_path', 'data/models/cat_classifier.pth'))
        self.classifier = CatIdentifier(
            model_path=model_path,
            num_classes=classifier_config.get('num_classes', 4),
            class_names=self.config.get_cat_names(),
            input_size=classifier_config.get('input_size', 224),
            use_gpu=classifier_config.get('pretrained', True)
        )
        self.logger.info(f"猫分类器初始化完成: {model_path}")

        # 初始化ROI
        roi_config = self.config.get_roi_config()
        if roi_config.get('type') == 'rectangle':
            rect = roi_config.get('rectangle', {})
            roi = ROI(
                roi_type='rectangle',
                rectangle=[rect.get('x', 100), rect.get('y', 100), rect.get('width', 300), rect.get('height', 300)]
            )
        else:
            roi = ROI(
                roi_type='polygon',
                polygon=roi_config.get('polygon', [])
            )

        # 初始化行为分析器
        behavior_config = self.config.get_behavior_config()
        self.analyzer = BehaviorAnalyzer(
            roi=roi,
            min_frames_in_roi=roi_config.get('min_frames_in_roi', 15),
            exit_delay_frames=roi_config.get('exit_delay_frames', 30),
            min_duration=behavior_config.get('min_duration', 5.0),
            min_interval=behavior_config.get('min_interval', 30.0)
        )
        self.logger.info("行为分析器初始化完成")

        # 初始化数据库
        database_config = self.config.get_database_config()
        db_path = self.config.get_absolute_path(database_config.get('path', 'data/litter_monitor.db'))
        self.database = Database(db_path=db_path)
        self.logger.info(f"数据库初始化完成: {db_path}")

        # 初始化Web应用
        web_config = self.config.get_web_config()
        self.web_app = WebApp(
            host=web_config.get('host', '0.0.0.0'),
            port=web_config.get('port', 5000),
            debug=web_config.get('debug', False)
        )
        # 设置停止回调
        self.web_app.set_stop_callback(self.stop)
        # 创建模板目录
        create_templates_directory()
        self.logger.info(f"Web应用初始化完成: {web_config.get('host')}:{web_config.get('port')}")

    def _signal_handler(self, signum, frame) -> None:
        """
        信号处理函数

        Args:
            signum: 信号编号
            frame: 当前帧
        """
        self.logger.info(f"接收到信号 {signum}，正在停止系统...")
        self.stop()

    def start(self) -> None:
        """
        启动系统
        """
        self.logger.info("启动系统...")
        self.running = True

        # 启动摄像头
        if not self.camera.start():
            self.logger.error("摄像头启动失败")
            return

        self.logger.info("摄像头已启动")

        # 启动Web服务器（在单独线程中）
        web_thread = threading.Thread(target=self.web_app.run, daemon=True)
        web_thread.start()
        self.logger.info("Web服务器已启动")

        # 更新Web状态
        self.web_app.set_running(True)

        # 主循环
        system_config = self.config.get_system_config()
        process_every_n_frames = system_config.get('process_every_n_frames', 1)

        try:
            consecutive_failures = 0
            while self.running:
                # 读取帧
                ret, frame = self.camera.read()
                if not ret:
                    consecutive_failures += 1
                    self.logger.warning(f"读取帧失败 (连续失败{consecutive_failures}次)")
                    time.sleep(0.1)

                    # 如果连续失败太多，尝试重新连接摄像头
                    if consecutive_failures > 50:
                        self.logger.error("连续读取失败次数过多，尝试重启摄像头...")
                        self.camera.stop()
                        time.sleep(2)
                        if self.camera.start():
                            self.logger.info("摄像头重启成功")
                            consecutive_failures = 0
                        else:
                            self.logger.error("摄像头重启失败")
                    continue

                consecutive_failures = 0  # 重置失败计数
                self.frame_count += 1

                # 跳帧处理标记
                should_process = (self.frame_count % process_every_n_frames == 0)

                # 每100帧记录一次
                if self.frame_count % 100 == 0:
                    self.logger.info(f"已处理 {self.frame_count} 帧")

                # 处理帧（只在应该处理的帧上进行完整处理）
                if should_process:
                    processed_frame = self._process_frame(frame)
                else:
                    # 跳帧时只显示原始帧，保持视频流连续性
                    processed_frame = frame.copy()

                # 更新Web帧（无论是否处理，都更新视频流）
                self.web_app.update_frame(processed_frame)

                # 定期更新统计
                if self.frame_count % 600 == 0:  # 每600帧更新一次
                    self._update_statistics()

        except Exception as e:
            self.logger.error(f"主循环异常: {e}", exc_info=True)
        finally:
            self.stop()

    def _process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        处理视频帧

        Args:
            frame: 输入帧

        Returns:
            处理后的帧
        """
        # 复制帧
        display_frame = frame.copy()

        # 检测猫
        detections = self.detector.detect(frame)
        if len(detections) > 0:
            self.logger.debug(f"检测到 {len(detections)} 只猫")
            for d in detections:
                self.logger.debug(f"  - 置信度: {d.confidence:.3f}, 位置: {d.bbox}")

        # 追踪
        tracks = self.tracker.update(detections)
        self.logger.debug(f"追踪器输出: {len(tracks)} 个追踪目标")
        for track in tracks:
            self.logger.debug(f"  Track ID: {track.track_id}, Bbox: {getattr(track, 'bbox', getattr(track, 'tlwh', 'N/A'))}")

        # 个体识别
        for track in tracks:
            if hasattr(track, 'bbox') and track.bbox is not None:
                # 获取边界框
                bbox = track.bbox
                x1, y1, x2, y2 = [int(coord) for coord in [bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]]]

                # 裁剪ROI
                roi = frame[y1:y2, x1:x2]

                if roi.size > 0:
                    # 识别
                    prediction = self.classifier.predict(roi)

                    # 更新分析器
                    if prediction['confidence'] > 0.5:
                        self.analyzer.update_cat_info(
                            track.track_id,
                            prediction['class_id'],
                            prediction['class_name']
                        )

        # 行为分析
        fps = self.config.get_camera_config().get('fps', 30)
        completed_events = self.analyzer.update(tracks, fps)

        # 保存完成的事件
        for event in completed_events:
            self.logger.info(
                f"事件完成: {event.cat_name} (ID: {event.cat_id}), "
                f"时长: {event.duration:.1f}秒"
            )
            self.database.insert_event(event.to_dict())

        # 绘制结果
        display_frame = self._draw_results(display_frame, detections, tracks)

        # 更新Web数据
        self.web_app.update_detections(detections)
        self.web_app.update_tracks(tracks)
        self.web_app.update_events(self.analyzer.get_completed_events())

        return display_frame

    def _draw_results(
        self,
        frame: np.ndarray,
        detections: list,
        tracks: list
    ) -> np.ndarray:
        """
        在帧上绘制结果

        Args:
            frame: 输入帧
            detections: 检测列表
            tracks: 追踪列表

        Returns:
            绘制后的帧
        """
        # 获取猫颜色配置
        cat_colors = self.config.get_cat_colors_config()

        # 绘制行为分析结果
        frame = self.analyzer.draw_analysis(frame, tracks)

        # 不再绘制检测结果（绿色框），只显示追踪框使画面更清晰
        # 如需调试可取消下方注释
        # for detection in detections:
        #     if hasattr(detection, 'bbox'):
        #         bbox = detection.bbox
        #         x1, y1, x2, y2 = [int(v) for v in bbox]
        #         cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
        #         label = f"Cat: {detection.confidence:.2f}"
        #         cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # 然后绘制追踪结果（使用每只猫的颜色）
        for track in tracks:
            if hasattr(track, 'bbox'):
                bbox = track.bbox
                x, y, w, h = bbox
            elif hasattr(track, 'tlwh'):
                tlwh = track.tlwh
                x, y, w, h = tlwh
            else:
                continue

            # 获取猫名字和颜色
            cat_name = self.analyzer.get_cat_name_for_track(track.track_id)
            default_color = (255, 0, 0)  # 默认蓝色

            if cat_name and cat_name in cat_colors:
                color = cat_colors[cat_name]
                self.logger.debug(f"Track {track.track_id} 使用颜色 {color} (猫: {cat_name})")
            else:
                color = default_color
                self.logger.debug(f"Track {track.track_id} 使用默认颜色 {color}")

            # 绘制边界框（使用猫的颜色）
            cv2.rectangle(frame, (int(x), int(y)), (int(x + w), int(y + h)), color, 2)

            # 绘制标签（一直显示猫名字，不管在不在ROI）
            label = f"ID:{track.track_id}"

            # 显示猫名字（如果有）
            if cat_name:
                label += f" {cat_name}"
            elif track.track_id in self.analyzer.track_states:
                state = self.analyzer.track_states[track.track_id]
                # 如果当前事件有猫名字，也显示
                if state.get('current_event') and state['current_event'].cat_name != '未知':
                    label += f" {state['current_event'].cat_name}"

            cv2.putText(
                frame,
                label,
                (int(x), int(y - 40)),  # 向上偏移，避免覆盖检测标签
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )

        return frame

    def _update_statistics(self) -> None:
        """
        更新统计数据
        """
        try:
            # 更新每日统计
            self.database.update_daily_statistics()

            # 获取统计
            summary = self.database.get_summary_statistics()
            self.web_app.update_statistics(summary)

            self.logger.info(f"统计更新: 总事件数 {summary['total_events']}")
        except Exception as e:
            self.logger.error(f"更新统计失败: {e}")

    def stop(self) -> None:
        """
        停止系统
        """
        if not self.running:
            return

        self.logger.info("停止系统...")
        self.running = False

        # 更新Web状态
        self.web_app.set_running(False)

        # 停止摄像头
        self.camera.stop()

        # 最后一次统计更新
        self._update_statistics()

        # 关闭所有 OpenCV 窗口
        cv2.destroyAllWindows()

        self.logger.info("系统已停止")


def main():
    """
    主函数
    """
    import argparse

    parser = argparse.ArgumentParser(description='猫厕所监控系统')
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径'
    )

    args = parser.parse_args()

    # 创建并启动系统
    system = LitterMonitorSystem(config_file=args.config)
    system.start()


if __name__ == '__main__':
    main()
