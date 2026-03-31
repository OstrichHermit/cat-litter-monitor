"""
日志输出重定向模块

将 stdout/stderr 同时输出到终端和日志文件，支持 pythonw.exe（无控制台）模式。
"""

import sys
import os
from pathlib import Path


class TeeWriter:
    """同时写入终端和日志文件的包装器"""

    def __init__(self, terminal, log_file):
        self.terminal = terminal  # 可能是 None（pythonw.exe 模式）
        self.log_file = log_file

    def write(self, message):
        if message:  # 跳过空写入
            if self.terminal is not None:
                try:
                    self.terminal.write(message)
                except Exception:
                    pass
            if self.log_file is not None:
                try:
                    self.log_file.write(message)
                    self.log_file.flush()
                except Exception:
                    pass

    def flush(self):
        if self.terminal is not None:
            try:
                self.terminal.flush()
            except Exception:
                pass
        if self.log_file is not None:
            try:
                self.log_file.flush()
            except Exception:
                pass

    def isatty(self):
        if self.terminal is not None:
            return self.terminal.isatty()
        return False


def setup_logging(service_name: str):
    """
    设置日志重定向，将 stdout/stderr 同时输出到日志文件。

    必须在所有其他 import 之前调用，确保所有输出都被捕获。

    Args:
        service_name: 服务名称，用于日志文件名（如 'main', 'manager'）
    """
    project_root = Path(__file__).parent.parent.parent
    log_dir = project_root / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f'{service_name}.log'
    log_file = open(log_path, 'a', encoding='utf-8')

    # 写入分隔线标记新会话
    log_file.write(f'\n{"="*60}\n')
    log_file.write(f'Service: {service_name} | Started at: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
    log_file.write(f'{"="*60}\n')
    log_file.flush()

    # 替换 stdout 和 stderr
    sys.stdout = TeeWriter(sys.stdout, log_file)
    sys.stderr = TeeWriter(sys.stderr, log_file)
