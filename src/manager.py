"""
Manager 监控进程

该模块负责监控主进程的运行状态，当检测到连续帧读取失败超过阈值时触发重启。
"""

import os
import sys
import time
import json
import psutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志重定向（必须在所有其他 import 之前）
from src.utils.log_writer import setup_logging
setup_logging('manager')

from src.config import get_config
from src.utils.logger import get_logger, setup_logger_from_config


class ProcessManager:
    """
    进程管理器

    负责监控主进程状态，并在必要时执行重启操作。

    Attributes:
        config: 配置对象
        logger: 日志对象
        state_file: 状态文件路径
        restart_script: 重启脚本路径
        max_failures: 最大连续失败次数
        check_interval: 检查间隔（秒）
        running: 运行标志
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化进程管理器

        Args:
            config_file: 配置文件路径
        """
        # 加载配置
        self.config = get_config(config_file)

        # 初始化日志
        logging_config = self.config.get_logging_config()
        self.logger = setup_logger_from_config(logging_config)
        self.logger.info("进程管理器初始化中...")

        # 获取管理器配置
        manager_config = self.config.config.get('manager', {})
        self.max_failures = manager_config.get('max_frame_failures', 30)
        self.check_interval = manager_config.get('check_interval', 5)

        # 状态文件路径
        self.state_file = project_root / 'data' / 'manager_state.json'

        # 确保数据目录存在
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # 重启脚本路径
        self.restart_script = project_root / 'restart.bat'

        # 进程信息
        self.main_process_name = 'python.exe'  # 主进程名称
        self.go2rtc_process_name = 'go2rtc.exe'  # go2rtc 进程名称

        # 运行标志
        self.running = False

        # 记录上次重启时间
        self.last_restart_time = 0
        self.restart_cooldown = 60  # 重启冷却时间（秒）

        self.logger.info(f"最大连续失败次数: {self.max_failures}")
        self.logger.info(f"检查间隔: {self.check_interval}秒")
        self.logger.info("进程管理器初始化完成")

    def read_state(self) -> Dict[str, Any]:
        """
        读取状态文件

        Returns:
            状态字典
        """
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {
                'consecutive_failures': 0,
                'last_update': time.time(),
                'status': 'running'
            }
        except Exception as e:
            self.logger.error(f"读取状态文件失败: {e}")
            return {
                'consecutive_failures': 0,
                'last_update': time.time(),
                'status': 'unknown'
            }

    def write_state(self, state: Dict[str, Any]) -> None:
        """
        写入状态文件

        Args:
            state: 状态字典
        """
        try:
            state['last_update'] = time.time()
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"写入状态文件失败: {e}")

    def check_process_alive(self, process_name: str) -> bool:
        """
        检查进程是否存活

        Args:
            process_name: 进程名称

        Returns:
            进程是否存活
        """
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == process_name:
                    return True
            return False
        except Exception as e:
            self.logger.error(f"检查进程失败 ({process_name}): {e}")
            return False

    def should_restart(self) -> bool:
        """
        判断是否需要重启

        Returns:
            是否需要重启
        """
        state = self.read_state()

        # 检查连续失败次数
        consecutive_failures = state.get('consecutive_failures', 0)

        if consecutive_failures >= self.max_failures:
            self.logger.warning(f"检测到连续帧失败次数: {consecutive_failures}，超过阈值 {self.max_failures}")
            return True

        # 检查状态是否正常更新
        last_update = state.get('last_update', 0)
        current_time = time.time()
        update_threshold = self.check_interval * 3  # 超过3倍检查间隔未更新则认为异常

        if current_time - last_update > update_threshold:
            self.logger.warning(f"状态文件未更新时间过长: {current_time - last_update:.1f}秒")
            # 检查主进程是否还活着
            if not self.check_process_alive(self.main_process_name):
                self.logger.error("主进程未运行，需要重启")
                return True

        return False

    def execute_restart(self) -> bool:
        """
        执行重启操作

        Returns:
            重启是否成功
        """
        current_time = time.time()

        # 检查冷却时间
        if current_time - self.last_restart_time < self.restart_cooldown:
            self.logger.warning(f"重启冷却中，距离上次重启仅 {current_time - self.last_restart_time:.1f}秒")
            return False

        self.logger.info("开始执行重启操作...")
        self.last_restart_time = current_time

        try:
            # 调用重启脚本
            if self.restart_script.exists():
                self.logger.info(f"执行重启脚本: {self.restart_script}")

                # 使用 subprocess 在后台执行重启脚本
                # 参考 discord bridge 的调用方式，使用 cmd /c
                subprocess.Popen(
                    ["cmd", "/c", str(self.restart_script)],
                    cwd=str(project_root),
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )

                self.logger.info("重启脚本已启动")
                return True
            else:
                self.logger.error(f"重启脚本不存在: {self.restart_script}")
                return False

        except Exception as e:
            self.logger.error(f"执行重启失败: {e}")
            return False

    def monitor(self) -> None:
        """
        监控主循环

        持续检查主进程状态，并在必要时执行重启。
        """
        self.logger.info("启动监控...")
        self.running = True

        try:
            while self.running:
                # 检查是否需要重启
                if self.should_restart():
                    if self.execute_restart():
                        self.logger.info("重启操作已触发，等待系统恢复...")
                        # 重启后等待较长时间再继续监控
                        time.sleep(30)
                    else:
                        # 重启失败或冷却中，等待较短时间
                        time.sleep(self.check_interval)
                else:
                    # 正常状态，读取状态并记录
                    state = self.read_state()
                    failures = state.get('consecutive_failures', 0)
                    status = state.get('status', 'unknown')

                    if failures > 0:
                        self.logger.info(f"当前连续失败次数: {failures}")

                    # 等待下次检查
                    time.sleep(self.check_interval)

        except KeyboardInterrupt:
            self.logger.info("接收到中断信号，停止监控...")
        except Exception as e:
            self.logger.error(f"监控循环异常: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
        finally:
            self.running = False
            self.logger.info("监控已停止")

    def stop(self) -> None:
        """
        停止监控
        """
        self.logger.info("停止进程管理器...")
        self.running = False


def main():
    """
    主函数
    """
    import argparse

    parser = argparse.ArgumentParser(description='猫咪监控系统 - 进程管理器')
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径'
    )

    args = parser.parse_args()

    # 创建并启动进程管理器
    manager = ProcessManager(config_file=args.config)
    manager.monitor()


if __name__ == '__main__':
    main()
