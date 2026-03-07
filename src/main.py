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
from src.core.behavior_analyzer import BehaviorAnalyzer, ROI, MultiROI
from src.core.photo_capture import PhotoCaptureManager, PhotoCaptureConfig
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

        # 初始化ROI（支持多ROI）
        roi_config = self.config.get_roi_config()
        multi_roi = None

        # 检查是否是新的多ROI格式
        if 'rois' in roi_config:
            # 新格式：多ROI
            rois_list = []
            for roi_data in roi_config['rois']:
                if roi_data.get('type') == 'rectangle':
                    rect = roi_data.get('rectangle', {})
                    roi = ROI(
                        roi_type='rectangle',
                        rectangle=[rect.get('x', 100), rect.get('y', 100),
                                  rect.get('width', 300), rect.get('height', 300)]
                    )
                else:
                    roi = ROI(
                        roi_type='polygon',
                        polygon=roi_data.get('polygon', [])
                    )
                rois_list.append(roi)

            multi_roi = MultiROI(rois_list)
            self.logger.info(f"加载了 {len(rois_list)} 个ROI区域")

        elif roi_config.get('type'):
            # 旧格式：单个ROI，保持向后兼容
            if roi_config.get('type') == 'rectangle':
                rect = roi_config.get('rectangle', {})
                roi = ROI(
                    roi_type='rectangle',
                    rectangle=[rect.get('x', 100), rect.get('y', 100),
                              rect.get('width', 300), rect.get('height', 300)]
                )
            else:
                roi = ROI(
                    roi_type='polygon',
                    polygon=roi_config.get('polygon', [])
                )
            multi_roi = MultiROI([roi])
            self.logger.info("加载了单个ROI区域（旧格式）")

        # 初始化行为分析器
        behavior_config = self.config.get_behavior_config()
        self.analyzer = BehaviorAnalyzer(
            multi_roi=multi_roi,
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
            debug=web_config.get('debug', False),
            database=self.database
        )
        # 设置停止回调
        self.web_app.set_stop_callback(self.stop)
        # 设置重启回调
        self.web_app.set_restart_callback(self.restart)
        # 创建模板目录
        create_templates_directory()
        self.logger.info(f"Web应用初始化完成: {web_config.get('host')}:{web_config.get('port')}")

        # 初始化拍照管理器
        photo_config = self.config.get_photo_config()
        photo_capture_config = PhotoCaptureConfig(
            min_stay_seconds=photo_config.get('min_stay_seconds', 3.0),
            photo_interval=photo_config.get('photo_interval', 10.0),
            photo_base_dir=photo_config.get('photo_base_dir', 'photo')
        )
        self.photo_manager = PhotoCaptureManager(photo_capture_config, self.logger)
        self.logger.info("拍照管理器初始化完成")

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

        # 系统启动时更新统计数据
        self.logger.info("系统启动，更新统计数据...")
        self._update_statistics()

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
                try:
                    # 读取帧
                    ret, frame = self.camera.read()
                    if not ret:
                        consecutive_failures += 1
                        if consecutive_failures >= 50:
                            self.logger.error(f"读取帧失败 (连续失败{consecutive_failures}次)")
                        time.sleep(0.1)
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

                except Exception as frame_error:
                    # 单帧处理异常，记录但继续运行
                    self.logger.error(f"处理帧时出错 (frame {self.frame_count}): {frame_error}")
                    import traceback
                    self.logger.debug(traceback.format_exc())
                    continue

        except Exception as e:
            self.logger.error(f"主循环严重异常: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
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

        # 行为分析
        fps = self.config.get_camera_config().get('fps', 30)
        completed_events = self.analyzer.update(tracks, fps)

        # 拍照管理：检查每个ROI区域是否需要拍照
        # 统计每个ROI区域是否有检测
        roi_detection_map = {}  # roi_index -> has_detection

        # 首先标记所有ROI为无检测
        for i in range(1, len(self.analyzer.multi_roi.rois) + 1):
            roi_detection_map[i] = False

        # 检查每个track所在的ROI
        for track in tracks:
            # 获取中心点
            if hasattr(track, 'bbox'):
                bbox = track.bbox
                center_x = bbox[0] + bbox[2] / 2
                center_y = bbox[1] + bbox[3] / 2
                center = (center_x, center_y)
            elif hasattr(track, 'tlwh'):
                tlwh = track.tlwh
                center_x = tlwh[0] + tlwh[2] / 2
                center_y = tlwh[1] + tlwh[3] / 2
                center = (center_x, center_y)
            else:
                continue

            # 判断在哪个ROI内
            roi_index = self.analyzer.multi_roi.get_roi_id(center) or 0
            if roi_index > 0:
                roi_detection_map[roi_index] = True

        # 对每个ROI更新拍照管理器
        for roi_index, has_detection in roi_detection_map.items():
            photo_path = self.photo_manager.update(
                roi_index,
                has_detection,
                frame,
                fps
            )

            if photo_path:
                self.logger.info(f"拍照成功: {photo_path}")
                # 通知Web前端记录更新
                self.web_app.notify_records_update()

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
            tracks: 追踪列表（保留用于行为分析，但不绘制）

        Returns:
            绘制后的帧
        """
        # 绘制行为分析结果（ROI区域等）
        frame = self.analyzer.draw_analysis(frame, tracks)

        # 只绘制检测结果（绿色Cat框 + 中心点）
        for detection in detections:
            if hasattr(detection, 'bbox'):
                bbox = detection.bbox
                x1, y1, x2, y2 = [int(v) for v in bbox]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = "Cat"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # 绘制中心点
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                cv2.circle(frame, (center_x, center_y), 5, (0, 255, 0), -1)

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

            self.logger.info(f"统计更新: 总记录数 {summary['total_records']}")
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

    def restart(self) -> None:
        """
        重启系统
        """
        self.logger.info("重启系统...")

        # 先停止系统
        if self.running:
            self.stop()

        # 等待停止完成
        import time
        time.sleep(2)

        # 重新启动系统
        self.start()


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
