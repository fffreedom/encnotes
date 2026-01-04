#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据迁移工具 - 从JSON迁移到SQLite数据库
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def migrate_json_to_sqlite():
    """将JSON数据迁移到SQLite数据库"""
    
    print("=" * 60)
    print("数学笔记 - 数据迁移工具")
    print("从JSON格式迁移到SQLite数据库")
    print("=" * 60)
    print()
    
    # 旧数据路径
    old_data_dir = Path.home() / ".mathnotes"
    old_notes_file = old_data_dir / "notes.json"
    
    # 检查旧数据是否存在
    if not old_notes_file.exists():
        print("✅ 未发现旧的JSON数据文件，无需迁移")
        print(f"   路径: {old_notes_file}")
        return True
        
    print(f"📁 发现旧数据文件: {old_notes_file}")
    
    # 读取旧数据
    try:
        with open(old_notes_file, 'r', encoding='utf-8') as f:
            old_notes = json.load(f)
            
        print(f"📊 读取到 {len(old_notes)} 条笔记")
        print()
        
    except Exception as e:
        print(f"❌ 读取旧数据失败: {e}")
        return False
        
    # 导入新的笔记管理器
    try:
        from note_manager import NoteManager
    except ImportError:
        print("❌ 无法导入NoteManager，请确保在正确的目录下运行")
        return False
        
    # 创建新的数据库
    print("🔧 初始化SQLite数据库...")
    note_manager = NoteManager()
    print(f"✅ 数据库创建成功: {note_manager.db_path}")
    print()
    
    # 迁移数据
    print("🚀 开始迁移数据...")
    migrated_count = 0
    failed_count = 0
    
    for note_id, note_data in old_notes.items():
        try:
            # 解析时间
            created_at = datetime.fromisoformat(note_data.get('created_at', datetime.now().isoformat()))
            updated_at = datetime.fromisoformat(note_data.get('updated_at', datetime.now().isoformat()))
            
            # 转换为Cocoa时间戳
            created_cocoa = note_manager._timestamp_to_cocoa(created_at)
            updated_cocoa = note_manager._timestamp_to_cocoa(updated_at)
            
            # 插入数据
            cursor = note_manager.conn.cursor()
            cursor.execute('''
                INSERT INTO ZNOTE (
                    ZIDENTIFIER, ZTITLE, ZCONTENT,
                    ZCREATIONDATE, ZMODIFICATIONDATE,
                    ZISFAVORITE, ZISDELETED
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                note_id,
                note_data.get('title', '无标题'),
                note_data.get('content', ''),
                created_cocoa,
                updated_cocoa,
                1 if note_data.get('is_favorite', False) else 0,
                1 if note_data.get('is_deleted', False) else 0
            ))
            
            note_manager.conn.commit()
            migrated_count += 1
            print(f"  ✓ 迁移笔记: {note_data.get('title', '无标题')[:30]}")
            
        except Exception as e:
            failed_count += 1
            print(f"  ✗ 迁移失败: {note_data.get('title', '无标题')[:30]} - {e}")
            
    print()
    print("=" * 60)
    print("迁移完成！")
    print(f"  成功: {migrated_count} 条")
    print(f"  失败: {failed_count} 条")
    print("=" * 60)
    print()
    
    # 备份旧数据
    if migrated_count > 0:
        backup_file = old_data_dir / f"notes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            import shutil
            shutil.copy2(old_notes_file, backup_file)
            print(f"📦 旧数据已备份到: {backup_file}")
            print()
            
            # 询问是否删除旧文件
            response = input("是否删除旧的JSON文件？(y/N): ").strip().lower()
            if response == 'y':
                old_notes_file.unlink()
                print("✅ 旧文件已删除")
            else:
                print("ℹ️  旧文件已保留")
                
        except Exception as e:
            print(f"⚠️  备份失败: {e}")
            
    # 关闭数据库
    note_manager.close()
    
    print()
    print("🎉 迁移完成！现在可以启动应用了。")
    
    return True


if __name__ == "__main__":
    try:
        success = migrate_json_to_sqlite()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  迁移已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 迁移过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
