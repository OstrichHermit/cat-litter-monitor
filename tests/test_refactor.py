"""
重构验证测试脚本

测试重构后的系统核心功能
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试导入"""
    print("测试1：导入模块...")
    try:
        from src.config import get_config
        from src.core.photo_capture import PhotoCaptureManager, PhotoCaptureConfig
        from src.storage.database import Database
        from src.storage.photo_manager import PhotoManager
        print("  ✅ 所有模块导入成功")
        return True
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return False

def test_config():
    """测试配置"""
    print("\n测试2：配置管理...")
    try:
        from src.config import get_config
        config = get_config()

        # 测试新配置节
        photo_config = config.get_photo_config()
        assert photo_config is not None
        print(f"  ✅ 拍照配置: min_stay={photo_config.get('min_stay_seconds')}秒")

        return True
    except Exception as e:
        print(f"  ❌ 配置测试失败: {e}")
        return False

def test_database():
    """测试数据库"""
    print("\n测试3：数据库...")
    try:
        from src.storage.database import Database
        import tempfile

        # 使用临时数据库
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name

        db = Database(db_path=temp_db)

        # 测试猫咪表
        cats = db.get_all_cats()
        print(f"  ✅ 默认猫咪数量: {len(cats)}")
        for cat in cats:
            print(f"     - {cat['name']} ({cat.get('color', 'N/A')})")

        # 测试插入记录
        record_id = db.insert_litter_record(
            cat_name='猪猪',
            record_date='2026-03-06',
            record_time='12:00:00',
            photo_path='photo/2026-03-06/Unidentified/test.jpg'
        )
        print(f"  ✅ 插入记录ID: {record_id}")

        # 测试查询记录
        records = db.get_litter_records(limit=10)
        print(f"  ✅ 查询记录数量: {len(records)}")

        # 清理
        import os
        os.unlink(temp_db)

        return True
    except Exception as e:
        print(f"  ❌ 数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_photo_manager():
    """测试照片管理器"""
    print("\n测试4：照片管理器...")
    try:
        from src.storage.photo_manager import PhotoManager
        import tempfile
        import shutil

        # 使用临时目录
        temp_dir = tempfile.mkdtemp()
        manager = PhotoManager(temp_dir)

        # 创建测试照片
        test_photo_dir = Path(temp_dir) / '2026-03-06' / 'Unidentified'
        test_photo_dir.mkdir(parents=True)
        test_photo = test_photo_dir / 'test.jpg'
        test_photo.write_text('test')

        # 测试获取未识别照片
        photos = manager.get_unidentified_photos()
        print(f"  ✅ 未识别照片数量: {len(photos)}")

        # 测试照片统计
        stats = manager.get_photo_stats()
        print(f"  ✅ 照片统计: {stats}")

        # 清理
        shutil.rmtree(temp_dir)

        return True
    except Exception as e:
        print(f"  ❌ 照片管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_photo_capture():
    """测试拍照管理器"""
    print("\n测试5：拍照管理器...")
    try:
        from src.core.photo_capture import PhotoCaptureManager, PhotoCaptureConfig
        import numpy as np
        import tempfile
        import shutil

        # 使用临时目录
        temp_dir = tempfile.mkdtemp()

        config = PhotoCaptureConfig(
            min_stay_seconds=1.0,
            photo_interval=5.0,
            photo_base_dir=temp_dir
        )
        manager = PhotoCaptureManager(config)

        # 模拟一帧
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # 测试拍照（模拟在ROI内停留足够时间）
        fps = 30.0
        for i in range(40):  # 模拟40帧，约1.33秒
            photo_path = manager.update(track_id=1, in_roi=True, current_frame=frame, fps=fps)
            if photo_path:
                print(f"  ✅ 拍照成功: {photo_path}")
                break

        # 清理
        shutil.rmtree(temp_dir)

        return True
    except Exception as e:
        print(f"  ❌ 拍照管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mcp_server():
    """测试MCP服务器"""
    print("\n测试6：MCP服务器...")
    try:
        from src.mcp.server import LitterMonitorMCPServer

        # 只测试类加载，不实际运行服务器
        print("  ✅ MCP服务器类加载成功")
        return True
    except Exception as e:
        print(f"  ❌ MCP服务器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("cat-litter-monitor 重构验证测试")
    print("=" * 50)

    results = []

    # 运行测试
    results.append(("导入模块", test_imports()))
    results.append(("配置管理", test_config()))
    results.append(("数据库", test_database()))
    results.append(("照片管理器", test_photo_manager()))
    results.append(("拍照管理器", test_photo_capture()))
    results.append(("MCP服务器", test_mcp_server()))

    # 汇总结果
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:15s} {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！重构成功！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查")
        return 1

if __name__ == '__main__':
    sys.exit(main())
