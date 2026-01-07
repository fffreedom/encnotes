#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临时文件管理测试脚本
"""

import time
import tempfile
from pathlib import Path


def test_temp_file_cleanup():
    """测试临时文件清理功能"""
    
    print("=" * 60)
    print("临时文件管理测试")
    print("=" * 60)
    
    # 1. 检查临时目录
    temp_dir = Path(tempfile.gettempdir())
    print(f"\n📁 临时目录: {temp_dir}")
    
    # 2. 查找现有的encnotes临时文件
    pattern = "encnotes_temp_*"
    existing_files = list(temp_dir.glob(pattern))
    print(f"\n🔍 现有临时文件数量: {len(existing_files)}")
    
    if existing_files:
        print("\n现有文件列表:")
        for file_path in existing_files:
            file_stat = file_path.stat()
            print(f"  - {file_path.name}")
            print(f"    大小: {file_stat.st_size} 字节")
    
    # 3. 模拟清理过程
    print("\n🧹 模拟清理过程...")
    cleaned_count = 0
    
    for file_path in existing_files:
        try:
            print(f"  ✓ 清理: {file_path.name}")
            # 注意：这里只是模拟，不实际删除
            # file_path.unlink()
            cleaned_count += 1
        except Exception as e:
            print(f"  ✗ 错误: {file_path.name} - {e}")
    
    print(f"\n📊 清理统计:")
    print(f"  - 总文件数: {len(existing_files)}")
    print(f"  - 需要清理: {cleaned_count}")
    
    # 4. 测试创建临时文件
    print("\n🔧 测试创建临时文件...")
    test_attachment_id = "test-uuid-12345"
    test_filename = "test_document.pdf"
    test_temp_name = f"encnotes_temp_{test_attachment_id}_{test_filename}"
    test_temp_path = temp_dir / test_temp_name
    
    try:
        # 创建测试文件
        test_temp_path.write_text("这是一个测试文件")
        print(f"  ✓ 创建成功: {test_temp_name}")
        print(f"  路径: {test_temp_path}")
        
        # 检查文件
        if test_temp_path.exists():
            print(f"  ✓ 文件存在")
            print(f"  大小: {test_temp_path.stat().st_size} 字节")
        
        # 清理测试文件
        test_temp_path.unlink()
        print(f"  ✓ 清理成功")
        
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


def manual_cleanup():
    """手动清理所有encnotes临时文件"""
    
    print("\n⚠️  手动清理模式")
    print("=" * 60)
    
    temp_dir = Path(tempfile.gettempdir())
    pattern = "encnotes_temp_*"
    files = list(temp_dir.glob(pattern))
    
    if not files:
        print("✓ 没有需要清理的文件")
        return
    
    print(f"找到 {len(files)} 个临时文件:")
    for file_path in files:
        print(f"  - {file_path.name}")
    
    response = input("\n确认清理这些文件? (y/n): ")
    
    if response.lower() == 'y':
        cleaned_count = 0
        for file_path in files:
            try:
                file_path.unlink()
                print(f"  ✓ 已清理: {file_path.name}")
                cleaned_count += 1
            except Exception as e:
                print(f"  ✗ 清理失败: {file_path.name} - {e}")
        
        print(f"\n✓ 共清理 {cleaned_count} 个文件")
    else:
        print("\n✗ 已取消清理")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        manual_cleanup()
    else:
        test_temp_file_cleanup()
        
        print("\n💡 提示:")
        print("  - 运行 'python test_temp_cleanup.py --cleanup' 可手动清理所有临时文件")
        print("  - 临时文件会在应用启动时自动清理（清理所有临时文件）")
        print("  - 临时文件会在应用正常退出时自动清理")
