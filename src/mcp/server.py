"""
MCP服务器入口

该模块提供MCP服务器的主要功能，用于管理猫厕所监控系统的外部接口。
基于 FastMCP 框架，支持 stdio 和 HTTP 两种传输模式。
"""

import sys
from pathlib import Path
from typing import Optional

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 日志重定向（必须在其他 import 之前，捕获所有输出到 logs/mcp.log）
from src.utils.log_writer import setup_logging
setup_logging('mcp')

import json
import logging
import argparse
from fastmcp import FastMCP

from src.storage.database import Database
from src.storage.photo_manager import PhotoManager
from src.config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# FastMCP 实例
mcp = FastMCP('cat-litter-monitor')


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

    def get_valid_cat_names(self) -> set:
        """获取有效的猫咪名字集合"""
        try:
            return set(self.config.get_cat_names())
        except Exception:
            return {'小巫', '猪猪', '汪三', '猪妞'}

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
        # 从配置读取猫咪名字
        VALID_CAT_NAMES = self.get_valid_cat_names()

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
                        'error': f'记录 {i+1} 的猫咪名字无效: "{cat_name}"。必须是: {", ".join(sorted(VALID_CAT_NAMES))}'
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


# ==================== MCP 工具注册 ====================

@mcp.tool
async def add_litter_records(records: list) -> str:
    """
    批量添加猫砂盆使用记录

    将猫砂盆使用记录批量添加到数据库，并自动处理照片文件的移动和复制。
    当同一张照片中有多只猫咪时，会为每只猫创建单独的记录。

    Args:
        records: 记录列表，每条记录包含：
            - cat_name: 猫咪名称（必须是小巫、猪猪、汪三、猪妞之一）
            - date: 日期 (YYYY-MM-DD)
            - time: 时间 (HH:MM:SS)
            - photo_path: 照片路径

    Returns:
        JSON 格式的操作结果，包含成功状态、记录ID列表和照片处理信息

    Examples:
        # 添加单条记录
        add_litter_records(records=[{
            "cat_name": "小巫",
            "date": "2025-01-15",
            "time": "08:30:00",
            "photo_path": "photo/2025-01-15/photo_001.jpg"
        }])

        # 同一张照片有多只猫
        add_litter_records(records=[
            {"cat_name": "小巫", "date": "2025-01-15", "time": "08:30:00", "photo_path": "photo/2025-01-15/photo_001.jpg"},
            {"cat_name": "猪猪", "date": "2025-01-15", "time": "08:30:00", "photo_path": "photo/2025-01-15/photo_001.jpg"}
        ])

    Note:
        - 猫咪名字必须是系统配置中的有效名称
        - 照片会被自动移动到对应猫咪的目录下
        - 如果同一张照片引用多次，第一只猫移动原图，后续的猫使用副本
    """
    server = get_server()
    result = server.add_litter_records(records)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_litter_records(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    cat_name: Optional[str] = None,
    limit: int = 100
) -> str:
    """
    获取猫砂盆使用记录

    按条件查询猫砂盆使用记录，支持日期范围和猫咪名称过滤。

    Args:
        start_date: 开始日期 (YYYY-MM-DD)，可选
        end_date: 结束日期 (YYYY-MM-DD)，可选
        cat_name: 猫咪名称（可选），用于过滤特定猫咪的记录
        limit: 返回数量限制，默认 100

    Returns:
        JSON 格式的查询结果，包含记录列表和总数

    Examples:
        # 获取所有记录（默认100条）
        get_litter_records()

        # 获取指定日期范围的记录
        get_litter_records(start_date="2025-01-01", end_date="2025-01-31")

        # 获取特定猫咪的记录
        get_litter_records(cat_name="小巫", limit=50)

    Note:
        - 不传日期参数则不限制日期范围
        - 不传猫咪名称则返回所有猫咪的记录
        - 结果按时间倒序排列
    """
    server = get_server()
    result = server.get_litter_records(
        start_date=start_date,
        end_date=end_date,
        cat_name=cat_name,
        limit=limit
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_daily_statistics(record_date: Optional[str] = None) -> str:
    """
    获取每日统计数据

    获取指定日期的猫砂盆使用统计数据，包括各猫咪的使用次数等信息。

    Args:
        record_date: 日期 (YYYY-MM-DD)，可选。如果不传则返回今天的统计

    Returns:
        JSON 格式的统计数据，包含各猫咪的使用次数等汇总信息

    Examples:
        # 获取今天的统计
        get_daily_statistics()

        # 获取指定日期的统计
        get_daily_statistics(record_date="2025-01-15")

    Note:
        - 不传日期参数则默认返回今天的统计
        - 统计数据通常由系统自动维护
    """
    server = get_server()
    result = server.get_daily_statistics(record_date=record_date)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_unidentified_photos() -> str:
    """
    获取未识别的照片列表

    获取待识别目录中所有尚未被识别（未关联到具体猫咪）的照片列表。
    这些照片通常由监控摄像头自动拍摄，等待人工或AI识别。

    Returns:
        JSON 格式的照片列表，包含每张照片的路径和文件名

    Examples:
        # 获取所有未识别的照片
        get_unidentified_photos()

    Note:
        - 返回的照片位于待识别目录中
        - 可以配合 mark_unidentifiable 工具标记无法识别的照片
    """
    server = get_server()
    result = server.get_unidentified_photos()
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def mark_unidentifiable(photo_path: str) -> str:
    """
    将无法识别的照片标记为无法识别

    将一张无法确认猫咪身份的照片移动到 Unidentifiable 文件夹，
    避免重复识别浪费资源。

    Args:
        photo_path: 照片路径（必需），待识别照片的相对或绝对路径

    Returns:
        JSON 格式的操作结果，包含移动后的新路径

    Examples:
        # 标记一张照片为无法识别
        mark_unidentifiable(photo_path="photo/unidentified/2025-01-15/photo_001.jpg")

    Note:
        - 照片路径中必须包含日期信息 (YYYY-MM-DD 格式)
        - 标记后照片会被移动到 Unidentifiable 目录，不再出现在未识别列表中
        - 此操作不可逆，标记后的照片需要手动恢复
    """
    server = get_server()
    result = server.mark_unidentifiable(photo_path=photo_path)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 启动入口 ====================

def run_server(transport: str = 'stdio', host: str = '0.0.0.0', port: int = 5001):
    """
    启动 MCP 服务器

    Args:
        transport: 传输模式，'stdio' 或 'http'
        host: HTTP模式的监听地址，默认 0.0.0.0
        port: HTTP模式的监听端口，默认 5001
    """
    # 日志输出到 stderr，避免污染 stdio 传输
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("  Cat Litter Monitor MCP Server", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  传输模式: {transport.upper()}", file=sys.stderr)

    if transport == 'stdio':
        print("  协议: MCP over stdio (标准输入输出)", file=sys.stderr)
    elif transport == 'http':
        print(f"  协议: MCP over HTTP", file=sys.stderr)
        print(f"  服务器监听: {host}:{port}", file=sys.stderr)

    print("", file=sys.stderr)
    print("  已注册的工具:", file=sys.stderr)
    print("    1. add_litter_records      - 批量添加猫砂盆使用记录", file=sys.stderr)
    print("    2. get_litter_records       - 获取猫砂盆使用记录", file=sys.stderr)
    print("    3. get_daily_statistics     - 获取每日统计数据", file=sys.stderr)
    print("    4. get_unidentified_photos  - 获取未识别的照片列表", file=sys.stderr)
    print("    5. mark_unidentifiable      - 标记照片为无法识别", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)

    # 根据传输模式运行服务器
    try:
        if transport == 'stdio':
            mcp.run(transport='stdio', show_banner=False)
        elif transport == 'http':
            mcp.run(
                transport='http',
                host=host,
                port=port,
                path='/mcp',
                show_banner=False
            )
        else:
            raise ValueError(f"不支持的传输模式: {transport}")
    except Exception as e:
        logger.error(f"MCP Server 运行时崩溃: {e}")
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='猫厕所监控系统MCP服务器')
    parser.add_argument(
        '--transport',
        choices=['stdio', 'http'],
        default='stdio',
        help='传输模式：stdio (默认) 或 http'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='HTTP模式的监听地址，默认 0.0.0.0'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5001,
        help='HTTP模式的监听端口，默认 5001'
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径'
    )

    args = parser.parse_args()

    try:
        run_server(
            transport=args.transport,
            host=args.host,
            port=args.port
        )
    except Exception as e:
        logger.error(f"MCP Server 启动失败: {e}")
        sys.exit(1)
