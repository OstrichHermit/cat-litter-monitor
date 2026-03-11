"""
照片文件管理模块

该模块负责管理照片文件的存储、移动和组织。
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
import logging


class PhotoManager:
    """
    照片文件管理器类

    负责照片文件的存储、移动和组织。

    目录结构：
    photo/
      ├── YYYY-MM-DD/
      │   ├── Unidentified/
      │   │   └── YYYYMMDD_HHMMSS.jpg
      │   └── Identified/
      │       └── 猫名/
      │           └── YYYYMMDD_HHMMSS.jpg

    Attributes:
        photo_base_dir: 照片基础目录
        logger: 日志对象
    """

    def __init__(self, photo_base_dir: str = "photo", logger=None):
        """
        初始化照片管理器

        Args:
            photo_base_dir: 照片基础目录
            logger: 日志对象
        """
        self.photo_base_dir = Path(photo_base_dir)
        self.logger = logger or logging.getLogger(__name__)

        # 确保基础目录存在
        self.photo_base_dir.mkdir(parents=True, exist_ok=True)

    def get_unidentified_photos(self) -> List[Dict[str, str]]:
        """
        获取所有未识别的照片

        Returns:
            未识别照片列表，每项包含日期、路径等信息
        """
        unidentified_photos = []

        # 遍历所有日期目录
        for date_dir in self.photo_base_dir.iterdir():
            if not date_dir.is_dir():
                continue

            # 检查是否有 Unidentified 目录
            unidentified_dir = date_dir / "Unidentified"
            if not unidentified_dir.exists():
                continue

            # 获取该目录下的所有照片
            for photo_file in unidentified_dir.glob("*.jpg"):
                unidentified_photos.append({
                    'date': date_dir.name,
                    'path': str(photo_file),
                    'filename': photo_file.name
                })

        # 按日期排序
        unidentified_photos.sort(key=lambda x: x['date'], reverse=True)

        return unidentified_photos

    def move_photo(
        self,
        photo_path: str,
        cat_name: str,
        date_str: str
    ) -> Optional[str]:
        """
        移动照片从 Unidentified 到 Identified

        Args:
            photo_path: 原照片路径
            cat_name: 猫咪名称
            date_str: 日期字符串 (YYYY-MM-DD)

        Returns:
            新照片路径，如果失败返回None
        """
        try:
            # 源文件
            source_path = Path(photo_path)
            if not source_path.exists():
                self.logger.warning(f"照片文件不存在: {photo_path}")
                return None

            # 目标目录：photo/YYYY-MM-DD/Identified/猫名/
            target_dir = self.photo_base_dir / date_str / "Identified" / cat_name
            target_dir.mkdir(parents=True, exist_ok=True)

            # 目标文件路径
            target_path = target_dir / source_path.name

            # 移动文件
            shutil.move(str(source_path), str(target_path))

            self.logger.info(f"照片移动成功: {source_path} -> {target_path}")

            # 返回相对路径，使用正斜杠（Unix风格）而不是反斜杠（Windows风格）
            # Web界面期望的格式：photo/YYYY-MM-DD/Identified/猫名/文件名.jpg
            relative_path = target_path.relative_to(self.photo_base_dir.parent)
            return relative_path.as_posix()

        except Exception as e:
            self.logger.error(f"移动照片失败: {e}")
            return None

    def copy_photo(
        self,
        photo_path: str,
        cat_name: str,
        date_str: str,
        suffix: str = ""
    ) -> Optional[str]:
        """
        复制照片从 Unidentified 到 Identified（用于多只猫共享一张照片的情况）

        Args:
            photo_path: 原照片路径
            cat_name: 猫咪名称
            date_str: 日期字符串 (YYYY-MM-DD)
            suffix: 文件名后缀，用于区分副本（例如：_copy1, _copy2）

        Returns:
            新照片路径，如果失败返回None
        """
        try:
            # 源文件
            source_path = Path(photo_path)
            if not source_path.exists():
                self.logger.warning(f"照片文件不存在: {photo_path}")
                return None

            # 目标目录：photo/YYYY-MM-DD/Identified/猫名/
            target_dir = self.photo_base_dir / date_str / "Identified" / cat_name
            target_dir.mkdir(parents=True, exist_ok=True)

            # 构建新的文件名（添加后缀）
            stem = source_path.stem
            extension = source_path.suffix
            new_filename = f"{stem}{suffix}{extension}"
            target_path = target_dir / new_filename

            # 复制文件
            shutil.copy2(str(source_path), str(target_path))

            self.logger.info(f"照片复制成功: {source_path} -> {target_path}")

            # 返回相对路径，使用正斜杠（Unix风格）而不是反斜杠（Windows风格）
            # Web界面期望的格式：photo/YYYY-MM-DD/Identified/猫名/文件名.jpg
            relative_path = target_path.relative_to(self.photo_base_dir.parent)
            return relative_path.as_posix()

        except Exception as e:
            self.logger.error(f"复制照片失败: {e}")
            return None

    def copy_photo_from_source(
        self,
        source_abs_path: str,
        cat_name: str,
        date_str: str,
        suffix: str = ""
    ) -> Optional[str]:
        """
        从源文件复制照片到目标猫咪目录（用于多只猫共享一张照片的情况）

        Args:
            source_abs_path: 源照片的绝对路径
            cat_name: 猫咪名称
            date_str: 日期字符串 (YYYY-MM-DD)
            suffix: 文件名后缀，用于区分副本（例如：_copy1, _copy2）

        Returns:
            新照片路径，如果失败返回None
        """
        try:
            # 源文件（绝对路径）
            source_path = Path(source_abs_path)
            if not source_path.exists():
                self.logger.warning(f"源照片文件不存在: {source_abs_path}")
                return None

            # 目标目录：photo/YYYY-MM-DD/Identified/猫名/
            target_dir = self.photo_base_dir / date_str / "Identified" / cat_name
            target_dir.mkdir(parents=True, exist_ok=True)

            # 构建新的文件名（添加后缀）
            stem = source_path.stem
            extension = source_path.suffix
            new_filename = f"{stem}{suffix}{extension}"
            target_path = target_dir / new_filename

            # 复制文件
            shutil.copy2(str(source_path), str(target_path))

            self.logger.info(f"照片复制成功: {source_path} -> {target_path}")

            # 返回相对路径，使用正斜杠（Unix风格）而不是反斜杠（Windows风格）
            # Web界面期望的格式：photo/YYYY-MM-DD/Identified/猫名/文件名.jpg
            relative_path = target_path.relative_to(self.photo_base_dir.parent)
            return relative_path.as_posix()

        except Exception as e:
            self.logger.error(f"从源文件复制照片失败: {e}")
            return None

    def move_photos_batch(
        self,
        photo_records: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        批量移动照片

        Args:
            photo_records: 照片记录列表，每项包含：
                - photo_path: 照片路径
                - cat_name: 猫咪名称
                - date: 日期

        Returns:
            移动结果列表
        """
        results = []

        for record in photo_records:
            new_path = self.move_photo(
                photo_path=record['photo_path'],
                cat_name=record['cat_name'],
                date_str=record['date']
            )

            results.append({
                'old_path': record['photo_path'],
                'new_path': new_path,
                'success': new_path is not None
            })

        return results

    def get_photo_url(self, photo_path: str) -> str:
        """
        获取照片的URL路径（用于Web访问）

        Args:
            photo_path: 照片文件路径

        Returns:
            照片URL路径
        """
        # 将文件路径转换为URL路径
        # 例如：photo/2026-03-06/Identified/猪猪/20260306_123456.jpg
        #      -> /static/photo/2026-03-06/Identified/猪猪/20260306_123456.jpg

        try:
            path = Path(photo_path)

            # 获取相对路径
            relative_path = path.relative_to(self.photo_base_dir.parent)

            # 转换为URL
            url_path = f"/static/{relative_path.as_posix()}"

            return url_path

        except Exception as e:
            self.logger.error(f"生成照片URL失败: {e}")
            return ""

    def delete_photo(self, photo_path: str) -> bool:
        """
        删除照片

        Args:
            photo_path: 照片路径

        Returns:
            是否删除成功
        """
        try:
            path = Path(photo_path)
            if path.exists():
                path.unlink()
                self.logger.info(f"照片删除成功: {photo_path}")
                return True
            else:
                self.logger.warning(f"照片文件不存在: {photo_path}")
                return False

        except Exception as e:
            self.logger.error(f"删除照片失败: {e}")
            return False

    def get_photo_stats(self) -> Dict[str, int]:
        """
        获取照片统计信息

        Returns:
            统计信息字典
        """
        stats = {
            'total_photos': 0,
            'unidentified_photos': 0,
            'identified_photos': 0,
            'total_size_mb': 0
        }

        try:
            # 统计未识别照片
            for date_dir in self.photo_base_dir.iterdir():
                if not date_dir.is_dir():
                    continue

                unidentified_dir = date_dir / "Unidentified"
                if unidentified_dir.exists():
                    unidentified_photos = list(unidentified_dir.glob("*.jpg"))
                    stats['unidentified_photos'] += len(unidentified_photos)
                    stats['total_photos'] += len(unidentified_photos)

                    # 计算大小
                    for photo in unidentified_photos:
                        stats['total_size_mb'] += photo.stat().st_size / (1024 * 1024)

                # 统计已识别照片
                identified_dir = date_dir / "Identified"
                if identified_dir.exists():
                    for cat_dir in identified_dir.iterdir():
                        if cat_dir.is_dir():
                            identified_photos = list(cat_dir.glob("*.jpg"))
                            stats['identified_photos'] += len(identified_photos)
                            stats['total_photos'] += len(identified_photos)

                            # 计算大小
                            for photo in identified_photos:
                                stats['total_size_mb'] += photo.stat().st_size / (1024 * 1024)

            stats['total_size_mb'] = round(stats['total_size_mb'], 2)

        except Exception as e:
            self.logger.error(f"获取照片统计失败: {e}")

        return stats

    def cleanup_old_photos(self, days: int = 30) -> int:
        """
        清理旧照片

        Args:
            days: 保留天数

        Returns:
            删除的照片数量
        """
        from datetime import datetime, timedelta

        deleted_count = 0
        cutoff_date = datetime.now() - timedelta(days=days)

        try:
            for date_dir in self.photo_base_dir.iterdir():
                if not date_dir.is_dir():
                    continue

                # 解析日期
                try:
                    dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                except ValueError:
                    continue

                # 如果目录日期超过保留天数，删除整个目录
                if dir_date < cutoff_date:
                    shutil.rmtree(date_dir)
                    deleted_count += 1
                    self.logger.info(f"删除旧照片目录: {date_dir}")

        except Exception as e:
            self.logger.error(f"清理旧照片失败: {e}")

        return deleted_count
