"""
数据存储模块

该模块提供SQLite数据库操作，包括事件记录、统计查询等功能。
"""

import sqlite3
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
from pathlib import Path
from contextlib import contextmanager


class Database:
    """
    数据库管理类

    负责SQLite数据库的创建、连接和操作。

    Attributes:
        db_path: 数据库文件路径
        connection: 数据库连接
    """

    def __init__(self, db_path: str = 'data/litter_monitor.db'):
        """
        初始化数据库

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.connection: Optional[sqlite3.Connection] = None

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_database()

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）

        Yields:
            数据库连接
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self) -> None:
        """
        初始化数据库表结构
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 创建事件表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS litter_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER NOT NULL,
                    cat_id INTEGER NOT NULL,
                    cat_name TEXT NOT NULL,
                    enter_time TEXT NOT NULL,
                    exit_time TEXT,
                    duration REAL NOT NULL,
                    start_frame INTEGER NOT NULL,
                    end_frame INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建每日统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cat_id INTEGER NOT NULL,
                    cat_name TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    total_duration REAL NOT NULL,
                    avg_duration REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(cat_id, event_date)
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_cat_id
                ON litter_events(cat_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_enter_time
                ON litter_events(enter_time)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_stats_cat_date
                ON daily_statistics(cat_id, event_date)
            """)

    def insert_event(self, event_dict: Dict) -> int:
        """
        插入事件记录

        Args:
            event_dict: 事件字典，包含以下键：
                - track_id: 追踪ID
                - cat_id: 猫ID
                - cat_name: 猫名称
                - enter_time: 进入时间（ISO格式字符串）
                - exit_time: 离开时间（ISO格式字符串）
                - duration: 持续时间（秒）
                - start_frame: 开始帧号
                - end_frame: 结束帧号

        Returns:
            插入记录的ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO litter_events (
                    track_id, cat_id, cat_name, enter_time, exit_time,
                    duration, start_frame, end_frame
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_dict['track_id'],
                event_dict['cat_id'],
                event_dict['cat_name'],
                event_dict['enter_time'],
                event_dict.get('exit_time'),
                event_dict['duration'],
                event_dict['start_frame'],
                event_dict.get('end_frame')
            ))
            return cursor.lastrowid

    def get_events_by_cat(
        self,
        cat_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        获取特定猫的事件

        Args:
            cat_id: 猫ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            事件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM litter_events WHERE cat_id = ?"
            params = [cat_id]

            if start_date:
                query += " AND date(enter_time) >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND date(enter_time) <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY enter_time DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def get_events_by_date(
        self,
        event_date: date,
        cat_id: Optional[int] = None
    ) -> List[Dict]:
        """
        获取特定日期的事件

        Args:
            event_date: 日期
            cat_id: 猫ID（可选）

        Returns:
            事件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM litter_events WHERE date(enter_time) = ?"
            params = [event_date.isoformat()]

            if cat_id is not None:
                query += " AND cat_id = ?"
                params.append(cat_id)

            query += " ORDER BY enter_time DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def get_recent_events(
        self,
        limit: int = 100,
        cat_id: Optional[int] = None
    ) -> List[Dict]:
        """
        获取最近的事件

        Args:
            limit: 返回数量
            cat_id: 猫ID（可选）

        Returns:
            事件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM litter_events"
            params = []

            if cat_id is not None:
                query += " WHERE cat_id = ?"
                params.append(cat_id)

            query += " ORDER BY enter_time DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def get_daily_statistics(
        self,
        event_date: Optional[date] = None
    ) -> List[Dict]:
        """
        获取每日统计

        Args:
            event_date: 日期，如果为None则返回所有日期的统计

        Returns:
            统计列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if event_date:
                cursor.execute("""
                    SELECT * FROM daily_statistics
                    WHERE event_date = ?
                    ORDER BY cat_id
                """, (event_date.isoformat(),))
            else:
                cursor.execute("""
                    SELECT * FROM daily_statistics
                    ORDER BY event_date DESC, cat_id
                """)

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_cat_daily_statistics(
        self,
        cat_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        获取特定猫的每日统计

        Args:
            cat_id: 猫ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM daily_statistics WHERE cat_id = ?"
            params = [cat_id]

            if start_date:
                query += " AND event_date >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND event_date <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY event_date DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def update_daily_statistics(self, event_date: Optional[date] = None) -> None:
        """
        更新每日统计

        Args:
            event_date: 日期，如果为None则更新今天的统计
        """
        if event_date is None:
            event_date = date.today()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 先删除当天的旧统计
            cursor.execute("""
                DELETE FROM daily_statistics WHERE event_date = ?
            """, (event_date.isoformat(),))

            # 计算新的统计
            cursor.execute("""
                INSERT INTO daily_statistics (
                    cat_id, cat_name, event_date, event_count,
                    total_duration, avg_duration
                )
                SELECT
                    cat_id,
                    cat_name,
                    date(enter_time) as event_date,
                    COUNT(*) as event_count,
                    SUM(duration) as total_duration,
                    AVG(duration) as avg_duration
                FROM litter_events
                WHERE date(enter_time) = ?
                GROUP BY cat_id, cat_name, date(enter_time)
            """, (event_date.isoformat(),))

    def get_summary_statistics(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict:
        """
        获取汇总统计

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            汇总统计字典
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT COUNT(*) as total_events FROM litter_events"
            params = []

            if start_date or end_date:
                query += " WHERE 1=1"

                if start_date:
                    query += " AND date(enter_time) >= ?"
                    params.append(start_date.isoformat())

                if end_date:
                    query += " AND date(enter_time) <= ?"
                    params.append(end_date.isoformat())

            cursor.execute(query, params)
            total_events = cursor.fetchone()['total_events']

            # 按猫统计
            query = """
                SELECT
                    cat_id,
                    cat_name,
                    COUNT(*) as event_count,
                    AVG(duration) as avg_duration
                FROM litter_events
            """
            query_params = []

            if start_date or end_date:
                query += " WHERE 1=1"

                if start_date:
                    query += " AND date(enter_time) >= ?"
                    query_params.append(start_date.isoformat())

                if end_date:
                    query += " AND date(enter_time) <= ?"
                    query_params.append(end_date.isoformat())

            query += " GROUP BY cat_id, cat_name ORDER BY event_count DESC"

            cursor.execute(query, query_params)
            by_cat = [dict(row) for row in cursor.fetchall()]

            return {
                'total_events': total_events,
                'by_cat': by_cat
            }

    def delete_old_events(self, days: int = 30) -> int:
        """
        删除旧事件

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM litter_events
                WHERE date(enter_time) < date('now', '-' || ? || ' days')
            """, (days,))
            return cursor.rowcount

    def get_database_size(self) -> int:
        """
        获取数据库大小（字节）

        Returns:
            数据库大小
        """
        return self.db_path.stat().st_size if self.db_path.exists() else 0

    def vacuum(self) -> None:
        """
        优化数据库
        """
        with self.get_connection() as conn:
            conn.execute("VACUUM")
