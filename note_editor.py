#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
笔记编辑器 - 支持富文本和数学公式
"""

from PyQt6.QtWidgets import (
    QTextEdit, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextBrowser,
    QSplitter, QToolBar, QWidget, QFileDialog, QMessageBox,
    QInputDialog, QMenu, QTableWidget, QTableWidgetItem,
    QSpinBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QSize, QUrl, QMimeData, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import (
    QTextCursor, QFont, QTextCharFormat, QColor, QAction,
    QTextBlockFormat, QTextListFormat, QTextTableFormat,
    QTextFrameFormat, QTextLength, QImage, QPixmap, QClipboard,
    QTextImageFormat
)
from math_renderer import MathRenderer
import os
import uuid
from pathlib import Path
import base64
import html
import re


class PasteImageTextEdit(QTextEdit):
    """支持粘贴图片的文本编辑器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_editor = parent
        self.setMouseTracking(True)
        self.resizing_image = None
        self.resize_start_pos = None
        self.resize_start_size = None
    
    def mousePressEvent(self, event):
        """鼠标按下事件 - 检测是否点击图片"""
        cursor = self.cursorForPosition(event.pos())
        char_format = cursor.charFormat()
        
        # 检查是否点击了图片
        if char_format.isImageFormat():
            self.resizing_image = char_format.toImageFormat()
            self.resize_start_pos = event.pos()
            self.resize_start_size = (self.resizing_image.width(), self.resizing_image.height())
            event.accept()
            return
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 调整图片大小"""
        if self.resizing_image and self.resize_start_pos:
            # 计算新的大小
            delta = event.pos() - self.resize_start_pos
            new_width = max(50, self.resize_start_size[0] + delta.x())
            new_height = max(50, self.resize_start_size[1] + delta.y())
            
            # 保持宽高比
            aspect_ratio = self.resize_start_size[0] / self.resize_start_size[1]
            new_height = int(new_width / aspect_ratio)
            
            # 更新图片大小
            self.resizing_image.setWidth(new_width)
            self.resizing_image.setHeight(new_height)
            
            event.accept()
            return
        
        # 检查鼠标是否悬停在图片上，改变光标
        cursor = self.cursorForPosition(event.pos())
        char_format = cursor.charFormat()
        
        if char_format.isImageFormat():
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 完成调整"""
        if self.resizing_image:
            self.resizing_image = None
            self.resize_start_pos = None
            self.resize_start_size = None
            event.accept()
            return
        
        super().mouseReleaseEvent(event)
    
    def canInsertFromMimeData(self, source):
        """检查是否可以从MIME数据插入"""
        if source.hasImage() or source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)
    
    def insertFromMimeData(self, source):
        """从MIME数据插入（支持截图粘贴）"""
        # 处理图片
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                if self.parent_editor:
                    self.parent_editor.insert_image_to_editor(image)
                return
        
        # 处理文件URL
        if source.hasUrls():
            for url in source.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if self.is_image_file(file_path):
                        image = QImage(file_path)
                        if not image.isNull():
                            if self.parent_editor:
                                self.parent_editor.insert_image_to_editor(image)
                            return
        
        # 默认处理
        super().insertFromMimeData(source)
    
    def is_image_file(self, file_path):
        """检查是否是图片文件"""
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']
        ext = os.path.splitext(file_path)[1].lower()
        return ext in image_extensions


class NoteEditor(QWidget):
    """笔记编辑器类 - 包含工具栏和编辑区"""
    
    def __init__(self):
        super().__init__()
        self.math_renderer = MathRenderer()
        self.attachments = {}  # 存储附件 {filename: filepath}
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建格式工具栏
        self.toolbar = self.create_format_toolbar()
        layout.addWidget(self.toolbar)
        
        # 创建文本编辑器（支持粘贴图片）
        self.text_edit = PasteImageTextEdit(self)
        
        # 设置字体
        font = QFont("SF Pro Text", 14)  # Mac系统字体
        self.text_edit.setFont(font)
        
        # 设置样式
        self.text_edit.setStyleSheet("""
            QTextEdit {
                border: none;
                padding: 20px;
                background-color: #ffffff;
            }
        """)
        
        # 启用富文本
        self.text_edit.setAcceptRichText(True)
        
        # 监听光标位置变化，自动格式化第一行
        self.text_edit.cursorPositionChanged.connect(self.auto_format_first_line)
        
        layout.addWidget(self.text_edit)
        
    def create_format_toolbar(self):
        """创建格式工具栏（模仿Mac备忘录）"""
        # 创建容器widget来实现居中
        toolbar_container = QWidget()
        toolbar_container.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border-bottom: 1px solid #d0d0d0;
            }
        """)
        
        container_layout = QHBoxLayout(toolbar_container)
        container_layout.setContentsMargins(0, 4, 0, 4)
        
        # 添加左侧弹簧
        container_layout.addStretch()
        
        # 创建工具栏
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: transparent;
                border: none;
                padding: 0px;
                spacing: 2px;
            }
            QToolButton {
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                margin: 2px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
            QToolButton:pressed {
                background-color: #d0d0d0;
            }
            QPushButton {
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                margin: 2px;
                background-color: transparent;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        
        # 格式菜单
        format_menu = QMenu("格式", self)
        
        # 标题子菜单
        heading_menu = format_menu.addMenu("标题")
        
        title_action = QAction("标题", self)
        title_action.triggered.connect(lambda: self.apply_heading(1))
        heading_menu.addAction(title_action)
        
        heading_action = QAction("大标题", self)
        heading_action.triggered.connect(lambda: self.apply_heading(2))
        heading_menu.addAction(heading_action)
        
        subheading_action = QAction("小标题", self)
        subheading_action.triggered.connect(lambda: self.apply_heading(3))
        heading_menu.addAction(subheading_action)
        
        format_menu.addSeparator()
        
        # 文本样式
        bold_action = QAction("粗体", self)
        bold_action.setShortcut("Ctrl+B")
        bold_action.triggered.connect(self.toggle_bold)
        format_menu.addAction(bold_action)
        
        italic_action = QAction("斜体", self)
        italic_action.setShortcut("Ctrl+I")
        italic_action.triggered.connect(self.toggle_italic)
        format_menu.addAction(italic_action)
        
        underline_action = QAction("下划线", self)
        underline_action.setShortcut("Ctrl+U")
        underline_action.triggered.connect(self.toggle_underline)
        format_menu.addAction(underline_action)
        
        strikethrough_action = QAction("删除线", self)
        strikethrough_action.triggered.connect(self.toggle_strikethrough)
        format_menu.addAction(strikethrough_action)
        
        format_menu.addSeparator()
        
        # 正文
        body_action = QAction("正文", self)
        body_action.triggered.connect(self.apply_body_text)
        format_menu.addAction(body_action)
        
        format_menu.addSeparator()
        
        # 列表子菜单（移到格式菜单下）
        list_menu = format_menu.addMenu("列表")
        
        bullet_action = QAction("• 项目符号列表", self)
        bullet_action.triggered.connect(self.insert_bullet_list)
        list_menu.addAction(bullet_action)
        
        number_action = QAction("1. 编号列表", self)
        number_action.triggered.connect(self.insert_numbered_list)
        list_menu.addAction(number_action)
        
        # 格式按钮
        format_button = QPushButton("格式")
        format_button.setMenu(format_menu)
        toolbar.addWidget(format_button)
        
        # 表格按钮
        table_button = QPushButton("⊞")
        table_button.setToolTip("表格")
        table_button.clicked.connect(self.insert_table)
        toolbar.addWidget(table_button)
        
        # 附件按钮
        attachment_button = QPushButton("📎")
        attachment_button.setToolTip("附件")
        attachment_button.clicked.connect(self.insert_attachment)
        toolbar.addWidget(attachment_button)
        
        toolbar.addSeparator()
        
        # 超链接按钮
        link_button = QPushButton("🔗")
        link_button.setToolTip("添加链接")
        link_button.setShortcut("Ctrl+K")
        link_button.clicked.connect(self.insert_link)
        toolbar.addWidget(link_button)
        
        # LaTeX按钮
        latex_button = QPushButton("LaTeX")
        latex_button.setToolTip("LaTeX公式")
        latex_button.clicked.connect(self.insert_latex)
        toolbar.addWidget(latex_button)
        
        # MathML按钮
        mathml_button = QPushButton("MathML")
        mathml_button.setToolTip("MathML公式")
        mathml_button.clicked.connect(self.insert_mathml)
        toolbar.addWidget(mathml_button)
        
        # 将工具栏添加到容器
        container_layout.addWidget(toolbar)
        
        # 添加右侧弹簧
        container_layout.addStretch()
        
        return toolbar_container
    
    # 代理属性和方法，使NoteEditor表现得像QTextEdit
    @property
    def textChanged(self):
        """返回文本编辑器的textChanged信号"""
        return self.text_edit.textChanged
    
    def toHtml(self):
        return self.text_edit.toHtml()
    
    def toPlainText(self):
        return self.text_edit.toPlainText()
    
    def setHtml(self, html_content):
        """设置HTML内容，并重新渲染数学公式"""
        # 先设置HTML
        self.text_edit.setHtml(html_content)
        
        # 重新渲染所有数学公式
        self.rerender_formulas()
    
    def clear(self):
        self.text_edit.clear()
        self.attachments.clear()
    
    def blockSignals(self, block):
        return self.text_edit.blockSignals(block)
    
    def textCursor(self):
        return self.text_edit.textCursor()
    
    def setTextCursor(self, cursor):
        self.text_edit.setTextCursor(cursor)
    
    def auto_format_first_line(self):
        """自动将第一行格式化为大标题"""
        # 获取文档
        document = self.text_edit.document()
        if document.isEmpty():
            return
        
        # 获取第一个文本块（第一行）
        first_block = document.firstBlock()
        if not first_block.isValid():
            return
        
        # 创建光标指向第一行
        cursor = QTextCursor(first_block)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        
        # 检查第一行是否已经是标题格式
        char_fmt = cursor.charFormat()
        current_size = char_fmt.fontPointSize()
        
        # 如果第一行不是大标题格式（22号字体），则应用格式
        if current_size != 22:
            # 阻止信号，避免递归
            self.text_edit.blockSignals(True)
            
            # 设置字符格式
            new_char_fmt = QTextCharFormat()
            new_char_fmt.setFontPointSize(22)
            new_char_fmt.setFontWeight(QFont.Weight.Bold)
            
            # 应用格式到第一行
            cursor.mergeCharFormat(new_char_fmt)
            
            # 恢复信号
            self.text_edit.blockSignals(False)
    
    # 格式化方法
    def apply_heading(self, level):
        """应用标题格式"""
        cursor = self.text_edit.textCursor()
        
        # 设置块格式
        block_fmt = QTextBlockFormat()
        
        # 设置字符格式
        char_fmt = QTextCharFormat()
        char_fmt.setFontWeight(QFont.Weight.Bold)
        
        if level == 1:  # 标题
            char_fmt.setFontPointSize(28)
        elif level == 2:  # 大标题
            char_fmt.setFontPointSize(22)
        elif level == 3:  # 小标题
            char_fmt.setFontPointSize(18)
        
        cursor.beginEditBlock()
        cursor.mergeBlockFormat(block_fmt)
        cursor.mergeCharFormat(char_fmt)
        cursor.endEditBlock()
    
    def apply_body_text(self):
        """应用正文格式"""
        cursor = self.text_edit.textCursor()
        
        char_fmt = QTextCharFormat()
        char_fmt.setFontPointSize(14)
        char_fmt.setFontWeight(QFont.Weight.Normal)
        
        cursor.mergeCharFormat(char_fmt)
    
    def toggle_bold(self):
        """切换粗体"""
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        
        if fmt.fontWeight() == QFont.Weight.Bold:
            fmt.setFontWeight(QFont.Weight.Normal)
        else:
            fmt.setFontWeight(QFont.Weight.Bold)
        
        cursor.mergeCharFormat(fmt)
    
    def toggle_italic(self):
        """切换斜体"""
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        cursor.mergeCharFormat(fmt)
    
    def toggle_underline(self):
        """切换下划线"""
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        cursor.mergeCharFormat(fmt)
    
    def toggle_strikethrough(self):
        """切换删除线"""
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        cursor.mergeCharFormat(fmt)
    
    def insert_bullet_list(self):
        """插入项目符号列表"""
        cursor = self.text_edit.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDisc)
    
    def insert_numbered_list(self):
        """插入编号列表"""
        cursor = self.text_edit.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDecimal)
    
    def insert_table(self):
        """插入表格"""
        dialog = TableInsertDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rows, cols = dialog.get_dimensions()
            
            cursor = self.text_edit.textCursor()
            
            # 创建表格格式
            table_format = QTextTableFormat()
            table_format.setBorder(1)
            table_format.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            table_format.setCellPadding(4)
            table_format.setCellSpacing(0)
            table_format.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
            
            # 插入表格
            cursor.insertTable(rows, cols, table_format)
    
    def insert_link(self):
        """插入超链接"""
        cursor = self.text_edit.textCursor()
        selected_text = cursor.selectedText()
        
        dialog = LinkInsertDialog(self, selected_text)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text, url = dialog.get_link()
            
            if text and url:
                # 创建超链接格式
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(url)
                fmt.setForeground(QColor("#007AFF"))  # Mac蓝色
                fmt.setFontUnderline(True)
                
                # 插入或替换文本
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                
                cursor.insertText(text, fmt)
    
    def insert_attachment(self):
        """插入附件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择附件", "", "所有文件 (*.*)"
        )
        
        if file_path:
            file_name = os.path.basename(file_path)
            
            # 保存附件引用
            attachment_id = str(uuid.uuid4())
            self.attachments[attachment_id] = file_path
            
            # 在文本中插入附件标记
            cursor = self.text_edit.textCursor()
            
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#f0f0f0"))
            fmt.setForeground(QColor("#007AFF"))
            fmt.setToolTip(file_path)
            
            cursor.insertText(f"📎 {file_name}", fmt)
            cursor.insertText(" ")  # 添加空格
    
    def rerender_formulas(self):
        """重新渲染HTML中的所有数学公式"""
        html_content = self.text_edit.toHtml()
        
        # 查找所有带有MATH:前缀的图片标签
        # 格式: <img ... alt="MATH:type:code" ... />
        # 支持带或不带style属性的img标签
        pattern = r'<img\s+src="data:image/png;base64,[^"]*"\s+alt="MATH:([^:]+):([^"]+)"(?:\s+style="[^"]*")?\s*/>'
        
        def replace_formula(match):
            formula_type = match.group(1)
            escaped_code = match.group(2)
            # 反转义HTML实体
            code = html.unescape(escaped_code)
            
            # 重新渲染公式
            image_data = self.math_renderer.render(code, formula_type)
            
            if image_data:
                # 将图片转换为base64
                byte_array = QByteArray()
                buffer = QBuffer(byte_array)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image_data.save(buffer, "PNG")
                
                image_base64 = byte_array.toBase64().data().decode()
                
                # 返回新的HTML（保留alt属性中的元数据）
                alt_text = f"MATH:{formula_type}:{escaped_code}"
                return f'<img src="data:image/png;base64,{image_base64}" alt="{alt_text}" style="vertical-align: middle;" />'
            else:
                # 渲染失败，保留原样
                return match.group(0)
        
        # 替换所有公式
        new_html = re.sub(pattern, replace_formula, html_content)
        
        # 如果有变化，更新HTML
        if new_html != html_content:
            # 保存当前光标位置
            cursor = self.text_edit.textCursor()
            position = cursor.position()
            
            # 阻止信号以避免触发自动保存
            self.text_edit.blockSignals(True)
            self.text_edit.setHtml(new_html)
            self.text_edit.blockSignals(False)
            
            # 恢复光标位置
            cursor.setPosition(min(position, len(self.text_edit.toPlainText())))
            self.text_edit.setTextCursor(cursor)
    
    def insert_image_to_editor(self, image):
        """插入图片到编辑器"""
        # 限制图片大小
        max_width = 800
        original_width = image.width()
        original_height = image.height()
        
        if image.width() > max_width:
            image = image.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
        
        # 将图片转换为base64
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        
        image_data = byte_array.toBase64().data().decode()
        
        # 生成唯一的图片名称
        image_name = f"image_{uuid.uuid4().hex[:8]}.png"
        
        # 创建图片格式
        cursor = self.text_edit.textCursor()
        
        # 使用data URI插入图片，添加样式使其可调整大小
        # 添加 contenteditable="false" 使图片可以被选中
        # 添加 style 使图片可以通过拖动边角调整大小
        image_html = f'''<img src="data:image/png;base64,{image_data}" 
                         alt="{image_name}" 
                         width="{image.width()}" 
                         height="{image.height()}"
                         style="max-width: 100%; cursor: move; display: block; margin: 10px 0;" />'''
        cursor.insertHtml(image_html)
        cursor.insertBlock()  # 添加新行
        
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
        cursor = self.text_edit.textCursor()
        
        # 渲染公式为图片
        image_data = self.math_renderer.render(code, formula_type)
        
        if image_data:
            # 将图片转换为base64
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image_data.save(buffer, "PNG")
            
            image_base64 = byte_array.toBase64().data().decode()
            
            # 使用alt属性保存公式元数据（格式: MATH:type:code）
            # alt属性会被QTextEdit保留
            import html
            escaped_code = html.escape(code)
            alt_text = f"MATH:{formula_type}:{escaped_code}"
            
            # 公式图片添加样式（vertical-align: middle 使公式与文本在行高中间对齐）
            formula_html = f'<img src="data:image/png;base64,{image_base64}" alt="{alt_text}" style="vertical-align: bottom;" />'
            cursor.insertHtml(formula_html)
        else:
            # 如果渲染失败，插入原始代码
            if formula_type == 'latex':
                cursor.insertText(f"$${code}$$")
            else:
                cursor.insertText(f"[MathML: {code[:50]}...]")


class TableInsertDialog(QDialog):
    """表格插入对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("插入表格")
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # 行数
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel("行数:"))
        self.row_spin = QSpinBox()
        self.row_spin.setMinimum(1)
        self.row_spin.setMaximum(50)
        self.row_spin.setValue(3)
        row_layout.addWidget(self.row_spin)
        layout.addLayout(row_layout)
        
        # 列数
        col_layout = QHBoxLayout()
        col_layout.addWidget(QLabel("列数:"))
        self.col_spin = QSpinBox()
        self.col_spin.setMinimum(1)
        self.col_spin.setMaximum(20)
        self.col_spin.setValue(3)
        col_layout.addWidget(self.col_spin)
        layout.addLayout(col_layout)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def get_dimensions(self):
        """获取表格尺寸"""
        return self.row_spin.value(), self.col_spin.value()


class LinkInsertDialog(QDialog):
    """超链接插入对话框"""
    
    def __init__(self, parent=None, selected_text=""):
        super().__init__(parent)
        self.selected_text = selected_text
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("添加链接")
        self.setFixedSize(400, 150)
        
        layout = QVBoxLayout()
        
        # 显示文本
        text_layout = QHBoxLayout()
        text_layout.addWidget(QLabel("显示文本:"))
        self.text_input = QLineEdit()
        self.text_input.setText(self.selected_text)
        self.text_input.setPlaceholderText("链接文本")
        text_layout.addWidget(self.text_input)
        layout.addLayout(text_layout)
        
        # URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("链接地址:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def get_link(self):
        """获取链接信息"""
        return self.text_input.text(), self.url_input.text()


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
