"""
日志输出重定向模块

将 stdout/stderr 同时输出到终端和日志文件，支持 pythonw.exe（无控制台）模式。
"""

import sys
import os
from pathlib import Path
from datetime import datetime


class TeeWriter:
    """同时写入终端和日志文件的包装器"""

    def __init__(self, terminal, log_file):
        self.terminal = terminal  # 可能是 None（pythonw.exe 模式）
        self.log_file = log_file
        self.buffer = ""  # 行缓冲，用于累积不完整的写入和拆分的 UTF-8 序列

    def _flush_buffer_to_file(self):
        """将缓冲区中未完成的行加上时间戳写入文件"""
        if self.buffer and self.log_file is not None:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_file.write(f"[{timestamp}] {self.buffer}")
                self.buffer = ""
                self.log_file.flush()
            except Exception:
                pass

    def write(self, message):
        if not message:  # 跳过空写入
            return

        # 终端输出保持原始内容，不添加时间戳
        if self.terminal is not None:
            try:
                self.terminal.write(message)
            except Exception:
                pass

        if self.log_file is None:
            return

        # 累积到缓冲区，解决 UTF-8 多字节序列被拆分的问题
        self.buffer += message

        # 按行处理：遇到换行符时将缓冲区内容按行拆分，逐行加时间戳
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            # 最后一个元素是不包含换行符的残余部分，留在缓冲区
            self.buffer = lines[-1]
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for line in lines[:-1]:
                    self.log_file.write(f"[{timestamp}] {line}\n")
                self.log_file.flush()
            except Exception:
                pass

    def flush(self):
        # 将缓冲区中未完成的行写入文件
        self._flush_buffer_to_file()
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
