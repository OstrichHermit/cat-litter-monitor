"""
MCP服务器入口

该模块提供MCP服务器的主要功能，用于管理猫厕所监控系统的外部接口。
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    # 如果没有安装mcp包，提供一个简单的替代实现
    print("警告: MCP包未安装，请运行: pip install mcp")
    print("将使用简化模式运行...")
    Server = None
    Tool = None
    TextContent = None

from src.storage.database import Database
from src.storage.photo_manager import PhotoManager
from src.config import get_config
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LitterMonitorMCPServer:
    """
    猫厕所监控系统MCP服务器

    提供外部工具接口，用于添加记录、查询数据等操作。
    """

    def __init__(self):
        """初始化MCP服务器"""
        # 加载配置
        self.config = get_config()

        # 初始化数据库
        database_config = self.config.get_database_config()
        db_path = self.config.get_absolute_path(
            database_config.get('path', 'data/litter_monitor.db')
        )
        self.database = Database(db_path=db_path)

        # 初始化照片管理器
        photo_config = self.config.get_photo_config()
        photo_base_dir = photo_config.get('photo_base_dir', 'photo')
        self.photo_manager = PhotoManager(photo_base_dir)

        logger.info("MCP服务器初始化完成")

    def add_litter_records(self, records: list) -> dict:
        """
        批量添加猫砂盆使用记录

        Args:
            records: 记录列表，每条记录包含：
                - cat_name: 猫咪名称（必须是：小巫、猪猪、汪三、猪妞）
                - date: 日期 (YYYY-MM-DD)
                - time: 时间 (HH:MM:SS)
                - photo_path: 照片路径
                - roi_id: ROI区域ID（可选，默认为1）

        Returns:
            操作结果字典
        """
        # 固定的猫咪名字
        VALID_CAT_NAMES = {'小巫', '猪猪', '汪三', '猪妞'}

        try:
            logger.info(f"收到 {len(records)} 条记录添加请求")

            # 验证记录
            for i, record in enumerate(records):
                # 检查必需字段
                if not all(k in record for k in ['cat_name', 'date', 'time', 'photo_path']):
                    return {
                        'success': False,
                        'error': f'记录 {i+1} 缺少必需字段'
                    }

                # 验证猫咪名字
                cat_name = record['cat_name']
                if cat_name not in VALID_CAT_NAMES:
                    return {
                        'success': False,
                        'error': f'记录 {i+1} 的猫咪名字无效: "{cat_name}"。必须是: 小巫、猪猪、汪三、猪妞'
                    }

            # 统计每张照片被引用的次数
            photo_usage = {}  # photo_path -> count
            for record in records:
                photo_path = record['photo_path']
                photo_usage[photo_path] = photo_usage.get(photo_path, 0) + 1

            # 处理照片（移动或复制）
            moved_photos = []
            photo_path_mapping = {}  # 旧路径 -> 新路径的映射
            photo_copy_indices = {}  # photo_path -> 该照片当前是第几份副本
            first_moved_paths = {}  # photo_path -> 第一只猫移动后的完整路径

            for record in records:
                photo_path = record['photo_path']
                cat_name = record['cat_name']
                date_str = record['date']

                # 检查这张照片是否被多次引用
                usage_count = photo_usage[photo_path]

                if usage_count == 1:
                    # 只被引用一次，直接移动
                    new_path = self.photo_manager.move_photo(
                        photo_path, cat_name, date_str
                    )
                    if new_path:
                        photo_path_mapping[photo_path] = new_path
                        moved_photos.append({
                            'old_path': photo_path,
                            'new_path': new_path,
                            'action': 'move'
                        })
                else:
                    # 被多次引用，需要复制
                    # 初始化副本计数器
                    if photo_path not in photo_copy_indices:
                        photo_copy_indices[photo_path] = 0

                    # 第一只猫：移动照片
                    if photo_copy_indices[photo_path] == 0:
                        new_path = self.photo_manager.move_photo(
                            photo_path, cat_name, date_str
                        )
                        if new_path:
                            # 保存移动后的完整路径，供后续复制使用
                            first_moved_paths[photo_path] = new_path
                            photo_path_mapping[photo_path] = new_path
                            moved_photos.append({
                                'old_path': photo_path,
                                'new_path': new_path,
                                'action': 'move'
                            })
                        photo_copy_indices[photo_path] += 1
                    else:
                        # 后续的猫：从第一只猫移动后的位置复制照片
                        if photo_path in first_moved_paths:
                            # 转换相对路径为绝对路径
                            from src.config import get_config
                            config = get_config()
                            source_abs_path = config.get_absolute_path(first_moved_paths[photo_path])

                            copy_suffix = f"_copy{photo_copy_indices[photo_path]}"
                            new_path = self.photo_manager.copy_photo_from_source(
                                source_abs_path, cat_name, date_str, copy_suffix
                            )
                            if new_path:
                                # 使用新路径创建映射（键是原路径+索引，以区分不同副本）
                                map_key = f"{photo_path}_{photo_copy_indices[photo_path]}"
                                photo_path_mapping[map_key] = new_path
                                moved_photos.append({
                                    'old_path': photo_path,
                                    'new_path': new_path,
                                    'action': 'copy',
                                    'copy_suffix': copy_suffix
                                })
                        photo_copy_indices[photo_path] += 1

            # 使用新路径创建记录
            records_with_new_paths = []
            photo_current_copy = {}  # photo_path -> 当前副本索引

            for record in records:
                new_record = record.copy()
                old_path = record['photo_path']
                usage_count = photo_usage[old_path]

                if usage_count == 1:
                    # 只被引用一次，使用移动后的路径
                    if old_path in photo_path_mapping:
                        new_record['photo_path'] = photo_path_mapping[old_path]
                else:
                    # 被多次引用，需要追踪副本索引
                    if old_path not in photo_current_copy:
                        photo_current_copy[old_path] = 0

                    # 第一只猫使用移动后的路径
                    if photo_current_copy[old_path] == 0:
                        if old_path in photo_path_mapping:
                            new_record['photo_path'] = photo_path_mapping[old_path]
                    else:
                        # 后续的猫使用复制后的路径
                        map_key = f"{old_path}_{photo_current_copy[old_path]}"
                        if map_key in photo_path_mapping:
                            new_record['photo_path'] = photo_path_mapping[map_key]

                    photo_current_copy[old_path] += 1

                records_with_new_paths.append(new_record)

            # 插入数据库（使用更新后的路径）
            record_ids = self.database.insert_litter_records_batch(records_with_new_paths)

            # 更新每日统计
            from datetime import date
            today = date.today()
            self.database.update_daily_statistics(today)

            logger.info(f"成功添加 {len(record_ids)} 条记录")

            return {
                'success': True,
                'record_ids': record_ids,
                'moved_photos': moved_photos,
                'message': f'成功添加 {len(record_ids)} 条记录'
            }

        except Exception as e:
            logger.error(f"添加记录失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_litter_records(
        self,
        start_date: str = None,
        end_date: str = None,
        cat_name: str = None,
        limit: int = 100
    ) -> dict:
        """
        获取猫砂盆使用记录

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            cat_name: 猫咪名称（可选）
            limit: 返回数量限制

        Returns:
            操作结果字典
        """
        try:
            from datetime import datetime

            # 转换日期
            start = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
            end = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None

            # 获取猫咪ID
            cat_id = None
            if cat_name:
                cat = self.database.get_cat_by_name(cat_name)
                if cat:
                    cat_id = cat['id']

            # 查询记录
            records = self.database.get_litter_records(
                start_date=start,
                end_date=end,
                cat_id=cat_id,
                limit=limit
            )

            return {
                'success': True,
                'records': records,
                'count': len(records)
            }

        except Exception as e:
            logger.error(f"查询记录失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_daily_statistics(self, record_date: str = None) -> dict:
        """
        获取每日统计

        Args:
            record_date: 日期 (YYYY-MM-DD)，如果为None则返回今天

        Returns:
            操作结果字典
        """
        try:
            from datetime import datetime

            # 转换日期
            date_obj = None
            if record_date:
                date_obj = datetime.strptime(record_date, '%Y-%m-%d').date()

            # 查询统计
            stats = self.database.get_daily_statistics(date_obj)

            return {
                'success': True,
                'statistics': stats,
                'count': len(stats)
            }

        except Exception as e:
            logger.error(f"查询统计失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_unidentified_photos(self) -> dict:
        """
        获取未识别的照片列表

        Returns:
            操作结果字典
        """
        try:
            photos = self.photo_manager.get_unidentified_photos()

            return {
                'success': True,
                'photos': photos,
                'count': len(photos)
            }

        except Exception as e:
            logger.error(f"获取未识别照片失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def mark_unidentifiable(self, photo_path: str) -> dict:
        """
        将无法识别的照片标记为无法识别，移动到 Unidentifiable 文件夹

        Args:
            photo_path: 照片路径

        Returns:
            操作结果字典
        """
        try:
            import re

            # 从路径中提取日期 (YYYY-MM-DD)
            match = re.search(r'(\d{4}-\d{2}-\d{2})', photo_path)
            if not match:
                return {
                    'success': False,
                    'error': f'无法从路径中提取日期: {photo_path}'
                }

            date_str = match.group(1)

            new_path = self.photo_manager.move_to_unidentifiable(photo_path, date_str)

            if new_path:
                return {
                    'success': True,
                    'new_path': new_path,
                    'message': '已标记为无法识别'
                }
            else:
                return {
                    'success': False,
                    'error': '移动照片失败'
                }

        except Exception as e:
            logger.error(f"标记照片为无法识别失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }


# 全局服务器实例
_server_instance = None


def get_server():
    """获取MCP服务器实例"""
    global _server_instance
    if _server_instance is None:
        _server_instance = LitterMonitorMCPServer()
    return _server_instance


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='猫厕所监控系统MCP服务器')
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径'
    )
    parser.add_argument(
        '--mode',
        type=str,
        default='stdio',
        choices=['stdio', 'simple'],
        help='运行模式'
    )

    args = parser.parse_args()

    # 创建服务器实例
    server = LitterMonitorMCPServer()

    if args.mode == 'stdio' and Server is not None:
        # 使用标准MCP服务器
        mcp_server = Server("cat-litter-monitor")

        # 注册工具
        @mcp_server.list_tools()
        async def list_tools() -> list[Tool]:
            """列出可用工具"""
            return [
                Tool(
                    name="add_litter_records",
                    description="批量添加猫砂盆使用记录。猫咪名字只能是：小巫、猪猪、汪三、猪妞",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "records": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "cat_name": {
                                            "type": "string",
                                            "enum": ["小巫", "猪猪", "汪三", "猪妞"],
                                            "description": "猫咪名字（必须是四只猫之一）"
                                        },
                                        "date": {
                                            "type": "string",
                                            "description": "日期 (YYYY-MM-DD)"
                                        },
                                        "time": {
                                            "type": "string",
                                            "description": "时间 (HH:MM:SS)"
                                        },
                                        "photo_path": {
                                            "type": "string",
                                            "description": "照片路径"
                                        }
                                    },
                                    "required": ["cat_name", "date", "time", "photo_path"]
                                }
                            }
                        },
                        "required": ["records"]
                    }
                ),
                Tool(
                    name="get_litter_records",
                    description="获取猫砂盆使用记录",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"},
                            "cat_name": {"type": "string"}
                        }
                    }
                ),
                Tool(
                    name="get_daily_statistics",
                    description="获取每日统计",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "record_date": {"type": "string"}
                        }
                    }
                ),
                Tool(
                    name="get_unidentified_photos",
                    description="获取未识别的照片列表",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="mark_unidentifiable",
                    description="将无法识别的照片标记为无法识别，移动到 Unidentifiable 文件夹",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "photo_path": {
                                "type": "string",
                                "description": "照片路径"
                            }
                        },
                        "required": ["photo_path"]
                    }
                )
            ]

        @mcp_server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """调用工具"""
            if name == "add_litter_records":
                result = server.add_litter_records(arguments.get("records", []))
            elif name == "get_litter_records":
                result = server.get_litter_records(
                    start_date=arguments.get("start_date"),
                    end_date=arguments.get("end_date"),
                    cat_name=arguments.get("cat_name"),
                    limit=100
                )
            elif name == "get_daily_statistics":
                result = server.get_daily_statistics(
                    record_date=arguments.get("record_date")
                )
            elif name == "get_unidentified_photos":
                result = server.get_unidentified_photos()
            elif name == "mark_unidentifiable":
                result = server.mark_unidentifiable(arguments.get("photo_path"))
            else:
                result = {"success": False, "error": f"未知工具: {name}"}

            return [TextContent(type="text", text=str(result))]

        # 运行服务器
        async def run():
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                await mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp_server.create_initialization_options()
                )

        import asyncio
        asyncio.run(run())

    else:
        # 简单模式（用于测试）
        logger.info("运行在简单模式（仅用于测试）")
        logger.info("可用方法:")
        logger.info("  - add_litter_records(records)")
        logger.info("  - get_litter_records(start_date, end_date, cat_name, limit)")
        logger.info("  - get_daily_statistics(record_date)")
        logger.info("  - get_unidentified_photos()")

        # 保持运行
        import time
        while True:
            time.sleep(1)


if __name__ == '__main__':
    main()
