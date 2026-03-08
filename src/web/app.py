"""
Web界面模块

该模块提供Flask Web应用，用于实时视频流展示和统计数据查看。
"""

from flask import Flask, render_template, Response, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime, date
import json
from typing import Optional, Dict
import cv2
import numpy as np
from pathlib import Path


class WebApp:
    """
    Web应用类

    负责Flask应用的创建和路由配置。

    Attributes:
        app: Flask应用实例
        socketio: SocketIO实例
        host: 主机地址
        port: 端口
        debug: 调试模式
        stop_callback: 停止系统的回调函数
    """

    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 5000,
        debug: bool = False,
        secret_key: str = 'litter-monitor-secret-key',
        database=None
    ):
        """
        初始化Web应用

        Args:
            host: 主机地址
            port: 端口
            debug: 调试模式
            secret_key: 密钥
            database: 数据库实例（可选）
        """
        self.host = host
        self.port = port
        self.debug = debug
        self.stop_callback = None
        self.restart_callback = None
        self.database = database

        # 视频流客户端计数器
        self.stream_clients = 0

        # 创建Flask应用
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.app.config['SECRET_KEY'] = secret_key

        # 启用CORS
        CORS(self.app)

        # 创建SocketIO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")

        # 存储系统状态
        self.system_state = {
            'running': False,
            'frame': None,
            'detections': [],
            'tracks': [],
            'events': [],
            'statistics': {}
        }

        # 注册路由
        self._register_routes()

    def _register_routes(self) -> None:
        """
        注册路由
        """

        @self.app.route('/')
        def index():
            """主页 - 根据设备类型返回不同模板"""
            from flask import request
            user_agent = request.headers.get('User-Agent', '').lower()

            # 检测是否是移动设备
            is_mobile = any(mobile in user_agent for mobile in
                          ['iphone', 'android', 'ipad', 'mobile', 'ipod'])

            if is_mobile:
                return render_template('mobile.html')
            else:
                return render_template('index.html')

        @self.app.route('/mobile')
        def mobile():
            """移动端专用页面（可手动访问）"""
            return render_template('mobile.html')

        @self.app.route('/api/status')
        def status():
            """获取系统状态"""
            return jsonify({
                'running': self.system_state['running'],
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/statistics')
        def statistics():
            """获取统计数据"""
            return jsonify(self.system_state['statistics'])

        @self.app.route('/api/events')
        def events():
            """获取事件列表"""
            events_data = [e.to_dict() if hasattr(e, 'to_dict') else e for e in self.system_state['events']]
            return jsonify(events_data[-100:])  # 返回最近100条事件

        @self.app.route('/api/records/today')
        def records_today():
            """获取今天和昨天的记录"""
            try:
                from src.storage.database import Database
                from src.config import get_config

                config = get_config()
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                # 获取今天和昨天的记录
                today_records = database.get_today_records()
                yesterday_records = database.get_yesterday_records()

                return jsonify({
                    'success': True,
                    'today': today_records,
                    'yesterday': yesterday_records
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/records/unidentified')
        def records_unidentified():
            """获取未识别的照片列表"""
            try:
                from src.storage.photo_manager import PhotoManager
                from src.config import get_config

                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = photo_config.get('photo_base_dir', 'photo')

                photo_manager = PhotoManager(photo_base_dir)
                photos = photo_manager.get_unidentified_photos()

                return jsonify({
                    'success': True,
                    'photos': photos,
                    'count': len(photos)
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/records/delete/<int:record_id>', methods=['DELETE'])
        def delete_record(record_id):
            """删除单条记录"""
            try:
                from src.storage.database import Database
                from src.config import get_config
                import os

                config = get_config()
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                # 获取记录信息（用于删除照片文件）
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT photo_path FROM litter_records WHERE id = ?", (record_id,))
                    record = cursor.fetchone()

                if not record:
                    return jsonify({
                        'success': False,
                        'error': '记录不存在'
                    }), 404

                photo_path = record['photo_path']

                # 删除数据库记录
                success = database.delete_record_by_id(record_id)

                if success:
                    # 尝试删除照片文件
                    if photo_path:
                        abs_photo_path = config.get_absolute_path(photo_path)
                        if os.path.exists(abs_photo_path):
                            try:
                                os.remove(abs_photo_path)
                            except Exception as e:
                                print(f"删除照片文件失败: {e}")

                    return jsonify({
                        'success': True,
                        'message': '删除成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': '删除失败'
                    }), 500
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/records/edit/<int:record_id>', methods=['PUT'])
        def edit_record(record_id):
            """编辑记录的猫咪"""
            try:
                from src.storage.database import Database
                from src.config import get_config
                from src.storage.photo_manager import PhotoManager
                import os
                import shutil

                data = request.get_json()
                new_cat_name = data.get('cat_name')

                if not new_cat_name:
                    return jsonify({
                        'success': False,
                        'error': '缺少猫咪名称'
                    }), 400

                config = get_config()
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                # 获取记录信息
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT cat_name, photo_path, record_date, record_time FROM litter_records WHERE id = ?",
                        (record_id,)
                    )
                    record = cursor.fetchone()

                if not record:
                    return jsonify({
                        'success': False,
                        'error': '记录不存在'
                    }), 404

                old_cat_name = record['cat_name']
                photo_path = record['photo_path']
                record_date = record['record_date']
                record_time = record['record_time']

                # 如果猫咪名称没有变化，直接返回成功
                if old_cat_name == new_cat_name:
                    return jsonify({
                        'success': True,
                        'message': '猫咪名称未变化'
                    })

                # 先移动照片，再更新数据库
                photo_moved = False
                new_photo_path = photo_path  # 默认保持原路径

                if photo_path:
                    abs_photo_path = config.get_absolute_path(photo_path)

                    if os.path.exists(abs_photo_path):
                        # 构建新路径：photo/YYYY-MM-DD/Identified/新猫名/文件名
                        filename = os.path.basename(photo_path)
                        new_photo_path = f'photo/{record_date}/Identified/{new_cat_name}/{filename}'
                        new_abs_photo_path = config.get_absolute_path(new_photo_path)

                        try:
                            # 确保目标目录存在
                            os.makedirs(os.path.dirname(new_abs_photo_path), exist_ok=True)

                            # 如果目标文件已存在，先删除它
                            if os.path.exists(new_abs_photo_path):
                                os.remove(new_abs_photo_path)

                            # 移动照片
                            shutil.move(abs_photo_path, new_abs_photo_path)
                            photo_moved = True
                        except Exception as e:
                            print(f"移动照片文件失败: {e}")
                            # 照片移动失败，保持原路径
                            new_photo_path = photo_path
                            photo_moved = False
                    else:
                        print(f"原照片文件不存在: {abs_photo_path}")

                # 更新数据库中的猫咪名称和照片路径
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE litter_records SET cat_name = ?, photo_path = ? WHERE id = ?",
                        (new_cat_name, new_photo_path, record_id)
                    )
                    conn.commit()

                # 更新每日统计
                from datetime import datetime
                record_date_obj = datetime.fromisoformat(record_date).date() if isinstance(record_date, str) else record_date
                database.update_daily_statistics(record_date_obj)

                return jsonify({
                    'success': True,
                    'message': '修改成功',
                    'photo_moved': photo_moved
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/records/unidentified/delete', methods=['DELETE'])
        def delete_unidentified_photo():
            """删除未识别的照片"""
            try:
                from src.config import get_config
                import os

                data = request.get_json()
                photo_path = data.get('photo_path')

                if not photo_path:
                    return jsonify({
                        'success': False,
                        'error': '缺少照片路径'
                    }), 400

                # photo_path 是相对路径，格式: YYYY-MM-DD/Unidentified/filename.jpg
                # 需要加上 photo/ 前缀
                if not photo_path.startswith('photo/'):
                    photo_path = f'photo/{photo_path}'

                # 转换为绝对路径
                config = get_config()
                abs_photo_path = config.get_absolute_path(photo_path)

                if os.path.exists(abs_photo_path):
                    os.remove(abs_photo_path)
                    return jsonify({
                        'success': True,
                        'message': '删除成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': f'文件不存在: {abs_photo_path}'
                    }), 404
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/records/manual-add', methods=['POST'])
        def manual_add_record():
            """手动添加记录（将未识别照片入库）"""
            try:
                from src.storage.database import Database
                from src.config import get_config
                import os
                import shutil
                from datetime import datetime

                data = request.get_json()
                photo_rel_path = data.get('photo_path')  # 格式: YYYY-MM-DD/Unidentified/filename.jpg
                cat_name = data.get('cat_name')

                if not photo_rel_path or not cat_name:
                    return jsonify({
                        'success': False,
                        'error': '缺少照片路径或猫咪名称'
                    }), 400

                # 构建完整路径
                if not photo_rel_path.startswith('photo/'):
                    photo_rel_path = f'photo/{photo_rel_path}'

                config = get_config()
                abs_photo_path = config.get_absolute_path(photo_rel_path)

                if not os.path.exists(abs_photo_path):
                    return jsonify({
                        'success': False,
                        'error': f'照片文件不存在: {abs_photo_path}'
                    }), 404

                # 从文件名提取日期和时间
                # 文件名格式: YYYYMMDD_HHMMSS.jpg
                filename = os.path.basename(abs_photo_path)
                name_without_ext = os.path.splitext(filename)[0]

                try:
                    # 解析文件名获取日期时间
                    record_date = f"{name_without_ext[0:4]}-{name_without_ext[4:6]}-{name_without_ext[6:8]}"
                    record_time = f"{name_without_ext[9:11]}:{name_without_ext[11:13]}:{name_without_ext[13:15]}"
                except IndexError:
                    # 如果文件名格式不对，使用文件修改时间
                    mtime = os.path.getmtime(abs_photo_path)
                    dt = datetime.fromtimestamp(mtime)
                    record_date = dt.strftime('%Y-%m-%d')
                    record_time = dt.strftime('%H:%M:%S')

                # 移动照片到对应猫咪的文件夹
                # 从路径中提取日期部分，构建目标路径
                parts = photo_rel_path.split('/')
                date_part = parts[1] if len(parts) > 1 else record_date
                new_photo_rel_path = f"photo/{date_part}/Identified/{cat_name}/{filename}"
                new_abs_photo_path = config.get_absolute_path(new_photo_rel_path)

                # 创建目标目录并移动文件
                os.makedirs(os.path.dirname(new_abs_photo_path), exist_ok=True)
                shutil.move(abs_photo_path, new_abs_photo_path)

                # 插入数据库记录
                database_config = config.get_database_config()
                db_path = config.get_absolute_path(
                    database_config.get('path', 'data/litter_monitor.db')
                )
                database = Database(db_path=db_path)

                record_id = database.insert_litter_record(
                    cat_name=cat_name,
                    record_date=record_date,
                    record_time=record_time,
                    photo_path=new_photo_rel_path
                )

                # 通知前端记录已更新
                self.notify_records_update()

                return jsonify({
                    'success': True,
                    'message': '入库成功',
                    'record_id': record_id
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/stop', methods=['POST'])
        def stop_service():
            """停止系统服务"""
            try:
                import subprocess
                import sys
                from pathlib import Path

                # 获取项目根目录
                project_root = Path(__file__).parent.parent.parent
                stop_script = project_root / 'stop.bat'

                if stop_script.exists():
                    # 在后台执行停止脚本
                    if sys.platform == 'win32':
                        # Windows: 使用 shell=True 并传递字符串
                        subprocess.Popen(
                            f'cmd /c "{stop_script}"',
                            shell=True,
                            cwd=str(project_root),
                            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                        )
                    else:
                        subprocess.Popen(
                            [str(stop_script)],
                            cwd=str(project_root),
                            start_new_session=True
                        )
                    return jsonify({'status': 'stopping', 'message': '系统正在停止...'})
                else:
                    return jsonify({'status': 'error', 'message': f'停止脚本不存在: {stop_script}'}), 500
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'停止失败: {str(e)}'}), 500

        @self.app.route('/api/restart', methods=['POST'])
        def restart_service():
            """重启系统服务"""
            try:
                import subprocess
                import sys
                from pathlib import Path

                # 获取项目根目录
                project_root = Path(__file__).parent.parent.parent
                restart_script = project_root / 'restart.bat'

                if restart_script.exists():
                    # 在后台执行重启脚本
                    if sys.platform == 'win32':
                        # Windows: 使用 shell=True 并传递字符串
                        subprocess.Popen(
                            f'cmd /c "{restart_script}"',
                            shell=True,
                            cwd=str(project_root),
                            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                        )
                    else:
                        subprocess.Popen(
                            [str(restart_script)],
                            cwd=str(project_root),
                            start_new_session=True
                        )
                    return jsonify({'status': 'restarting', 'message': '系统正在重启...'})
                else:
                    return jsonify({'status': 'error', 'message': f'重启脚本不存在: {restart_script}'}), 500
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'重启失败: {str(e)}'}), 500

        @self.app.route('/video_feed')
        def video_feed():
            """视频流"""
            return Response(
                self._generate_frames(),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )

        @self.app.route('/static/photo/<path:filepath>')
        def serve_photo(filepath):
            """提供照片文件访问"""
            try:
                from src.config import get_config
                import os
                config = get_config()
                photo_config = config.get_photo_config()
                photo_base_dir = config.get_absolute_path(photo_config.get('photo_base_dir', 'photo'))

                # 构建完整文件路径
                full_path = os.path.join(photo_base_dir, filepath)

                # 安全检查：确保full_path在photo_base_dir内
                full_path_resolved = Path(full_path).resolve()
                photo_dir_resolved = Path(photo_base_dir).resolve()

                if not str(full_path_resolved).startswith(str(photo_dir_resolved)):
                    return jsonify({'error': 'Invalid path'}), 400

                # 获取目录和文件名
                filepath_obj = Path(filepath)
                if len(filepath_obj.parts) > 1:
                    subdir = filepath_obj.parent
                    filename = filepath_obj.name
                    return send_from_directory(Path(photo_base_dir) / subdir, filename)
                else:
                    return send_from_directory(photo_base_dir, filepath)
            except Exception as e:
                return jsonify({'error': str(e)}), 404

        @self.socketio.on('connect')
        def handle_connect():
            """处理客户端连接"""
            emit('connected', {'data': 'Connected to Litter Monitor'})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """处理客户端断开"""
            print('Client disconnected')

    def _generate_frames(self):
        """
        生成视频帧

        Yields:
            JPEG格式的视频帧
        """
        self.stream_clients += 1
        try:
            while True:
                if self.system_state['frame'] is not None:
                    # 编码为JPEG，降低质量以减少带宽
                    ret, buffer = cv2.imencode('.jpg', self.system_state['frame'],
                                              [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ret:
                        frame = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        finally:
            self.stream_clients -= 1

    def update_frame(self, frame: np.ndarray) -> None:
        """
        更新当前帧（只在有客户端连接时才复制）

        Args:
            frame: 视频帧
        """
        try:
            # 只在有客户端观看视频流时才更新帧
            if self.stream_clients > 0:
                self.system_state['frame'] = frame.copy()
        except Exception as e:
            # 静默处理，避免影响主循环
            pass

    def update_detections(self, detections: list) -> None:
        """
        更新检测结果

        Args:
            detections: 检测列表
        """
        try:
            self.system_state['detections'] = [
                d.to_dict() if hasattr(d, 'to_dict') else d
                for d in detections
            ]
        except Exception as e:
            # 静默处理，避免影响主循环
            self.system_state['detections'] = []

    def update_tracks(self, tracks: list) -> None:
        """
        更新追踪结果

        Args:
            tracks: 追踪列表
        """
        try:
            self.system_state['tracks'] = [
                {'id': t.track_id, 'bbox': t.bbox if hasattr(t, 'bbox') else (t.tlwh.tolist() if hasattr(t, 'tlwh') else [])}
                for t in tracks
            ]
        except Exception as e:
            # 静默处理，避免影响主循环
            self.system_state['tracks'] = []

    def update_events(self, events: list) -> None:
        """
        更新事件列表

        Args:
            events: 事件列表
        """
        try:
            self.system_state['events'] = events
        except Exception as e:
            # 静默处理，避免影响主循环
            self.system_state['events'] = []

    def update_statistics(self, statistics: Dict) -> None:
        """
        更新统计数据

        Args:
            statistics: 统计数据字典
        """
        self.system_state['statistics'] = statistics

        # 通过WebSocket发送更新
        self.socketio.emit('statistics_update', statistics)

    def set_running(self, running: bool) -> None:
        """
        设置运行状态

        Args:
            running: 是否运行中
        """
        self.system_state['running'] = running
        self.socketio.emit('status_update', {'running': running})

    def set_stop_callback(self, callback) -> None:
        """
        设置停止回调函数

        Args:
            callback: 停止系统的回调函数
        """
        self.stop_callback = callback

    def set_restart_callback(self, callback) -> None:
        """
        设置重启回调函数

        Args:
            callback: 重启系统的回调函数
        """
        self.restart_callback = callback

    def notify_records_update(self) -> None:
        """
        通知前端记录已更新

        通过SocketIO发送更新通知
        """
        try:
            self.socketio.emit('records_update', {
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            # 静默处理，避免影响主循环
            pass

    def run(self) -> None:
        """
        运行Web应用
        """
        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=self.debug,
            allow_unsafe_werkzeug=True
        )


def create_templates_directory():
    """
    创建模板目录和基础HTML文件
    """
    from pathlib import Path

    # 创建目录
    templates_dir = Path(__file__).parent / 'templates'
    static_dir = Path(__file__).parent / 'static'
    templates_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)

    # 创建HTML模板
    html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>猫厕所监控系统</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f0f0f0; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .header { background: #333; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { margin: 0; }
        .header p { margin: 5px 0 0 0; opacity: 0.8; }
        .stop-btn { background: #dc3545; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; transition: background 0.3s; }
        .stop-btn:hover { background: #c82333; }
        .stop-btn:disabled { background: #6c757d; cursor: not-allowed; }
        .main-content { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
        .video-container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .video-feed { width: 100%; border-radius: 5px; background: #000; }
        .info-container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .status { padding: 10px; margin-bottom: 10px; border-radius: 5px; }
        .status.running { background: #d4edda; color: #155724; }
        .status.stopped { background: #f8d7da; color: #721c24; }
        .stats-item { padding: 10px; margin: 5px 0; background: #f8f9fa; border-radius: 5px; }
        .events-list { max-height: 400px; overflow-y: auto; }
        .event-item { padding: 10px; margin: 5px 0; background: #e9ecef; border-radius: 5px; }
        h2 { margin-bottom: 15px; color: #333; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>猫厕所监控系统</h1>
                <p>实时监控和统计</p>
            </div>
            <button id="stopBtn" class="stop-btn">停止服务</button>
        </div>

        <div class="main-content">
            <div class="video-container">
                <h2>实时视频</h2>
                <img src="/video_feed" class="video-feed" alt="Video Feed">
            </div>

            <div class="info-container">
                <h2>系统状态</h2>
                <div id="status" class="status">检查中...</div>

                <h2>今日统计</h2>
                <div id="statistics">
                    <p>加载中...</p>
                </div>

                <h2>最近事件</h2>
                <div id="events" class="events-list">
                    <p>加载中...</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        // 连接WebSocket
        const socket = io();
        let isRunning = true;

        socket.on('connect', function() {
            console.log('Connected to server');
        });

        socket.on('status_update', function(data) {
            isRunning = data.running;
            const statusDiv = document.getElementById('status');
            const stopBtn = document.getElementById('stopBtn');
            if (data.running) {
                statusDiv.className = 'status running';
                statusDiv.textContent = '系统运行中';
                stopBtn.disabled = false;
            } else {
                statusDiv.className = 'status stopped';
                statusDiv.textContent = '系统已停止';
                stopBtn.disabled = true;
            }
        });

        socket.on('statistics_update', function(data) {
            const statsDiv = document.getElementById('statistics');
            let html = '';
            if (data.by_cat) {
                data.by_cat.forEach(cat => {
                    html += `<div class="stats-item">
                        <strong>${cat.cat_name}</strong>: ${cat.event_count} 次
                        (平均 ${cat.avg_duration.toFixed(1)} 秒)
                    </div>`;
                });
            }
            statsDiv.innerHTML = html || '<p>暂无数据</p>';
        });

        // 停止服务按钮
        document.getElementById('stopBtn').addEventListener('click', function() {
            if (confirm('确定要停止系统服务吗？')) {
                this.disabled = true;
                this.textContent = '正在停止...';
                fetch('/api/stop', { method: 'POST' })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'stopping') {
                            alert('系统正在停止，请稍候...');
                            setTimeout(function() {
                                window.location.reload();
                            }, 3000);
                        } else {
                            alert('停止失败: ' + data.message);
                            document.getElementById('stopBtn').disabled = false;
                            document.getElementById('stopBtn').textContent = '停止服务';
                        }
                    })
                    .catch(err => {
                        alert('请求失败: ' + err);
                        document.getElementById('stopBtn').disabled = false;
                        document.getElementById('stopBtn').textContent = '停止服务';
                    });
            }
        });

        // 定期获取状态
        setInterval(function() {
            fetch('/api/status')
                .then(res => res.json())
                .then(data => {
                    isRunning = data.running;
                    const statusDiv = document.getElementById('status');
                    const stopBtn = document.getElementById('stopBtn');
                    if (data.running) {
                        statusDiv.className = 'status running';
                        statusDiv.textContent = '系统运行中';
                        stopBtn.disabled = false;
                    } else {
                        statusDiv.className = 'status stopped';
                        statusDiv.textContent = '系统已停止';
                        stopBtn.disabled = true;
                    }
                });
        }, 5000);

        // 获取统计数据
        setInterval(function() {
            fetch('/api/statistics')
                .then(res => res.json())
                .then(data => {
                    const statsDiv = document.getElementById('statistics');
                    let html = '';
                    if (data.by_cat) {
                        data.by_cat.forEach(cat => {
                            html += `<div class="stats-item">
                                <strong>${cat.cat_name}</strong>: ${cat.event_count} 次
                                (平均 ${cat.avg_duration.toFixed(1)} 秒)
                            </div>`;
                        });
                    }
                    statsDiv.innerHTML = html || '<p>暂无数据</p>';
                });
        }, 10000);

        // 获取事件列表
        setInterval(function() {
            fetch('/api/events')
                .then(res => res.json())
                .then(data => {
                    const eventsDiv = document.getElementById('events');
                    let html = '';
                    data.slice(0, 10).forEach(event => {
                        const time = new Date(event.enter_time).toLocaleTimeString();
                        html += `<div class="event-item">
                            <strong>${event.cat_name}</strong> - ${time}<br>
                            时长: ${event.duration.toFixed(1)} 秒
                        </div>`;
                    });
                    eventsDiv.innerHTML = html || '<p>暂无事件</p>';
                });
        }, 10000);
    </script>
</body>
</html>'''

    # 只在 index.html 不存在时才创建
    index_file = templates_dir / 'index.html'
    if not index_file.exists():
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
