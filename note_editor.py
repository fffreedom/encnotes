#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
笔记编辑器 - 支持富文本和数学公式
"""

from PyQt6.QtWidgets import (
    QTextEdit, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextBrowser,
    QSplitter
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QTextCursor, QFont, QTextCharFormat, QColor
from math_renderer import MathRenderer


class NoteEditor(QTextEdit):
    """笔记编辑器类"""
    
    def __init__(self):
        super().__init__()
        self.math_renderer = MathRenderer()
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        # 设置字体
        font = QFont("SF Pro Text", 14)  # Mac系统字体
        self.setFont(font)
        
        # 设置样式
        self.setStyleSheet("""
            QTextEdit {
                border: none;
                padding: 20px;
                background-color: #ffffff;
            }
        """)
        
        # 启用富文本
        self.setAcceptRichText(True)
        
    def insert_latex(self):
        """插入LaTeX公式"""
        dialog = LatexInputDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            latex_code = dialog.get_latex()
            if latex_code:
                self.insert_math_formula(latex_code, 'latex')
                
    def insert_mathml(self):
        """插入MathML公式"""
        dialog = MathMLInputDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mathml_code = dialog.get_mathml()
            if mathml_code:
                self.insert_math_formula(mathml_code, 'mathml')
                
    def insert_math_formula(self, code, formula_type):
        """插入数学公式"""
        cursor = self.textCursor()
        
        # 渲染公式为图片
        image_data = self.math_renderer.render(code, formula_type)
        
        if image_data:
            # 插入图片
            cursor.insertImage(image_data)
            
            # 在图片后添加一个不可见的标记，保存公式代码
            fmt = QTextCharFormat()
            fmt.setToolTip(f"{formula_type}:{code}")
            fmt.setForeground(QColor(0, 0, 0, 0))
            cursor.insertText(" ", fmt)
        else:
            # 如果渲染失败，插入原始代码
            if formula_type == 'latex':
                cursor.insertText(f"$${code}$$")
            else:
                cursor.insertText(f"[MathML: {code[:50]}...]")


class LatexInputDialog(QDialog):
    """LaTeX输入对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("插入 LaTeX 公式")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # 说明标签
        label = QLabel("输入 LaTeX 公式（不需要包含 $ 符号）：")
        layout.addWidget(label)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 输入框
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("例如: x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}")
        self.input_edit.setMaximumHeight(150)
        self.input_edit.textChanged.connect(self.update_preview)
        splitter.addWidget(self.input_edit)
        
        # 预览区域
        preview_label = QLabel("预览：")
        layout.addWidget(preview_label)
        
        self.preview = QTextBrowser()
        self.preview.setMinimumHeight(150)
        splitter.addWidget(self.preview)
        
        layout.addWidget(splitter)
        
        # 常用公式示例
        examples_label = QLabel("常用示例：")
        layout.addWidget(examples_label)
        
        examples_layout = QHBoxLayout()
        
        examples = [
            ("分数", r"\frac{a}{b}"),
            ("根号", r"\sqrt{x}"),
            ("求和", r"\sum_{i=1}^{n} x_i"),
            ("积分", r"\int_{a}^{b} f(x)dx"),
            ("矩阵", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"),
        ]
        
        for name, code in examples:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, c=code: self.insert_example(c))
            examples_layout.addWidget(btn)
            
        layout.addLayout(examples_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        ok_button = QPushButton("插入")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def insert_example(self, code):
        """插入示例代码"""
        self.input_edit.insertPlainText(code)
        
    def update_preview(self):
        """更新预览"""
        latex_code = self.input_edit.toPlainText()
        if latex_code:
            # 简单预览，显示LaTeX代码
            self.preview.setHtml(f"<p style='font-family: monospace;'>${latex_code}$</p>")
        else:
            self.preview.clear()
            
    def get_latex(self):
        """获取LaTeX代码"""
        return self.input_edit.toPlainText()


class MathMLInputDialog(QDialog):
    """MathML输入对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("插入 MathML 公式")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # 说明标签
        label = QLabel("输入 MathML 代码：")
        layout.addWidget(label)
        
        # 输入框
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText(
            "例如: <math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"
        )
        layout.addWidget(self.input_edit)
        
        # 常用示例
        examples_label = QLabel("常用示例：")
        layout.addWidget(examples_label)
        
        examples_layout = QHBoxLayout()
        
        examples = [
            ("分数", "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"),
            ("根号", "<math><msqrt><mi>x</mi></msqrt></math>"),
            ("上标", "<math><msup><mi>x</mi><mn>2</mn></msup></math>"),
            ("下标", "<math><msub><mi>x</mi><mn>1</mn></msub></math>"),
        ]
        
        for name, code in examples:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, c=code: self.insert_example(c))
            examples_layout.addWidget(btn)
            
        layout.addLayout(examples_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        ok_button = QPushButton("插入")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def insert_example(self, code):
        """插入示例代码"""
        self.input_edit.insertPlainText(code)
        
    def get_mathml(self):
        """获取MathML代码"""
        return self.input_edit.toPlainText()
