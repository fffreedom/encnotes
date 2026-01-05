#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试标签功能
"""

from note_manager import NoteManager

def test_tags():
    """测试标签功能"""
    print("开始测试标签功能...")
    
    # 创建管理器
    manager = NoteManager()
    
    # 1. 创建标签
    print("\n1. 创建标签...")
    tag1_id = manager.create_tag("Python")
    tag2_id = manager.create_tag("数学")
    tag3_id = manager.create_tag("算法")
    print(f"   创建了3个标签: Python, 数学, 算法")
    
    # 2. 获取所有标签
    print("\n2. 获取所有标签...")
    tags = manager.get_all_tags()
    print(f"   共有 {len(tags)} 个标签:")
    for tag in tags:
        print(f"   - {tag['name']} (ID: {tag['id'][:8]}...)")
    
    # 3. 创建笔记
    print("\n3. 创建测试笔记...")
    note1_id = manager.create_note("Python基础", "学习Python编程")
    note2_id = manager.create_note("线性代数", "矩阵运算")
    note3_id = manager.create_note("排序算法", "快速排序和归并排序")
    print(f"   创建了3条笔记")
    
    # 4. 为笔记添加标签
    print("\n4. 为笔记添加标签...")
    manager.add_tag_to_note(note1_id, tag1_id)  # Python基础 -> Python
    manager.add_tag_to_note(note2_id, tag2_id)  # 线性代数 -> 数学
    manager.add_tag_to_note(note3_id, tag1_id)  # 排序算法 -> Python
    manager.add_tag_to_note(note3_id, tag3_id)  # 排序算法 -> 算法
    print(f"   已为笔记添加标签")
    
    # 5. 获取笔记的标签
    print("\n5. 获取笔记的标签...")
    note3_tags = manager.get_note_tags(note3_id)
    print(f"   '排序算法' 笔记的标签:")
    for tag in note3_tags:
        print(f"   - {tag['name']}")
    
    # 6. 按标签获取笔记
    print("\n6. 按标签获取笔记...")
    python_notes = manager.get_notes_by_tag(tag1_id)
    print(f"   'Python' 标签下的笔记:")
    for note in python_notes:
        print(f"   - {note['title']}")
    
    # 7. 获取标签的笔记数量
    print("\n7. 获取标签的笔记数量...")
    for tag in tags:
        count = manager.get_tag_count(tag['id'])
        print(f"   {tag['name']}: {count} 条笔记")
    
    # 8. 更新标签
    print("\n8. 更新标签...")
    manager.update_tag(tag1_id, "Python编程")
    updated_tag = manager.get_tag(tag1_id)
    print(f"   标签已更新: {updated_tag['name']}")
    
    # 9. 从笔记移除标签
    print("\n9. 从笔记移除标签...")
    manager.remove_tag_from_note(note3_id, tag1_id)
    note3_tags = manager.get_note_tags(note3_id)
    print(f"   '排序算法' 笔记的标签:")
    for tag in note3_tags:
        print(f"   - {tag['name']}")
    
    # 10. 删除标签
    print("\n10. 删除标签...")
    manager.delete_tag(tag3_id)
    tags = manager.get_all_tags()
    print(f"   删除后剩余 {len(tags)} 个标签")
    
    # 清理
    print("\n清理测试数据...")
    manager.permanently_delete_note(note1_id)
    manager.permanently_delete_note(note2_id)
    manager.permanently_delete_note(note3_id)
    manager.delete_tag(tag1_id)
    manager.delete_tag(tag2_id)
    
    manager.close()
    print("\n✅ 标签功能测试完成！")

if __name__ == "__main__":
    test_tags()
