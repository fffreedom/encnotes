#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数学公式持久化功能
"""

import sys
from PyQt6.QtWidgets import QApplication
from note_editor import NoteEditor
from note_manager import NoteManager


def test_formula_persistence():
    """测试公式保存和加载"""
    print("=" * 60)
    print("测试数学公式持久化功能")
    print("=" * 60)
    
    # 创建应用
    app = QApplication(sys.argv)
    
    # 创建编辑器和管理器
    editor = NoteEditor()
    manager = NoteManager()
    
    # 测试1: 插入LaTeX公式
    print("\n[测试1] 插入LaTeX公式...")
    latex_code = r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}"
    editor.insert_math_formula(latex_code, 'latex')
    
    # 获取HTML内容
    html_content = editor.toHtml()
    print(f"✓ 插入成功")
    print(f"  HTML长度: {len(html_content)} 字符")
    
    # 输出HTML片段用于调试
    print("\n  HTML片段预览:")
    if 'alt="MATH:' in html_content:
        start = html_content.find('alt="MATH:')
        end = start + 200
        print(f"  {html_content[start:end]}")
    else:
        print("  未找到alt=\"MATH:标记")
    
    # 检查是否包含公式标记
    if 'alt="MATH:latex:' in html_content:
        print("\n✓ HTML包含公式元数据")
    else:
        print("\n✗ HTML缺少公式元数据")
        print("  检查: alt=\"MATH:存在?", 'alt="MATH:' in html_content)
        return False
    
    # 测试2: 保存到数据库
    print("\n[测试2] 保存笔记到数据库...")
    note_id = manager.create_note(
        title="公式测试笔记",
        content=html_content
    )
    print(f"✓ 笔记已保存，ID: {note_id}")
    
    # 测试3: 从数据库加载
    print("\n[测试3] 从数据库加载笔记...")
    note = manager.get_note(note_id)
    if note:
        print(f"✓ 笔记已加载")
        print(f"  标题: {note['title']}")
        print(f"  内容长度: {len(note['content'])} 字符")
        
        # 检查内容是否包含公式标记
        if 'alt="MATH:latex:' in note['content']:
            print("✓ 加载的内容包含公式元数据")
        else:
            print("✗ 加载的内容缺少公式元数据")
            return False
    else:
        print("✗ 加载笔记失败")
        return False
    
    # 测试4: 重新渲染公式
    print("\n[测试4] 重新渲染公式...")
    editor2 = NoteEditor()
    editor2.setHtml(note['content'])
    
    # 获取重新渲染后的HTML
    rerendered_html = editor2.toHtml()
    print(f"✓ 公式已重新渲染")
    print(f"  重新渲染后HTML长度: {len(rerendered_html)} 字符")
    
    # 检查是否仍然包含公式标记
    if 'alt="MATH:latex:' in rerendered_html:
        print("✓ 重新渲染后仍保留公式元数据")
    else:
        print("✗ 重新渲染后丢失公式元数据")
        return False
    
    # 测试5: 测试MathML公式
    print("\n[测试5] 测试MathML公式...")
    editor3 = NoteEditor()
    mathml_code = "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"
    editor3.insert_math_formula(mathml_code, 'mathml')
    
    mathml_html = editor3.toHtml()
    if 'alt="MATH:mathml:' in mathml_html:
        print("✓ MathML公式元数据正确")
    else:
        print("✗ MathML公式元数据错误")
        return False
    
    # 清理测试数据
    print("\n[清理] 删除测试笔记...")
    manager.permanently_delete_note(note_id)
    print("✓ 测试数据已清理")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    
    return True


if __name__ == '__main__':
    try:
        success = test_formula_persistence()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
