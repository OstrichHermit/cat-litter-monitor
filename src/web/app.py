"""
Web界面模块

该模块提供Flask Web应用，用于实时视频流展示和统计数据查看。
"""

from flask import Flask, render_template, Response, jsonify, send_from_directory
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
        self.database = database

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
            """主页"""
            return render_template('index.html')

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

        @self.app.route('/api/stop', methods=['POST'])
        def stop_service():
            """停止系统服务"""
            if self.stop_callback:
                # 在新线程中调用停止回调，避免响应超时
                import threading
                threading.Thread(target=self.stop_callback, daemon=True).start()
                return jsonify({'status': 'stopping', 'message': '系统正在停止...'})
            return jsonify({'status': 'error', 'message': '停止回调未设置'}), 500

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
        while True:
            if self.system_state['frame'] is not None:
                # 编码为JPEG
                ret, buffer = cv2.imencode('.jpg', self.system_state['frame'])
                if ret:
                    frame = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    def update_frame(self, frame: np.ndarray) -> None:
        """
        更新当前帧

        Args:
            frame: 视频帧
        """
        self.system_state['frame'] = frame.copy()

    def update_detections(self, detections: list) -> None:
        """
        更新检测结果

        Args:
            detections: 检测列表
        """
        self.system_state['detections'] = [
            d.to_dict() if hasattr(d, 'to_dict') else d
            for d in detections
        ]

    def update_tracks(self, tracks: list) -> None:
        """
        更新追踪结果

        Args:
            tracks: 追踪列表
        """
        self.system_state['tracks'] = [
            {'id': t.track_id, 'bbox': t.bbox if hasattr(t, 'bbox') else t.tlwh.tolist()}
            for t in tracks
        ]

    def update_events(self, events: list) -> None:
        """
        更新事件列表

        Args:
            events: 事件列表
        """
        self.system_state['events'] = events

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

    def notify_records_update(self) -> None:
        """
        通知前端记录已更新

        通过SocketIO发送更新通知
        """
        self.socketio.emit('records_update', {
            'timestamp': datetime.now().isoformat()
        })

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
