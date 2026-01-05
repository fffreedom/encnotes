#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能测试脚本 - 测试编辑器新功能
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from note_editor import NoteEditor


class TestWindow(QMainWindow):
    """测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("编辑器功能测试")
        self.setGeometry(100, 100, 1000, 700)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # 创建编辑器
        self.editor = NoteEditor()
        layout.addWidget(self.editor)
        
        # 添加测试内容
        self.add_test_content()
    
    def add_test_content(self):
        """添加测试内容"""
        test_html = """
        <h1>编辑器功能测试</h1>
        
        <h2>测试项目</h2>
        
        <h3>1. 格式工具栏</h3>
        <p>✅ 格式菜单（标题、大标题、小标题、正文）</p>
        <p>✅ 文本样式（<b>粗体</b>、<i>斜体</i>、<u>下划线</u>、<s>删除线</s>）</p>
        
        <h3>2. 列表功能</h3>
        <ul>
            <li>项目符号列表项1</li>
            <li>项目符号列表项2</li>
        </ul>
        <ol>
            <li>编号列表项1</li>
            <li>编号列表项2</li>
        </ol>
        
        <h3>3. 截图粘贴</h3>
        <p>📸 请使用 Cmd+Shift+4 截图，然后按 Cmd+V 粘贴到这里测试</p>
        
        <h3>4. 附件功能</h3>
        <p>📎 点击工具栏的附件按钮添加文件</p>
        
        <h3>5. 超链接</h3>
        <p>🔗 选中文字后按 Ctrl+K 添加链接，或点击工具栏按钮</p>
        <p>示例：<a href="https://www.python.org">Python官网</a></p>
        
        <h3>6. 表格</h3>
        <p>⊞ 点击工具栏的表格按钮插入表格</p>
        
        <table border="1" cellpadding="4">
            <tr>
                <td>单元格1</td>
                <td>单元格2</td>
                <td>单元格3</td>
            </tr>
            <tr>
                <td>数据1</td>
                <td>数据2</td>
                <td>数据3</td>
            </tr>
        </table>
        
        <h3>7. 数学公式</h3>
        <p>∑ 点击工具栏的公式按钮插入LaTeX公式</p>
        
        <h2>快捷键测试</h2>
        <ul>
            <li>Ctrl+B - 粗体</li>
            <li>Ctrl+I - 斜体</li>
            <li>Ctrl+U - 下划线</li>
            <li>Ctrl+K - 插入链接</li>
            <li>Cmd+V - 粘贴截图</li>
        </ul>
        
        <p><b>提示：</b>所有功能都可以通过工具栏按钮或快捷键访问。</p>
        """
        
        self.editor.setHtml(test_html)


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 创建测试窗口
    window = TestWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
