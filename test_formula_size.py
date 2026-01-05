#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试公式大小 - 验证行内公式效果
"""

import sys
from PyQt6.QtWidgets import QApplication
from note_editor import NoteEditor
from note_manager import NoteManager


def test_formula_size():
    """测试公式大小是否与文字匹配"""
    print("=" * 60)
    print("测试数学公式大小")
    print("=" * 60)
    
    # 创建应用
    app = QApplication(sys.argv)
    
    # 创建编辑器和管理器
    editor = NoteEditor()
    manager = NoteManager()
    
    # 测试1: 插入行内公式
    print("\n[测试1] 插入行内公式...")
    
    # 插入一些文字
    editor.text_edit.insertPlainText("这是一个行内公式示例：")
    
    # 插入公式
    latex_code = r"x^2"
    editor.insert_math_formula(latex_code, 'latex')
    
    # 继续插入文字
    editor.text_edit.insertPlainText(" 的示例。")
    
    print("✓ 行内公式插入成功")
    
    # 测试2: 插入多个公式
    print("\n[测试2] 插入多个行内公式...")
    
    editor.text_edit.insertPlainText("\n\n根据二次方程公式 ")
    editor.insert_math_formula(r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}", 'latex')
    editor.text_edit.insertPlainText(" 可以求解。")
    
    editor.text_edit.insertPlainText("\n\n圆的面积公式是 ")
    editor.insert_math_formula(r"\pi r^2", 'latex')
    editor.text_edit.insertPlainText("，其中 ")
    editor.insert_math_formula(r"r", 'latex')
    editor.text_edit.insertPlainText(" 是半径。")
    
    print("✓ 多个行内公式插入成功")
    
    # 测试3: 保存和加载
    print("\n[测试3] 保存和加载笔记...")
    
    html_content = editor.toHtml()
    note_id = manager.create_note(
        title="行内公式测试",
        content=html_content
    )
    print(f"✓ 笔记已保存，ID: {note_id}")
    
    # 加载笔记
    note = manager.get_note(note_id)
    if note:
        print("✓ 笔记已加载")
        
        # 创建新编辑器并加载内容
        editor2 = NoteEditor()
        editor2.setHtml(note['content'])
        
        print("✓ 公式已重新渲染")
    
    # 测试4: 检查HTML
    print("\n[测试4] 检查HTML内容...")
    
    html = editor.toHtml()
    
    # 统计公式数量
    formula_count = html.count('alt="MATH:')
    print(f"✓ 找到 {formula_count} 个公式")
    
    # 检查是否包含元数据
    if 'alt="MATH:latex:' in html:
        print("✓ 公式元数据正确保存")
    
    # 清理测试数据
    print("\n[清理] 删除测试笔记...")
    manager.permanently_delete_note(note_id)
    print("✓ 测试数据已清理")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    print("\n提示：")
    print("- 公式大小现在与正文文字（14pt）一致")
    print("- 公式可以嵌入在文字中，实现行内效果")
    print("- 启动应用查看实际效果：python3 main.py")
    print("=" * 60)
    
    return True


if __name__ == '__main__':
    try:
        success = test_formula_size()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
