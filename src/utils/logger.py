"""
日志模块

该模块提供统一的日志记录接口，支持文件日志和控制台输出，
并支持日志轮转。
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import colorlog


class Logger:
    """
    日志管理类

    该类负责配置和管理系统日志，支持文件日志、控制台输出和日志轮转。

    Attributes:
        logger: logger实例
        log_dir: 日志目录
        log_file: 日志文件路径
    """

    # 日志级别映射
    LOG_LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    def __init__(
        self,
        name: str = 'LitterMonitor',
        log_file: Optional[str] = None,
        level: str = 'INFO',
        log_dir: Optional[str] = None,
        console: bool = True,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5
    ):
        """
        初始化日志管理器

        Args:
            name: logger名称
            log_file: 日志文件名（不含路径）
            level: 日志级别
            log_dir: 日志目录，如果为None则使用项目根目录下的logs目录
            console: 是否输出到控制台
            max_bytes: 日志文件最大大小（字节）
            backup_count: 备份文件数量
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.LOG_LEVELS.get(level.upper(), logging.INFO))

        # 避免重复添加handler
        if self.logger.handlers:
            return

        # 设置日志目录
        if log_dir is None:
            project_root = Path(__file__).parent.parent.parent
            log_dir = project_root / 'logs'
        else:
            log_dir = Path(log_dir)

        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 设置日志文件
        if log_file is None:
            log_file = 'litter_monitor.log'

        self.log_file = self.log_dir / log_file

        # 创建formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 添加文件处理器
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # 添加控制台处理器（只输出消息，时间戳由 TeeWriter 统一添加）
        if console:
            console_handler = colorlog.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(message)s',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

    def debug(self, message: str) -> None:
        """
        记录DEBUG级别日志

        Args:
            message: 日志消息
        """
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """
        记录INFO级别日志

        Args:
            message: 日志消息
        """
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """
        记录WARNING级别日志

        Args:
            message: 日志消息
        """
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """
        记录ERROR级别日志

        Args:
            message: 日志消息
        """
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """
        记录CRITICAL级别日志

        Args:
            message: 日志消息
        """
        self.logger.critical(message)

    def exception(self, message: str) -> None:
        """
        记录异常信息

        Args:
            message: 日志消息
        """
        self.logger.exception(message)

    def set_level(self, level: str) -> None:
        """
        设置日志级别

        Args:
            level: 日志级别字符串
        """
        self.logger.setLevel(self.LOG_LEVELS.get(level.upper(), logging.INFO))

    def get_logger(self) -> logging.Logger:
        """
        获取logger实例

        Returns:
            logger实例
        """
        return self.logger


# 全局logger实例
_global_logger: Optional[Logger] = None


def get_logger(
    name: str = 'LitterMonitor',
    log_file: Optional[str] = None,
    level: str = 'INFO',
    log_dir: Optional[str] = None,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5
) -> Logger:
    """
    获取全局logger实例

    Args:
        name: logger名称
        log_file: 日志文件名
        level: 日志级别
        log_dir: 日志目录
        console: 是否输出到控制台
        max_bytes: 日志文件最大大小（字节）
        backup_count: 备份文件数量

    Returns:
        Logger实例
    """
    global _global_logger

    if _global_logger is None:
        _global_logger = Logger(
            name=name,
            log_file=log_file,
            level=level,
            log_dir=log_dir,
            console=console,
            max_bytes=max_bytes,
            backup_count=backup_count
        )

    return _global_logger


def setup_logger_from_config(config: dict) -> Logger:
    """
    从配置字典设置logger

    Args:
        config: 日志配置字典，应包含以下键：
            - level: 日志级别
            - file: 日志文件名
            - console: 是否输出到控制台
            - max_bytes: 日志文件最大大小（MB）
            - backup_count: 备份文件数量

    Returns:
        Logger实例
    """
    level = config.get('level', 'INFO')
    log_file = config.get('file', 'litter_monitor.log')
    console = config.get('console', True)
    max_bytes = config.get('max_bytes', 10) * 1024 * 1024
    backup_count = config.get('backup_count', 5)

    # 从路径中提取文件名（Logger 类会自动在 logs 目录下创建）
    import os
    log_file = os.path.basename(log_file)

    return get_logger(
        level=level,
        log_file=log_file,
        console=console,
        max_bytes=max_bytes,
        backup_count=backup_count
    )
