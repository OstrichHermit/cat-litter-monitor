"""
数据存储模块

该模块提供SQLite数据库操作，包括记录管理、统计查询等功能。
新架构支持时间点记录和照片路径。
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

    新表结构：
    - cats: 猫咪信息表
    - litter_records: 猫砂盆使用记录表（时间点记录）
    - daily_statistics: 每日统计表

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

            # 创建猫咪表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    color TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建猫砂盆使用记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS litter_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cat_id INTEGER NOT NULL,
                    cat_name TEXT NOT NULL,
                    record_date TEXT NOT NULL,
                    record_time TEXT NOT NULL,
                    record_datetime TEXT NOT NULL,
                    photo_path TEXT NOT NULL,
                    roi_id INTEGER DEFAULT 1,
                    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cat_id) REFERENCES cats(id)
                )
            """)

            # 创建每日统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cat_id INTEGER NOT NULL,
                    cat_name TEXT NOT NULL,
                    record_date TEXT NOT NULL,
                    record_count INTEGER NOT NULL,
                    first_time TEXT NOT NULL,
                    last_time TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(cat_id, record_date),
                    FOREIGN KEY (cat_id) REFERENCES cats(id)
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_cat_id
                ON litter_records(cat_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_date
                ON litter_records(record_date)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_datetime
                ON litter_records(record_datetime)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_stats_cat_date
                ON daily_statistics(cat_id, record_date)
            """)

            # 初始化默认猫咪（如果不存在）
            self._init_default_cats(cursor)

    def _init_default_cats(self, cursor) -> None:
        """
        初始化默认猫咪数据

        Args:
            cursor: 数据库游标
        """
        default_cats = [
            ('猪猪', '棕色虎斑'),
            ('汪三', '黑色')
        ]

        for cat_name, cat_color in default_cats:
            try:
                cursor.execute(
                    "INSERT INTO cats (name, color) VALUES (?, ?)",
                    (cat_name, cat_color)
                )
            except sqlite3.IntegrityError:
                # 猫咪已存在，跳过
                pass

    def add_cat(self, name: str, color: Optional[str] = None) -> int:
        """
        添加猫咪

        Args:
            name: 猫咪名称
            color: 猫咪颜色（可选）

        Returns:
            插入的猫咪ID

        Raises:
            sqlite3.IntegrityError: 猫咪名称已存在
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO cats (name, color) VALUES (?, ?)",
                (name, color)
            )
            return cursor.lastrowid

    def get_cat_by_name(self, name: str) -> Optional[Dict]:
        """
        根据名称获取猫咪信息

        Args:
            name: 猫咪名称

        Returns:
            猫咪信息字典，如果不存在返回None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cats WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_cats(self) -> List[Dict]:
        """
        获取所有猫咪

        Returns:
            猫咪列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cats ORDER BY id")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def insert_litter_record(
        self,
        cat_name: str,
        record_date: str,
        record_time: str,
        photo_path: str,
        roi_id: int = 1
    ) -> int:
        """
        插入猫砂盆使用记录

        Args:
            cat_name: 猫咪名称
            record_date: 记录日期（YYYY-MM-DD）
            record_time: 记录时间（HH:MM:SS）
            photo_path: 照片路径
            roi_id: ROI区域ID（默认为1）

        Returns:
            插入记录的ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 获取猫咪信息
            cat = self.get_cat_by_name(cat_name)
            if not cat:
                # 如果猫咪不存在，自动创建
                cat_id = self.add_cat(cat_name, None)
            else:
                cat_id = cat['id']

            # 组合日期时间
            record_datetime = f"{record_date} {record_time}"

            # 插入记录
            cursor.execute("""
                INSERT INTO litter_records (
                    cat_id, cat_name, record_date, record_time,
                    record_datetime, photo_path, roi_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                cat_id, cat_name, record_date, record_time,
                record_datetime, photo_path, roi_id
            ))

            return cursor.lastrowid

    def insert_litter_records_batch(
        self,
        records: List[Dict[str, str]]
    ) -> List[int]:
        """
        批量插入猫砂盆使用记录

        Args:
            records: 记录列表，每条记录包含：
                - cat_name: 猫咪名称
                - date: 日期（YYYY-MM-DD）
                - time: 时间（HH:MM:SS）
                - photo_path: 照片路径
                - roi_id: ROI区域ID（可选，默认为1）

        Returns:
            插入记录的ID列表
        """
        record_ids = []
        for record in records:
            record_id = self.insert_litter_record(
                cat_name=record['cat_name'],
                record_date=record['date'],
                record_time=record['time'],
                photo_path=record['photo_path'],
                roi_id=record.get('roi_id', 1)
            )
            record_ids.append(record_id)
        return record_ids

    def get_litter_records(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        cat_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        获取猫砂盆使用记录

        Args:
            start_date: 开始日期
            end_date: 结束日期
            cat_id: 猫咪ID（可选）
            limit: 返回数量限制

        Returns:
            记录列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM litter_records WHERE 1=1"
            params = []

            if start_date:
                query += " AND record_date >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND record_date <= ?"
                params.append(end_date.isoformat())

            if cat_id is not None:
                query += " AND cat_id = ?"
                params.append(cat_id)

            query += " ORDER BY record_datetime DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def get_today_records(self, cat_id: Optional[int] = None) -> List[Dict]:
        """
        获取今天的记录

        Args:
            cat_id: 猫咪ID（可选）

        Returns:
            记录列表
        """
        today = date.today()
        return self.get_litter_records(
            start_date=today,
            end_date=today,
            cat_id=cat_id,
            limit=1000
        )

    def get_yesterday_records(self, cat_id: Optional[int] = None) -> List[Dict]:
        """
        获取昨天的记录

        Args:
            cat_id: 猫咪ID（可选）

        Returns:
            记录列表
        """
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        return self.get_litter_records(
            start_date=yesterday,
            end_date=yesterday,
            cat_id=cat_id,
            limit=1000
        )

    def get_daily_statistics(
        self,
        record_date: Optional[date] = None
    ) -> List[Dict]:
        """
        获取每日统计

        Args:
            record_date: 日期，如果为None则返回所有日期的统计

        Returns:
            统计列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if record_date:
                cursor.execute("""
                    SELECT * FROM daily_statistics
                    WHERE record_date = ?
                    ORDER BY cat_id
                """, (record_date.isoformat(),))
            else:
                cursor.execute("""
                    SELECT * FROM daily_statistics
                    ORDER BY record_date DESC, cat_id
                """)

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_daily_statistics(self, record_date: Optional[date] = None) -> None:
        """
        更新每日统计

        Args:
            record_date: 日期，如果为None则更新今天的统计
        """
        if record_date is None:
            record_date = date.today()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 计算新的统计并使用 REPLACE 策略（会先删除冲突的行再插入）
            cursor.execute("""
                INSERT OR REPLACE INTO daily_statistics (
                    cat_id, cat_name, record_date, record_count,
                    first_time, last_time, created_at
                )
                SELECT
                    lr.cat_id,
                    lr.cat_name,
                    lr.record_date,
                    COUNT(*) as record_count,
                    MIN(lr.record_time) as first_time,
                    MAX(lr.record_time) as last_time,
                    COALESCE(
                        (SELECT created_at FROM daily_statistics
                         WHERE cat_id = lr.cat_id AND record_date = lr.record_date),
                        CURRENT_TIMESTAMP
                    ) as created_at
                FROM litter_records lr
                WHERE lr.record_date = ?
                GROUP BY lr.cat_id, lr.cat_name, lr.record_date
            """, (record_date.isoformat(),))

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

            query = "SELECT COUNT(*) as total_records FROM litter_records"
            params = []

            if start_date or end_date:
                query += " WHERE 1=1"

                if start_date:
                    query += " AND record_date >= ?"
                    params.append(start_date.isoformat())

                if end_date:
                    query += " AND record_date <= ?"
                    params.append(end_date.isoformat())

            cursor.execute(query, params)
            total_records = cursor.fetchone()['total_records']

            # 按猫统计
            query = """
                SELECT
                    cat_id,
                    cat_name,
                    COUNT(*) as record_count
                FROM litter_records
            """
            query_params = []

            if start_date or end_date:
                query += " WHERE 1=1"

                if start_date:
                    query += " AND record_date >= ?"
                    query_params.append(start_date.isoformat())

                if end_date:
                    query += " AND record_date <= ?"
                    query_params.append(end_date.isoformat())

            query += " GROUP BY cat_id, cat_name ORDER BY record_count DESC"

            cursor.execute(query, query_params)
            by_cat = [dict(row) for row in cursor.fetchall()]

            return {
                'total_records': total_records,
                'by_cat': by_cat
            }

    def delete_old_records(self, days: int = 30) -> int:
        """
        删除旧记录

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM litter_records
                WHERE record_date < date('now', '-' || ? || ' days')
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

    def delete_record_by_id(self, record_id: int) -> bool:
        """
        根据ID删除单条记录

        Args:
            record_id: 记录ID

        Returns:
            是否删除成功
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM litter_records WHERE id = ?
            """, (record_id,))
            return cursor.rowcount > 0

    def update_record_cat_name(self, record_id: int, new_cat_name: str) -> bool:
        """
        更新记录的猫咪名称

        Args:
            record_id: 记录ID
            new_cat_name: 新的猫咪名称

        Returns:
            是否更新成功
        """
        from datetime import datetime

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 先获取记录的日期（用于更新统计）
            cursor.execute("""
                SELECT record_date FROM litter_records WHERE id = ?
            """, (record_id,))
            result = cursor.fetchone()
            record_date = result['record_date'] if result else None

            # 更新猫咪名称
            cursor.execute("""
                UPDATE litter_records
                SET cat_name = ?
                WHERE id = ?
            """, (new_cat_name, record_id))
            conn.commit()

            # 更新每日统计
            if record_date:
                # record_date 是字符串，需要转换为 date 对象
                if isinstance(record_date, str):
                    record_date_obj = datetime.fromisoformat(record_date).date()
                else:
                    record_date_obj = record_date
                self.update_daily_statistics(record_date_obj)

            return cursor.rowcount > 0
