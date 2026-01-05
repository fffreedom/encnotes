#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试QTextEdit对HTML的处理
"""

import sys
from PyQt6.QtWidgets import QApplication, QTextEdit


def test_html_preservation():
    """测试QTextEdit保留哪些HTML元素"""
    app = QApplication(sys.argv)
    editor = QTextEdit()
    
    # 测试各种HTML元素
    test_cases = [
        ("HTML注释", "<!--test comment--><p>Text</p>"),
        ("data属性", '<p data-custom="value">Text</p>'),
        ("class属性", '<p class="custom-class">Text</p>'),
        ("style属性", '<p style="color: red;">Text</p>'),
        ("title属性", '<p title="tooltip">Text</p>'),
        ("alt属性", '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" alt="test" />'),
    ]
    
    print("=" * 60)
    print("测试QTextEdit HTML保留情况")
    print("=" * 60)
    
    for name, html_input in test_cases:
        editor.clear()
        editor.setHtml(html_input)
        html_output = editor.toHtml()
        
        print(f"\n[{name}]")
        print(f"  输入: {html_input[:80]}")
        
        # 检查关键部分是否保留
        if "comment" in name:
            preserved = "<!--" in html_output
        elif "data-" in html_input:
            preserved = "data-custom" in html_output
        elif "class=" in html_input:
            preserved = "custom-class" in html_output
        elif "style=" in html_input:
            preserved = "color" in html_output
        elif "title=" in html_input:
            preserved = "title=" in html_output
        elif "alt=" in html_input:
            preserved = "alt=" in html_output
        else:
            preserved = False
        
        status = "✓ 保留" if preserved else "✗ 丢失"
        print(f"  结果: {status}")
        
        if not preserved:
            # 显示实际输出的片段
            if len(html_output) > 200:
                print(f"  输出片段: ...{html_output[-200:]}")
            else:
                print(f"  输出: {html_output}")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    test_html_preservation()
