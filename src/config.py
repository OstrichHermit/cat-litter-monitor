"""
配置管理模块

该模块负责加载和管理系统配置，支持从YAML文件读取配置，
并提供配置访问接口。
"""

import os
import yaml
from typing import Dict, Any, Optional, Tuple
from pathlib import Path


class Config:
    """
    配置管理类

    该类负责加载和管理系统配置，支持从YAML文件读取配置，
    并提供配置访问接口。

    Attributes:
        config_dir: 配置文件目录
        config_file: 配置文件路径
        config: 配置字典
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_file: 配置文件路径，如果为None则使用默认配置文件
        """
        # 获取项目根目录
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"

        # 设置配置文件路径
        if config_file is None:
            config_file = self.config_dir / "default.yaml"
        else:
            config_file = Path(config_file)

        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件

        Returns:
            配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML文件格式错误
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_file}")

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"配置文件格式错误: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        支持点号分隔的嵌套键，例如: "camera.width"

        Args:
            key: 配置键，支持嵌套（用点号分隔）
            default: 默认值

        Returns:
            配置值，如果不存在则返回默认值
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        设置配置值

        支持点号分隔的嵌套键，例如: "camera.width"

        Args:
            key: 配置键，支持嵌套（用点号分隔）
            value: 配置值
        """
        keys = key.split('.')
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, config_file: Optional[str] = None) -> None:
        """
        保存配置到文件

        Args:
            config_file: 配置文件路径，如果为None则使用当前配置文件
        """
        if config_file is None:
            config_file = self.config_file
        else:
            config_file = Path(config_file)

        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)

    def get_camera_config(self) -> Dict[str, Any]:
        """
        获取摄像头配置

        Returns:
            摄像头配置字典
        """
        return self.config.get('camera', {})

    def get_detection_config(self) -> Dict[str, Any]:
        """
        获取检测配置

        Returns:
            检测配置字典
        """
        return self.config.get('detection', {})

    def get_tracking_config(self) -> Dict[str, Any]:
        """
        获取追踪配置

        Returns:
            追踪配置字典
        """
        return self.config.get('tracking', {})

    def get_classifier_config(self) -> Dict[str, Any]:
        """
        获取分类器配置

        Returns:
            分类器配置字典
        """
        return self.config.get('classifier', {})

    def get_roi_config(self) -> Dict[str, Any]:
        """
        获取ROI配置

        Returns:
            ROI配置字典
        """
        return self.config.get('roi', {})

    def get_behavior_config(self) -> Dict[str, Any]:
        """
        获取行为分析配置

        Returns:
            行为分析配置字典
        """
        return self.config.get('behavior', {})

    def get_database_config(self) -> Dict[str, Any]:
        """
        获取数据库配置

        Returns:
            数据库配置字典
        """
        return self.config.get('database', {})

    def get_logging_config(self) -> Dict[str, Any]:
        """
        获取日志配置

        Returns:
            日志配置字典
        """
        return self.config.get('logging', {})

    def get_web_config(self) -> Dict[str, Any]:
        """
        获取Web界面配置

        Returns:
            Web界面配置字典
        """
        return self.config.get('web', {})

    def get_system_config(self) -> Dict[str, Any]:
        """
        获取系统配置

        Returns:
            系统配置字典
        """
        return self.config.get('system', {})

    def get_cat_names(self) -> list:
        """
        获取猫的名称列表

        Returns:
            猫的名称列表
        """
        return self.config.get('cats', [])

    def get_cat_colors_config(self) -> Dict[str, Tuple[int, int, int]]:
        """
        获取猫的颜色配置

        Returns:
            猫名字到BGR颜色元组的映射字典
        """
        cat_colors = self.config.get('cat_colors', {})

        # 转换为元组格式
        color_dict = {}
        for cat_name, color_list in cat_colors.items():
            if isinstance(color_list, list) and len(color_list) == 3:
                color_dict[cat_name] = tuple(color_list)
            else:
                # 默认颜色（蓝色）
                color_dict[cat_name] = (255, 0, 0)

        return color_dict

    def get_absolute_path(self, relative_path: str) -> str:
        """
        将相对路径转换为绝对路径

        Args:
            relative_path: 相对路径（相对于项目根目录）

        Returns:
            绝对路径
        """
        return str(self.project_root / relative_path)

    def __repr__(self) -> str:
        """
        返回配置的字符串表示

        Returns:
            配置的字符串表示
        """
        return f"Config(config_file={self.config_file})"


# 全局配置实例
_global_config: Optional[Config] = None


def get_config(config_file: Optional[str] = None) -> Config:
    """
    获取全局配置实例

    Args:
        config_file: 配置文件路径，仅在首次调用时有效

    Returns:
        配置实例
    """
    global _global_config

    if _global_config is None:
        _global_config = Config(config_file)

    return _global_config


def reload_config(config_file: Optional[str] = None) -> Config:
    """
    重新加载配置

    Args:
        config_file: 配置文件路径

    Returns:
        配置实例
    """
    global _global_config
    _global_config = Config(config_file)
    return _global_config
