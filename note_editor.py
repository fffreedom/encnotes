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
        
        # 图片选中和缩放相关
        self.selected_image = None  # 当前选中的图片格式
        self.selected_image_rect = None  # 图片的矩形区域
        self.selected_image_cursor = None  # 图片的光标位置
        
        # 缩放相关
        self.resizing = False
        self.resize_handle = None  # 'tl', 't', 'tr', 'r', 'br', 'b', 'bl', 'l'
        self.resize_start_pos = None
        self.resize_start_size = None
        
        # 拖动移动相关
        self.dragging = False
        self.drag_start_pos = None
        self.drag_start_cursor_pos = None
        self.drag_preview_cursor = None  # 拖动预览光标位置
        
        # 文本选择相关
        self.text_selecting = False
        
        # 表格选中相关
        self.selected_table = None  # 当前选中的表格
        self.selected_table_cursor = None  # 表格的光标位置
        self.table_select_handle_size = 20  # 表格全选图标的大小
        self.table_debug_logged = False  # 表格调试日志是否已输出
        
        # 边界检测阈值
        self.handle_size = 8
        
        # 监听滚动事件
        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self.on_scroll)
        

    
    def on_scroll(self):
        """滚动事件处理 - 更新边界框位置"""
        if self.selected_image and self.selected_image_cursor:
            # 重新计算图片位置
            self.selected_image_rect = self.get_image_rect_at_cursor(self.selected_image_cursor)
            # 触发重绘
            self.viewport().update()
    
    def get_table_rect(self, table):
        """获取表格的精确边界框（使用表格格式宽度信息）
        
        Args:
            table: QTextTable对象
            
        Returns:
            QRectF: 表格的边界框，如果计算失败则返回None
        """
        if not table:
            return None
        
        from PyQt6.QtCore import QRectF
        
        # 只在第一次或调试模式下输出日志
        debug = not self.table_debug_logged
        if debug:
            print(f"\n=== 表格边界计算调试（使用表格格式宽度） ===")
            print(f"表格尺寸: {table.rows()} 行 x {table.columns()} 列")
        
        try:
            # 获取表格格式
            table_format = table.format()
            
            # 获取表格宽度设置
            table_width_length = table_format.width()
            
            if debug:
                print(f"表格宽度类型: {table_width_length.type()}")
                print(f"表格宽度值: {table_width_length.rawValue()}")
            
            # 获取左上角单元格（第一行第一列）
            top_left_cell = table.cellAt(0, 0)
            if not top_left_cell.isValid():
                if debug:
                    print("错误：无法获取左上角单元格")
                return None
            
            # 获取右下角单元格（最后一行最后一列）
            bottom_right_cell = table.cellAt(table.rows() - 1, table.columns() - 1)
            if not bottom_right_cell.isValid():
                if debug:
                    print("错误：无法获取右下角单元格")
                return None
            
            # 获取左上角单元格的光标矩形（第一个字符位置）
            top_left_cursor = top_left_cell.firstCursorPosition()
            top_left_rect = self.cursorRect(top_left_cursor)
            
            # 获取右下角单元格的光标矩形（最后一个字符位置）
            bottom_right_cursor = bottom_right_cell.lastCursorPosition()
            bottom_right_rect = self.cursorRect(bottom_right_cursor)
            
            if debug:
                print(f"左上角单元格光标矩形: {top_left_rect}")
                print(f"右下角单元格光标矩形: {bottom_right_rect}")
            
            # 计算表格边界
            # 左边界：左上角单元格的左边界 - 边框宽度
            border_width = table_format.border()
            cell_padding = table_format.cellPadding()
            
            left = top_left_rect.left() - border_width - cell_padding
            
            # 上边界：左上角单元格的上边界 - 边框宽度
            top = top_left_rect.top() - border_width - cell_padding
            
            # 下边界：右下角单元格的下边界 + 边框宽度
            bottom = bottom_right_rect.bottom() + border_width + cell_padding
            
            # **关键改进**：使用表格格式的宽度信息计算右边界
            # 获取文档的实际渲染宽度
            document = self.document()
            doc_layout = document.documentLayout()
            
            # 获取文档的页面大小
            doc_size = doc_layout.documentSize()
            doc_width = doc_size.width()
            
            # 获取文档的根框架（包含所有内容）
            root_frame = document.rootFrame()
            root_frame_format = root_frame.frameFormat()
            
            # 获取文档的左右边距
            doc_left_margin = root_frame_format.leftMargin()
            doc_right_margin = root_frame_format.rightMargin()
            
            # 计算内容区域的实际宽度（这才是表格100%宽度的参考）
            content_width = doc_width - doc_left_margin - doc_right_margin
            
            if debug:
                print(f"文档总宽度: {doc_width}")
                print(f"文档左边距: {doc_left_margin}, 右边距: {doc_right_margin}")
                print(f"内容区域宽度: {content_width}")
                print(f"表格左边界位置: {left}")
            
            # 根据表格宽度类型计算实际宽度
            from PyQt6.QtGui import QTextLength
            
            if table_width_length.type() == QTextLength.Type.PercentageLength:
                # 百分比宽度 - 相对于内容区域宽度
                percentage = table_width_length.rawValue()
                table_total_width = content_width * percentage / 100.0
                if debug:
                    print(f"表格宽度（百分比）: {percentage}%")
                    print(f"表格总宽度: {table_total_width}")
            elif table_width_length.type() == QTextLength.Type.FixedLength:
                # 固定宽度
                table_total_width = table_width_length.rawValue()
                if debug:
                    print(f"表格宽度（固定）: {table_total_width}")
            else:
                # 可变宽度，使用内容区域宽度
                table_total_width = content_width
                if debug:
                    print(f"表格宽度（可变）: {table_total_width}")
            
            # 计算右边界：左边界 + 表格总宽度
            # left已经是表格的实际左边界（包含了边框和内边距的调整）
            right = left + table_total_width
            
            # 创建矩形
            table_rect = QRectF(left, top, right - left, bottom - top)
            
            if debug:
                print(f"计算的表格边界:")
                print(f"  left={left}, top={top}")
                print(f"  right={right}, bottom={bottom}")
                print(f"  width={right - left}, height={bottom - top}")
                print(f"  表格总宽度={table_total_width}")
                print(f"  右边界计算: {left} + {table_total_width} = {right}")
                print(f"最终表格矩形: {table_rect}")
                print(f"=== 调试结束 ===\n")
                self.table_debug_logged = True  # 标记已输出过日志
            
            return table_rect
            
        except Exception as e:
            if debug:
                print(f"获取表格边界时发生错误: {e}")
                import traceback
                traceback.print_exc()
            return None
    
    def is_click_on_table_border(self, pos, table):
        """检查点击位置是否在表格的边框线上
        
        Args:
            pos: 鼠标点击位置
            table: QTextTable对象
            
        Returns:
            bool: 如果点击在边框线上返回True，否则返回False
        """
        if not table:
            return False
        
        table_rect = self.get_table_rect(table)
        if not table_rect:
            return False
        
        # 定义边框线的检测容差（像素）
        tolerance = 5
        
        x = pos.x()
        y = pos.y()
        
        # 检查是否在表格矩形范围内（包含容差）
        if not (table_rect.left() - tolerance <= x <= table_rect.right() + tolerance and
                table_rect.top() - tolerance <= y <= table_rect.bottom() + tolerance):
            return False
        
        # 检查是否靠近四条边框线
        near_left = abs(x - table_rect.left()) <= tolerance
        near_right = abs(x - table_rect.right()) <= tolerance
        near_top = abs(y - table_rect.top()) <= tolerance
        near_bottom = abs(y - table_rect.bottom()) <= tolerance
        
        # 如果靠近任何一条边框线，返回True
        return near_left or near_right or near_top or near_bottom
    

    
    def open_attachment(self, url_or_path):
        """处理链接点击事件 - 打开附件
        
        Args:
            url_or_path: 可以是字符串路径或QUrl对象
        """
        try:
            import subprocess
            import platform
            import tempfile
            
            # 获取文件路径或附件ID
            if isinstance(url_or_path, str):
                file_path = url_or_path
            else:
                # QUrl对象
                file_path = url_or_path.toString()
            
            # 检查是否是加密附件（attachment://协议）
            if file_path.startswith('attachment://'):
                attachment_id = file_path[13:]  # 去掉 'attachment://' 前缀
                
                # 获取附件管理器
                if not self.parent_editor or not self.parent_editor.note_manager:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "错误", "无法访问附件管理器")
                    return
                
                attachment_manager = self.parent_editor.note_manager.attachment_manager
                
                # 使用AttachmentManager的新方法打开附件（自动管理临时文件）
                success, message = attachment_manager.open_attachment_with_system(attachment_id)
                if not success:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "打开失败", message)
                    return
                
                print(f"打开加密附件: {message}")
                return
            
            # 处理普通文件链接
            # 去掉 file:// 前缀（如果有）
            if file_path.startswith('file://'):
                file_path = file_path[7:]  # 去掉 'file://' 前缀
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "文件不存在", f"无法找到文件：\n{file_path}")
                return
            
            # 根据操作系统使用不同的命令打开文件
            system = platform.system()
            if system == 'Darwin':  # macOS
                subprocess.run(['open', file_path])
            elif system == 'Windows':
                os.startfile(file_path)
            elif system == 'Linux':
                subprocess.run(['xdg-open', file_path])
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "不支持的系统", f"当前系统不支持自动打开文件")
                
            print(f"打开附件: {file_path}")
            
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "打开失败", f"无法打开文件：\n{str(e)}")
            print(f"打开附件失败: {e}")
            import traceback
            traceback.print_exc()
    
    def paintEvent(self, event):
        """绘制事件 - 绘制选中图片的边界框"""
        super().paintEvent(event)
        
        # 绘制选中表格的边界框和全选图标
        if self.selected_table and self.selected_table_cursor:
            from PyQt6.QtGui import QPainter, QPen, QBrush
            from PyQt6.QtCore import QRectF, QRect
            
            painter = QPainter(self.viewport())
            
            # 计算表格的实际边界框
            table_rect = self.get_table_rect(self.selected_table)
            
            if table_rect:
                # 输出表格边框位置调试信息
                print(f"\n=== 表格渲染调试 ===")
                print(f"表格边界框: left={table_rect.left()}, top={table_rect.top()}")
                print(f"           right={table_rect.right()}, bottom={table_rect.bottom()}")
                print(f"           width={table_rect.width()}, height={table_rect.height()}")
                print(f"=== 渲染调试结束 ===\n")
                
                # 只绘制边框，不绘制角标
                # 绘制蓝色边界框
                pen = QPen(QColor("#007AFF"), 3)
                painter.setPen(pen)
                painter.drawRect(table_rect)
            
            painter.end()
        
        if self.selected_image and self.selected_image_cursor:
            # 实时计算图片位置（确保滚动时位置正确）
            self.selected_image_rect = self.get_image_rect_at_cursor(self.selected_image_cursor)
            
            if self.selected_image_rect:
                from PyQt6.QtGui import QPainter, QPen
                
                painter = QPainter(self.viewport())
                
                # 绘制边界框
                pen = QPen(QColor("#007AFF"), 2)
                painter.setPen(pen)
                painter.drawRect(self.selected_image_rect)
                
                # 绘制8个控制点
                handles = self.get_resize_handles()
                painter.setBrush(QColor("#007AFF"))
                for handle_rect in handles.values():
                    painter.drawRect(handle_rect)
                
                painter.end()
        
        # 绘制拖动预览指示器
        if self.dragging and self.drag_preview_cursor:
            from PyQt6.QtGui import QPainter, QPen
            from PyQt6.QtCore import QPoint
            
            painter = QPainter(self.viewport())
            
            # 获取预览位置的光标矩形
            preview_rect = self.cursorRect(self.drag_preview_cursor)
            
            # 绘制一条垂直的蓝色虚线，表示图片将被插入的位置
            pen = QPen(QColor("#007AFF"), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            
            # 绘制插入位置指示线
            x = preview_rect.left()
            y_start = preview_rect.top() - 5
            y_end = preview_rect.bottom() + 5
            
            painter.drawLine(QPoint(x, y_start), QPoint(x, y_end))
            
            # 在指示线两端绘制小三角形
            from PyQt6.QtGui import QPolygon
            
            # 上三角
            top_triangle = QPolygon([
                QPoint(x, y_start),
                QPoint(x - 4, y_start - 6),
                QPoint(x + 4, y_start - 6)
            ])
            painter.setBrush(QColor("#007AFF"))
            painter.drawPolygon(top_triangle)
            
            # 下三角
            bottom_triangle = QPolygon([
                QPoint(x, y_end),
                QPoint(x - 4, y_end + 6),
                QPoint(x + 4, y_end + 6)
            ])
            painter.drawPolygon(bottom_triangle)
            
            painter.end()
    
    def get_resize_handles(self):
        """获取8个缩放控制点的矩形区域"""
        if not self.selected_image_rect:
            return {}
        
        from PyQt6.QtCore import QRect
        
        rect = self.selected_image_rect
        hs = self.handle_size
        
        handles = {
            'tl': QRect(rect.left() - hs//2, rect.top() - hs//2, hs, hs),
            't': QRect(rect.center().x() - hs//2, rect.top() - hs//2, hs, hs),
            'tr': QRect(rect.right() - hs//2, rect.top() - hs//2, hs, hs),
            'r': QRect(rect.right() - hs//2, rect.center().y() - hs//2, hs, hs),
            'br': QRect(rect.right() - hs//2, rect.bottom() - hs//2, hs, hs),
            'b': QRect(rect.center().x() - hs//2, rect.bottom() - hs//2, hs, hs),
            'bl': QRect(rect.left() - hs//2, rect.bottom() - hs//2, hs, hs),
            'l': QRect(rect.left() - hs//2, rect.center().y() - hs//2, hs, hs),
        }
        
        return handles
    
    def get_handle_at_pos(self, pos):
        """获取鼠标位置对应的控制点"""
        handles = self.get_resize_handles()
        for name, rect in handles.items():
            if rect.contains(pos):
                return name
        return None
    
    def get_cursor_for_handle(self, handle):
        """根据控制点返回对应的光标形状"""
        cursor_map = {
            'tl': Qt.CursorShape.SizeFDiagCursor,
            't': Qt.CursorShape.SizeVerCursor,
            'tr': Qt.CursorShape.SizeBDiagCursor,
            'r': Qt.CursorShape.SizeHorCursor,
            'br': Qt.CursorShape.SizeFDiagCursor,
            'b': Qt.CursorShape.SizeVerCursor,
            'bl': Qt.CursorShape.SizeBDiagCursor,
            'l': Qt.CursorShape.SizeHorCursor,
        }
        return cursor_map.get(handle, Qt.CursorShape.ArrowCursor)
    
    def find_image_at_position(self, pos):
        """通过鼠标位置查找图片
        
        Args:
            pos: 鼠标点击的位置（视口坐标）
            
        Returns:
            tuple: (image_format, image_cursor, image_rect) 如果找到图片，否则返回 (None, None, None)
        """
        # 遍历文档中的所有字符，查找图片
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        
        while not cursor.atEnd():
            # 保存当前位置（图片字符的起始位置）
            current_pos = cursor.position()
            
            # 检查当前位置的字符格式
            # 注意：需要先向右移动一个字符，再检查格式
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            char_format = cursor.charFormat()
            selected_text = cursor.selectedText()
            
            # **关键修复**：只检测真正的图片字符（U+FFFC），忽略段落分隔符（U+2029）
            if char_format.isImageFormat() and selected_text == '\ufffc':
                # 找到一个真正的图片字符
                # 创建一个新光标，指向图片字符的起始位置
                image_cursor = QTextCursor(self.document())
                image_cursor.setPosition(current_pos)
                
                # 计算图片的矩形区域
                img_format = char_format.toImageFormat()
                img_rect = self.get_image_rect_at_cursor(image_cursor)
                
                # 检查鼠标位置是否在这个图片的矩形内
                if img_rect and img_rect.contains(pos):
                    return (img_format, image_cursor, img_rect)
            
            # 清除选区，移动到下一个字符
            cursor.clearSelection()
        
        return (None, None, None)
    
    def get_image_rect_at_cursor(self, cursor):
        """获取光标位置图片的矩形区域
        
        Args:
            cursor: 指向图片字符起始位置的光标
            
        Returns:
            QRect: 图片的矩形区域，如果不是图片则返回None
        """
        # 创建一个光标副本，避免修改原光标
        temp_cursor = QTextCursor(cursor)
        
        # 向右移动一个字符并选中，这样charFormat()才能返回图片字符的格式
        temp_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        char_format = temp_cursor.charFormat()
        
        if not char_format.isImageFormat():
            return None
        
        # 获取图片格式
        img_format = char_format.toImageFormat()
        width = img_format.width()
        height = img_format.height()
        
        # 创建一个新光标，指向图片字符的起始位置
        image_cursor = QTextCursor(cursor)
        
        # 获取图片字符的光标矩形
        cursor_rect = self.cursorRect(image_cursor)
        
        from PyQt6.QtCore import QRect
        
        # 图片的左边界是光标的左边界
        image_left = cursor_rect.left()
        
        # **关键修复**：图片的顶部应该根据图片在行中的实际渲染位置计算
        # Qt 的 QTextEdit 中，图片作为内联元素，底部对齐文本基线
        # 但是当图片很高时，行高会自动扩展以容纳图片
        # 我们需要找到图片实际显示的顶部位置
        
        # 方法：向右移动光标到图片之后，获取该位置的光标矩形
        # 图片之后的光标矩形的 bottom() 就是图片底部的位置
        temp_cursor2 = QTextCursor(image_cursor)
        temp_cursor2.movePosition(QTextCursor.MoveOperation.Right)
        cursor_rect_after = self.cursorRect(temp_cursor2)
        
        # 图片底部 = 图片之后光标的底部
        image_bottom = cursor_rect_after.bottom()
        
        # 图片顶部 = 图片底部 - 图片高度
        image_top = image_bottom - int(height)
        
        result_rect = QRect(image_left, image_top, int(width), int(height))
        
        # 返回图片的矩形区域（在视口坐标系中）
        return result_rect
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        
        if event.button() == Qt.MouseButton.LeftButton:
            # 首先检查是否点击了链接（附件）
            cursor = self.cursorForPosition(event.pos())
            char_format = cursor.charFormat()
            
            if char_format.isAnchor():
                # 点击了链接，获取URL并打开
                anchor_href = char_format.anchorHref()
                if anchor_href:
                    self.open_attachment(anchor_href)
                    event.accept()
                    return
            
            # 检查是否点击了表格
            table = cursor.currentTable()
            if table:
                # 检查是否点击了表格边框
                if self.is_click_on_table_border(event.pos(), table):
                    # 点击了边框，选中整个表格
                    self.selected_table = table
                    self.selected_table_cursor = cursor
                    
                    # 取消图片选中
                    if self.selected_image:
                        self.selected_image = None
                        self.selected_image_rect = None
                        self.selected_image_cursor = None
                    
                    self.viewport().update()
                    event.accept()
                    return
                else:
                    # 点击了表格内容区域，取消表格选中，进入编辑模式
                    if self.selected_table:
                        self.selected_table = None
                        self.selected_table_cursor = None
                        self.viewport().update()
                    
                    # 使用默认行为，进入单元格编辑模式
                    super().mousePressEvent(event)
                    return
            else:
                # 取消表格选中
                if self.selected_table:
                    self.selected_table = None
                    self.selected_table_cursor = None
                    self.viewport().update()
            
            # 检查是否点击了控制点
            if self.selected_image:
                handle = self.get_handle_at_pos(event.pos())
                if handle:
                    # 开始缩放
                    self.resizing = True
                    self.resize_handle = handle
                    self.resize_start_pos = event.pos()
                    self.resize_start_size = (self.selected_image.width(), self.selected_image.height())
                    event.accept()
                    return
                
                # 检查是否点击了图片中心区域（用于拖动移动）
                if self.selected_image_rect and self.selected_image_rect.contains(event.pos()):
                    # 开始拖动
                    self.dragging = True
                    self.drag_start_pos = event.pos()
                    self.drag_start_cursor_pos = self.selected_image_cursor.position()
                    event.accept()
                    return
            
            # **关键修复**：使用像素位置而非光标位置来检测图片点击
            # 通过遍历文档中的所有图片，计算它们的矩形区域，检查鼠标是否点击在图片上
            image_format, image_cursor, image_rect = self.find_image_at_position(event.pos())
            
            if image_format and image_cursor:
                # 选中图片
                self.selected_image = image_format
                self.selected_image_cursor = image_cursor
                self.selected_image_rect = image_rect
                
                # **关键修复**：查找并选中真正的图片字符（U+FFFC）
                # 在空行行首插入图片时，Qt会插入段落分隔符（U+2029）+ 图片字符（U+FFFC）
                # 我们需要找到真正的图片字符并选中它
                cursor = QTextCursor(image_cursor)
                real_image_pos = None
                
                # 从当前位置开始，向右查找最多2个字符，找到真正的图片字符
                for offset in range(2):
                    check_pos = image_cursor.position() + offset
                    cursor.setPosition(check_pos)
                    
                    # 向右移动一个字符并选中
                    if cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1):
                        selected_text = cursor.selectedText()
                        char_format = cursor.charFormat()
                        
                        # 检查是否是真正的图片字符
                        if char_format.isImageFormat() and selected_text == '\ufffc':
                            real_image_pos = check_pos
                            break
                    
                    # 清除选区，继续查找
                    cursor.clearSelection()
                
                if real_image_pos is not None:
                    # 选中真正的图片字符
                    cursor.setPosition(real_image_pos)
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                    self.setTextCursor(cursor)
                else:
                    # 如果找不到真正的图片字符，使用原来的逻辑
                    cursor = QTextCursor(image_cursor)
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                    self.setTextCursor(cursor)
                
                self.viewport().update()
                event.accept()
                return
            else:
                # 取消选中
                if self.selected_image:
                    self.selected_image = None
                    self.selected_image_rect = None
                    self.selected_image_cursor = None
                    self.viewport().update()
            
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        # 处理缩放
        if self.resizing and self.resize_handle and self.resize_start_pos:
            # 计算偏移量
            delta = event.pos() - self.resize_start_pos
            
            # 根据控制点计算新的尺寸
            new_width = self.resize_start_size[0]
            new_height = self.resize_start_size[1]
            aspect_ratio = self.resize_start_size[0] / self.resize_start_size[1]
            
            if self.resize_handle in ['tl', 'l', 'bl']:
                # 左侧控制点：减小宽度
                new_width = max(50, self.resize_start_size[0] - delta.x())
            elif self.resize_handle in ['tr', 'r', 'br']:
                # 右侧控制点：增加宽度
                new_width = max(50, self.resize_start_size[0] + delta.x())
            
            if self.resize_handle in ['tl', 't', 'tr']:
                # 顶部控制点：减小高度
                new_height = max(50, self.resize_start_size[1] - delta.y())
            elif self.resize_handle in ['bl', 'b', 'br']:
                # 底部控制点：增加高度
                new_height = max(50, self.resize_start_size[1] + delta.y())
            
            # 角落控制点：保持宽高比
            if self.resize_handle in ['tl', 'tr', 'bl', 'br']:
                # 以宽度为准，计算高度
                new_height = int(new_width / aspect_ratio)
            
            # 更新图片
            self.update_image_size(new_width, new_height)
            
            event.accept()
            return
        
        # 处理拖动移动
        if self.dragging and self.drag_start_pos:
            # 更新预览光标位置
            target_pos = event.pos()
            self.drag_preview_cursor = self.cursorForPosition(target_pos)
            
            # 更新光标形状
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            
            # 触发重绘以显示预览指示器
            self.viewport().update()
            
            event.accept()
            return
        
        # 更新光标形状
        if self.selected_image:
            handle = self.get_handle_at_pos(event.pos())
            if handle:
                self.viewport().setCursor(self.get_cursor_for_handle(handle))
            else:
                # 检查是否在图片区域内
                if self.selected_image_rect and self.selected_image_rect.contains(event.pos()):
                    self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        else:
            # 检查是否悬停在图片上（使用像素位置检测）
            image_format, _, _ = self.find_image_at_position(event.pos())
            if image_format:
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                # 检查是否悬停在表格上
                cursor = self.cursorForPosition(event.pos())
                table = cursor.currentTable()
                if table:
                    # 检查是否悬停在表格边框上
                    if self.is_click_on_table_border(event.pos(), table):
                        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    else:
                        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
                else:
                    self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        
        if self.resizing:
            self.resizing = False
            self.resize_handle = None
            self.resize_start_pos = None
            self.resize_start_size = None
            event.accept()
            return
        
        if self.dragging:
            # 计算鼠标移动的距离
            delta = event.pos() - self.drag_start_pos
            
            # 如果移动距离足够大，执行移动
            if abs(delta.x()) > 5 or abs(delta.y()) > 5:
                # 获取目标位置的光标
                target_cursor = self.cursorForPosition(event.pos())
                # 执行图片移动
                self.move_image_to_cursor(target_cursor)
            
            # 重置拖动状态
            self.dragging = False
            self.drag_start_pos = None
            self.drag_start_cursor_pos = None
            self.drag_preview_cursor = None  # 清除预览光标
            
            # 拖动结束后取消选中状态，允许用户重新点击选择
            self.selected_image = None
            self.selected_image_rect = None
            self.selected_image_cursor = None
            self.viewport().update()
            
            event.accept()
            return
        
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件 - 防止双击图片时被删除"""
        if event.button() == Qt.MouseButton.LeftButton:
            # **使用像素位置检测图片**
            image_format, image_cursor, image_rect = self.find_image_at_position(event.pos())
            
            if image_format and image_cursor:
                # 检查是否是公式图片
                image_name = image_format.name()
                
                if '|||MATH:' in image_name:
                    # 这是一个公式图片，弹出编辑对话框
                    parts = image_name.split('|||', 1)
                    if len(parts) == 2:
                        metadata = parts[1]  # MATH:type:code
                        
                        # 解析元数据
                        if metadata.startswith('MATH:'):
                            metadata_parts = metadata[5:].split(':', 1)  # 去掉 'MATH:' 前缀
                            if len(metadata_parts) == 2:
                                formula_type = metadata_parts[0]
                                escaped_code = metadata_parts[1]
                                # 反转义HTML实体
                                code = html.unescape(escaped_code)
                                
                                # 调用父编辑器的编辑公式方法
                                if self.parent_editor:
                                    self.parent_editor.edit_math_formula(
                                        code, formula_type, image_cursor, image_format
                                    )
                                
                                event.accept()
                                return
                
                # 普通图片，只选中图片，不执行其他操作
                self.selected_image = image_format
                self.selected_image_cursor = image_cursor
                self.selected_image_rect = image_rect
                self.viewport().update()
                # 阻止默认的双击行为（选中文字等）
                event.accept()
                return
            
            # 检查是否双击了链接（附件）
            cursor = self.cursorForPosition(event.pos())
            char_format = cursor.charFormat()
            if char_format.isAnchor():
                # 双击链接时打开附件
                anchor_href = char_format.anchorHref()
                if anchor_href:
                    self.open_attachment(anchor_href)
                    event.accept()
                    return
        
        # 其他情况使用默认行为
        super().mouseDoubleClickEvent(event)
    
    def keyPressEvent(self, event):
        """键盘事件 - 使用默认行为，允许删除选区中的所有内容（包括图片）"""
        # 检查是否按下了删除键（Delete 或 Backspace）
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            # 如果有选中的表格，需要判断是否在编辑表格内容
            if self.selected_table and self.selected_table_cursor:
                # 获取当前光标
                current_cursor = self.textCursor()
                
                # 检查当前光标是否在表格内（正在编辑单元格）
                current_table = current_cursor.currentTable()
                
                # 如果当前光标在表格内，说明用户正在编辑单元格内容
                # 此时不应该删除整个表格，而是使用默认行为删除单元格内容
                if current_table == self.selected_table:
                    # 用户正在编辑表格内容，使用默认行为
                    super().keyPressEvent(event)
                    return
                
                # 如果当前光标不在表格内，说明用户选中了整个表格
                # 此时应该删除整个表格
                # 创建光标并选中整个表格
                cursor = QTextCursor(self.document())
                
                # 获取表格在文档中的位置
                table_start = self.selected_table.firstPosition()
                table_end = self.selected_table.lastPosition()
                
                cursor.setPosition(table_start)
                cursor.setPosition(table_end + 1, QTextCursor.MoveMode.KeepAnchor)
                
                # 删除选中的内容（包括表格）
                cursor.removeSelectedText()
                
                # 清除选中状态
                self.selected_table = None
                self.selected_table_cursor = None
                self.viewport().update()
                
                event.accept()
                return
        
        # 直接使用默认行为，不做任何特殊处理
        # 这样选区中的图片和文本都会被正常删除
        super().keyPressEvent(event)
    
    def update_image_size(self, new_width, new_height):
        """更新图片尺寸"""
        if not self.selected_image or not self.selected_image_cursor:
            return
        
        # 保存原位置
        old_pos = self.selected_image_cursor.position()
        
        # 创建光标对象
        cursor = QTextCursor(self.document())
        
        # 使用编辑块确保删除和插入是原子操作
        cursor.beginEditBlock()
        
        # **关键修复**：查找真正的图片字符位置（U+FFFC）
        # 从 old_pos 开始，向右查找最多2个字符，找到真正的图片字符
        real_image_pos = None
        has_paragraph_separator = False
        
        for offset in range(2):  # 检查当前位置和下一个位置
            check_pos = old_pos + offset
            cursor.setPosition(check_pos)
            
            # 向右移动一个字符并选中
            if cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1):
                selected_text = cursor.selectedText()
                char_format = cursor.charFormat()
                
                # 检查是否是真正的图片字符
                if char_format.isImageFormat() and selected_text == '\ufffc':
                    real_image_pos = check_pos
                    
                    # 检查图片字符前面是否有段落分隔符
                    if real_image_pos > 0:
                        cursor.setPosition(real_image_pos - 1)
                        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                        prev_text = cursor.selectedText()
                        prev_format = cursor.charFormat()
                        
                        if prev_format.isImageFormat() and prev_text == '\u2029':
                            has_paragraph_separator = True
                    
                    break
            
            # 清除选区，继续查找
            cursor.clearSelection()
        
        if real_image_pos is None:
            cursor.endEditBlock()
            return
        
        # **关键修复**：检查图片是否是公式（通过检查图片名称中的元数据）
        # 新格式：data:image/png;base64,...|||MATH:type:code
        image_name = self.selected_image.name()
        
        is_formula = False
        formula_metadata = None
        image_base_name = image_name
        
        # 检查是否包含公式元数据（使用 ||| 分隔符）
        if '|||MATH:' in image_name:
            parts = image_name.split('|||', 1)
            if len(parts) == 2:
                is_formula = True
                image_base_name = parts[0]  # data:image/png;base64,...
                formula_metadata = parts[1]  # MATH:type:code
        
        # **优化**：只删除图片字符本身，保留段落分隔符（如果有）
        # 移动到图片字符位置
        cursor.setPosition(real_image_pos)
        
        # 向右选中图片字符（只删除1个字符）
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
        
        # 删除选中的图片字符
        cursor.removeSelectedText()
        
        # 在删除位置插入新图片
        new_format = QTextImageFormat()
        if is_formula and formula_metadata:
            # 如果是公式，重新组合图片名称（保留元数据）
            new_format.setName(f"{image_base_name}|||{formula_metadata}")
        else:
            # 普通图片
            new_format.setName(image_name)
        
        new_format.setWidth(new_width)
        new_format.setHeight(new_height)
        # 设置垂直对齐方式为AlignBaseline，使图片底部与文本基线对齐
        new_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignBaseline)
        cursor.insertImage(new_format)
        
        # 结束编辑块
        cursor.endEditBlock()
        
        # 更新选中状态（光标现在在图片之后，需要向左移动一个位置）
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        
        # 重新获取图片格式（因为可能已经改变）
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
        new_char_format = cursor.charFormat()
        if new_char_format.isImageFormat():
            self.selected_image = new_char_format.toImageFormat()
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        
        self.selected_image_cursor = cursor
        self.selected_image_rect = self.get_image_rect_at_cursor(cursor)
        
        # 刷新显示
        self.viewport().update()
    
    def move_image_to_cursor(self, target_cursor):
        """移动图片到新的光标位置"""
        if not self.selected_image or not self.selected_image_cursor:
            return
        
        # 获取目标位置
        target_pos = target_cursor.position()
        current_pos = self.selected_image_cursor.position()
        
        # 如果位置相同，不需要移动
        if target_pos == current_pos or target_pos == current_pos + 1:
            return
        
        # 保存图片格式和原位置
        image_format = QTextImageFormat(self.selected_image)
        old_pos = self.selected_image_cursor.position()
        
        # **关键修复**：使用同一个光标对象执行所有操作，确保在编辑块中
        cursor = QTextCursor(self.document())
        
        # 开始编辑块
        cursor.beginEditBlock()
        
        # 1. 删除原位置的图片
        # **关键修复**：查找真正的图片字符位置（U+FFFC）
        # 从 old_pos 开始，向右查找最多2个字符，找到真正的图片字符
        real_image_pos = None
        has_paragraph_separator = False
        
        for offset in range(2):  # 检查当前位置和下一个位置
            check_pos = old_pos + offset
            cursor.setPosition(check_pos)
            
            # 向右移动一个字符并选中
            if cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1):
                selected_text = cursor.selectedText()
                char_format = cursor.charFormat()
                
                # 检查是否是真正的图片字符
                if char_format.isImageFormat() and selected_text == '\ufffc':
                    real_image_pos = check_pos
                    
                    # 检查图片字符前面是否有段落分隔符
                    if real_image_pos > 0:
                        cursor.setPosition(real_image_pos - 1)
                        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                        prev_text = cursor.selectedText()
                        prev_format = cursor.charFormat()
                        
                        if prev_format.isImageFormat() and prev_text == '\u2029':
                            has_paragraph_separator = True
                    
                    break
            
            # 清除选区，继续查找
            cursor.clearSelection()
        
        if real_image_pos is None:
            cursor.endEditBlock()
            return
        
        # **关键修复**：如果有段落分隔符，从段落分隔符位置开始删除
        delete_start_pos = real_image_pos - 1 if has_paragraph_separator else real_image_pos
        delete_count = 2 if has_paragraph_separator else 1
        
        # 移动到删除起始位置
        cursor.setPosition(delete_start_pos)
        
        # 向右选中需要删除的字符（段落分隔符 + 图片字符，或只有图片字符）
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, delete_count)
        
        # 删除选中的内容
        cursor.removeSelectedText()
        
        # 调整目标位置（如果删除位置在目标位置之前）
        adjusted_target_pos = target_pos
        if old_pos < target_pos:
            adjusted_target_pos = target_pos - 1
        
        # 2. 在新位置插入图片
        cursor.setPosition(adjusted_target_pos)
        cursor.insertImage(image_format)
        
        # 结束编辑块
        cursor.endEditBlock()
        
        # 更新选中状态
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        self.selected_image = image_format
        self.selected_image_cursor = cursor
        self.selected_image_rect = self.get_image_rect_at_cursor(cursor)
        
        # 刷新显示
        self.viewport().update()
    
    # 注释掉此函数以提升性能，需要调试时可以重新启用
    # def count_all_images(self):
    #     """统计文档中的所有图片数量和位置
    #     
    #     Returns:
    #         tuple: (图片数量, 图片位置列表)
    #     """
    #     count = 0
    #     positions = []
    #     cursor = QTextCursor(self.document())
    #     cursor.movePosition(QTextCursor.MoveOperation.Start)
    #     
    #     doc_length = self.document().characterCount()
    #     
    #     iteration = 0
    #     while not cursor.atEnd():
    #         iteration += 1
    #         # 保存当前位置
    #         current_pos = cursor.position()
    #         
    #         # 向右移动一个字符并选中
    #         move_success = cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
    #         
    #         if not move_success:
    #             break
    #         
    #         # 检查选中的字符格式
    #         char_format = cursor.charFormat()
    #         is_image = char_format.isImageFormat()
    #         
    #         # 获取选中的文本（图片字符）
    #         selected_text = cursor.selectedText()
    #         selected_text_repr = repr(selected_text)
    #         
    #         # **关键修复**：只统计真正的图片字符（U+FFFC），忽略段落分隔符（U+2029）
    #         # Qt在空行行首插入图片时，会插入两个字符：段落分隔符和图片字符
    #         # 我们只需要统计图片字符
    #         is_real_image = is_image and selected_text == '\ufffc'
    #         
    #         if is_real_image:
    #             count += 1
    #             positions.append(current_pos)
    #         
    #         # 清除选区后，光标会移动到选区的末尾（即 current_pos + 1）
    #         cursor.clearSelection()
    #         
    #         # 防止无限循环
    #         if iteration > doc_length + 100:
    #             break
    #     
    #     return count, positions
    

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
    
    def __init__(self, note_manager=None):
        super().__init__()
        self.math_renderer = MathRenderer()
        self.note_manager = note_manager
        self.current_note_id = None  # 当前编辑的笔记ID
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
        
        # 设置字体：优先使用系统默认字体，避免缺失字体导致Qt在启动时耗时做字体别名填充
        font = self.font()
        try:
            font.setPointSize(14)
        except Exception:
            pass
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
        
        # 标题样式（平铺在格式菜单下）
        title_action = QAction("标题", self)
        title_action.triggered.connect(lambda: self.apply_heading(1))
        format_menu.addAction(title_action)
        
        heading_action = QAction("小标题", self)
        heading_action.triggered.connect(lambda: self.apply_heading(2))
        format_menu.addAction(heading_action)
        
        subheading_action = QAction("副标题", self)
        subheading_action.triggered.connect(lambda: self.apply_heading(3))
        format_menu.addAction(subheading_action)
        
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
        """自动将第一行格式化为标题格式（28号字体），其他行为正文格式"""
        # 获取文档
        document = self.text_edit.document()
        if document.isEmpty():
            return
        
        # 获取当前光标
        current_cursor = self.text_edit.textCursor()
        
        # **关键修复**：如果当前有选区（用户正在拖选），不要执行格式化
        # 因为格式化操作可能会影响选区内容，导致图片等特殊字符丢失
        if current_cursor.hasSelection():
            return
        
        current_block = current_cursor.block()
        current_block_number = current_block.blockNumber()
        
        # 获取第一个文本块（第一行）
        first_block = document.firstBlock()
        if not first_block.isValid():
            return
        
        # 只在必要时格式化第一行
        first_cursor = QTextCursor(first_block)
        first_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        
        # 检查第一行是否已经是标题格式
        char_fmt = first_cursor.charFormat()
        current_size = char_fmt.fontPointSize()
        
        # 如果第一行不是标题格式（28号字体），则应用格式
        if current_size != 28:
            # 阻止信号，避免递归
            self.text_edit.blockSignals(True)
            
            # 设置字符格式
            new_char_fmt = QTextCharFormat()
            new_char_fmt.setFontPointSize(28)
            new_char_fmt.setFontWeight(QFont.Weight.Bold)
            
            # 应用格式到第一行
            first_cursor.mergeCharFormat(new_char_fmt)
            
            # 恢复信号
            self.text_edit.blockSignals(False)
        
        # 如果当前光标在第二行或之后，确保使用正文格式
        if current_block_number >= 1:
            # 获取当前字符格式
            current_char_fmt = current_cursor.charFormat()
            current_font_size = current_char_fmt.fontPointSize()
            
            # 只有当字体不是14号时才修改
            if current_font_size != 14:
                # 设置正文格式
                body_fmt = QTextCharFormat()
                body_fmt.setFontPointSize(14)
                body_fmt.setFontWeight(QFont.Weight.Normal)
                
                # 设置当前输入格式
                self.text_edit.setCurrentCharFormat(body_fmt)
    
    # 格式化方法
    def apply_heading(self, level):
        """应用标题格式"""
        cursor = self.text_edit.textCursor()
        
        # 设置块格式
        block_fmt = QTextBlockFormat()
        
        # 设置字符格式
        char_fmt = QTextCharFormat()
        char_fmt.setFontWeight(QFont.Weight.Bold)
        
        if level == 1:  # 标题（首行标题格式）
            char_fmt.setFontPointSize(28)
        elif level == 2:  # 小标题
            char_fmt.setFontPointSize(22)
        elif level == 3:  # 副标题
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
        """插入附件 - 弹出文件选择对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择附件", "", "所有文件 (*.*)"
        )
        
        if file_path:
            # 调用内部方法处理附件
            self._insert_attachment_with_path(file_path)
    
    def rerender_formulas(self):
        """重新渲染文档中的所有数学公式"""
        # **关键修复**：现在公式是通过 insertImage() 插入的真正图片字符（U+FFFC）
        # 元数据存储在图片名称中（格式：data:image/png;base64,...|||MATH:type:code）
        # 需要遍历文档中的所有图片字符，找到公式并重新渲染
        
        cursor = QTextCursor(self.text_edit.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        
        # 收集所有需要重新渲染的公式
        formulas_to_rerender = []  # [(position, formula_type, code, width, height), ...]
        
        while not cursor.atEnd():
            # 保存当前位置
            current_pos = cursor.position()
            
            # 向右移动一个字符并选中
            if cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor):
                char_format = cursor.charFormat()
                selected_text = cursor.selectedText()
                
                # 检查是否是真正的图片字符
                if char_format.isImageFormat() and selected_text == '\ufffc':
                    img_format = char_format.toImageFormat()
                    image_name = img_format.name()
                    
                    # 检查是否是公式（包含 |||MATH: 分隔符）
                    if '|||MATH:' in image_name:
                        parts = image_name.split('|||', 1)
                        if len(parts) == 2:
                            metadata = parts[1]  # MATH:type:code
                            
                            # 解析元数据
                            if metadata.startswith('MATH:'):
                                metadata_parts = metadata[5:].split(':', 1)  # 去掉 'MATH:' 前缀
                                if len(metadata_parts) == 2:
                                    formula_type = metadata_parts[0]
                                    escaped_code = metadata_parts[1]
                                    # 反转义HTML实体
                                    code = html.unescape(escaped_code)
                                    
                                    # 保存公式信息
                                    formulas_to_rerender.append((
                                        current_pos,
                                        formula_type,
                                        code,
                                        img_format.width(),
                                        img_format.height()
                                    ))
                
                # 清除选区
                cursor.clearSelection()
            else:
                break
        
        # 如果没有公式需要重新渲染，直接返回
        if not formulas_to_rerender:
            return
        
        # 开始编辑块
        edit_cursor = QTextCursor(self.text_edit.document())
        edit_cursor.beginEditBlock()
        
        # 从后往前处理，避免位置偏移
        for pos, formula_type, code, width, height in reversed(formulas_to_rerender):
            # 重新渲染公式
            image_data = self.math_renderer.render(code, formula_type)
            
            if image_data and not image_data.isNull():
                try:
                    from PIL import Image as PILImage
                    import io
                    
                    # 将 QImage 转换为 PIL Image
                    new_width = image_data.width()
                    new_height = image_data.height()
                    
                    image_data = image_data.convertToFormat(QImage.Format.Format_RGBA8888)
                    ptr = image_data.constBits()
                    ptr.setsize(image_data.sizeInBytes())
                    
                    pil_image = PILImage.frombytes('RGBA', (new_width, new_height), bytes(ptr), 'raw', 'RGBA', 0, 1)
                    
                    if pil_image.mode == 'RGBA':
                        background = PILImage.new('RGB', pil_image.size, (255, 255, 255))
                        background.paste(pil_image, mask=pil_image.split()[3])
                        pil_image = background
                    
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format='PNG', optimize=True)
                    image_bytes = buffer.getvalue()
                    
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    
                    # 重新组合图片名称（保留元数据）
                    escaped_code = html.escape(code)
                    new_image_name = f"data:image/png;base64,{image_base64}|||MATH:{formula_type}:{escaped_code}"
                    
                    # 删除旧图片
                    edit_cursor.setPosition(pos)
                    edit_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                    edit_cursor.removeSelectedText()
                    
                    # 插入新图片（保持原尺寸）
                    new_format = QTextImageFormat()
                    new_format.setName(new_image_name)
                    new_format.setWidth(width)
                    new_format.setHeight(height)
                    # 设置垂直对齐方式为AlignBaseline，使图片底部与文本基线对齐
                    new_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignBaseline)
                    edit_cursor.insertImage(new_format)
                    
                except Exception as e:
                    print(f"重新渲染公式失败: {e}")
                    import traceback
                    traceback.print_exc()
        
        # 结束编辑块
        edit_cursor.endEditBlock()
    
    def insert_image_to_editor(self, image):
        """插入图片到编辑器"""
        # 检查图片是否有效
        if image is None or image.isNull():
            print("错误：图片无效")
            return
        
        # 限制图片大小
        max_width = 800
        
        if image.width() > max_width:
            image = image.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
        
        # 再次检查缩放后的图片
        if image.isNull():
            print("错误：图片缩放后无效")
            return
        
        try:
            from PIL import Image as PILImage
            import io
            
            # 将 QImage 转换为 PIL Image，完全避免使用 Qt 的 save 方法
            # 获取图片的宽度、高度和格式
            width = image.width()
            height = image.height()
            
            # 转换为 RGBA8888 格式（PIL 兼容）
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            
            # 获取图片的原始字节数据
            ptr = image.constBits()
            ptr.setsize(image.sizeInBytes())
            
            # 使用 PIL 从原始字节创建图片
            pil_image = PILImage.frombytes('RGBA', (width, height), bytes(ptr), 'raw', 'RGBA', 0, 1)
            
            # 转换为 RGB（去除 alpha 通道，PNG 更小）
            if pil_image.mode == 'RGBA':
                # 创建白色背景
                background = PILImage.new('RGB', pil_image.size, (255, 255, 255))
                background.paste(pil_image, mask=pil_image.split()[3])  # 使用 alpha 通道作为 mask
                pil_image = background
            
            # 使用 PIL 保存为 PNG 格式到内存
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG', optimize=True)
            image_bytes = buffer.getvalue()
            
            # 转换为 base64
            image_data = base64.b64encode(image_bytes).decode('utf-8')
            
            # 生成唯一的图片名称
            image_name = f"image_{uuid.uuid4().hex[:8]}.png"
            
            # 获取光标
            cursor = self.text_edit.textCursor()
            
            # 使用QTextImageFormat插入图片（更可靠的方式）
            image_format = QTextImageFormat()
            image_format.setName(f"data:image/png;base64,{image_data}")
            image_format.setWidth(width)
            image_format.setHeight(height)
            # 设置垂直对齐方式为AlignBaseline，使图片底部与文本基线对齐
            image_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignBaseline)
            
            # 插入图片
            cursor.insertImage(image_format)
            
        except Exception as e:
            print(f"插入图片时发生错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _insert_attachment_with_path(self, file_path):
        """插入附件链接 - 使用附件管理器加密存储"""
        try:
            import os
            
            # 检查是否有note_manager和当前笔记ID
            if not self.note_manager or not self.current_note_id:
                QMessageBox.warning(self, "错误", "无法添加附件：笔记未保存")
                return
            
            # 获取文件名和大小
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # 格式化文件大小
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            
            # 使用附件管理器添加附件（复制并加密）
            success, message, attachment_id = self.note_manager.attachment_manager.add_attachment(
                file_path, self.current_note_id
            )
            
            if not success:
                QMessageBox.warning(self, "添加附件失败", message)
                return
            
            # 获取光标
            cursor = self.text_edit.textCursor()
            
            # 创建附件HTML（使用attachment_id作为链接）
            # 使用自定义协议 attachment:// 来标识这是一个加密附件
            attachment_url = f"attachment://{attachment_id}"
            
            # 创建附件HTML（带样式的链接）
            attachment_html = f'''
            <div style="background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; padding: 8px; margin: 4px 0; display: inline-block;">
                <span style="font-size: 16px;">📎</span>
                <a href="{attachment_url}" style="color: #0066cc; text-decoration: none; margin: 0 8px;" data-attachment-id="{attachment_id}">{file_name}</a>
                <span style="color: #666; font-size: 12px;">({size_str})</span>
            </div>
            '''
            
            cursor.insertHtml(attachment_html)
            cursor.insertBlock()  # 添加换行
            
            print(f"成功插入附件: {file_name} ({size_str}), ID: {attachment_id}")
            QMessageBox.information(self, "成功", f"{message}\n文件已加密保存")
            
        except Exception as e:
            print(f"插入附件时发生错误: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"插入附件失败: {str(e)}")
        
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
        
        if image_data and not image_data.isNull():
            try:
                from PIL import Image as PILImage
                import io
                
                # 将 QImage 转换为 PIL Image，完全避免使用 Qt 的 save 方法
                width = image_data.width()
                height = image_data.height()
                
                # 转换为 RGBA8888 格式（PIL 兼容）
                image_data = image_data.convertToFormat(QImage.Format.Format_RGBA8888)
                
                # 获取图片的原始字节数据
                ptr = image_data.constBits()
                ptr.setsize(image_data.sizeInBytes())
                
                # 使用 PIL 从原始字节创建图片
                pil_image = PILImage.frombytes('RGBA', (width, height), bytes(ptr), 'raw', 'RGBA', 0, 1)
                
                # 转换为 RGB（去除 alpha 通道）
                if pil_image.mode == 'RGBA':
                    background = PILImage.new('RGB', pil_image.size, (255, 255, 255))
                    background.paste(pil_image, mask=pil_image.split()[3])
                    pil_image = background
                
                # 使用 PIL 保存为 PNG 格式到内存
                buffer = io.BytesIO()
                pil_image.save(buffer, format='PNG', optimize=True)
                image_bytes = buffer.getvalue()
                
                # 转换为 base64
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # **关键修复**：使用 insertImage() 而不是 insertHtml()
                # 这样公式会成为真正的图片字符（U+FFFC），可以被点击选中
                # 在图片名称中编码公式元数据（格式: data:image/png;base64,...|||MATH:type:code）
                import html
                escaped_code = html.escape(code)
                # 使用 ||| 作为分隔符，将元数据附加到图片名称后面
                image_name = f"data:image/png;base64,{image_base64}|||MATH:{formula_type}:{escaped_code}"
                
                # 使用 QTextImageFormat 插入图片
                image_format = QTextImageFormat()
                image_format.setName(image_name)
                image_format.setWidth(width)
                image_format.setHeight(height)
                # 设置垂直对齐方式为AlignBaseline，使公式底部与文本基线对齐
                image_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignBaseline)
                
                cursor.insertImage(image_format)
                
            except Exception as e:
                print(f"插入公式时发生错误: {e}")
                import traceback
                traceback.print_exc()
                # 如果出错，插入原始代码
                if formula_type == 'latex':
                    cursor.insertText(f"$${code}$$")
                else:
                    cursor.insertText(f"[MathML: {code[:50]}...]")
        else:
            # 如果渲染失败，插入原始代码
            if formula_type == 'latex':
                cursor.insertText(f"$${code}$$")
            else:
                cursor.insertText(f"[MathML: {code[:50]}...]")
    
    def edit_math_formula(self, code, formula_type, image_cursor, image_format):
        """编辑已存在的数学公式
        
        Args:
            code: 公式代码
            formula_type: 公式类型（'latex' 或 'mathml'）
            image_cursor: 图片字符的光标位置
            image_format: 图片格式
        """
        # 根据公式类型弹出对应的编辑对话框
        if formula_type == 'latex':
            dialog = LatexInputDialog(self)
            # 设置对话框中的初始内容为原公式代码
            dialog.input_edit.setPlainText(code)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_code = dialog.get_latex()
                if new_code and new_code != code:
                    # 用户修改了公式，更新公式图片
                    self._update_formula_image(new_code, formula_type, image_cursor, image_format)
        
        elif formula_type == 'mathml':
            dialog = MathMLInputDialog(self)
            # 设置对话框中的初始内容为原公式代码
            dialog.input_edit.setPlainText(code)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_code = dialog.get_mathml()
                if new_code and new_code != code:
                    # 用户修改了公式，更新公式图片
                    self._update_formula_image(new_code, formula_type, image_cursor, image_format)
    
    def _update_formula_image(self, code, formula_type, image_cursor, old_image_format):
        """更新公式图片
        
        Args:
            code: 新的公式代码
            formula_type: 公式类型
            image_cursor: 图片字符的光标位置
            old_image_format: 旧的图片格式
        """
        # 渲染新公式为图片
        image_data = self.math_renderer.render(code, formula_type)
        
        if image_data and not image_data.isNull():
            try:
                from PIL import Image as PILImage
                import io
                
                # 将 QImage 转换为 PIL Image
                width = image_data.width()
                height = image_data.height()
                
                image_data = image_data.convertToFormat(QImage.Format.Format_RGBA8888)
                ptr = image_data.constBits()
                ptr.setsize(image_data.sizeInBytes())
                
                pil_image = PILImage.frombytes('RGBA', (width, height), bytes(ptr), 'raw', 'RGBA', 0, 1)
                
                if pil_image.mode == 'RGBA':
                    background = PILImage.new('RGB', pil_image.size, (255, 255, 255))
                    background.paste(pil_image, mask=pil_image.split()[3])
                    pil_image = background
                
                buffer = io.BytesIO()
                pil_image.save(buffer, format='PNG', optimize=True)
                image_bytes = buffer.getvalue()
                
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # 创建新的图片名称（包含元数据）
                escaped_code = html.escape(code)
                new_image_name = f"data:image/png;base64,{image_base64}|||MATH:{formula_type}:{escaped_code}"
                
                # 查找真正的图片字符位置
                old_pos = image_cursor.position()
                cursor = QTextCursor(self.text_edit.document())
                real_image_pos = None
                
                for offset in range(2):
                    check_pos = old_pos + offset
                    cursor.setPosition(check_pos)
                    
                    if cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1):
                        selected_text = cursor.selectedText()
                        char_format = cursor.charFormat()
                        
                        if char_format.isImageFormat() and selected_text == '\ufffc':
                            real_image_pos = check_pos
                            break
                    
                    cursor.clearSelection()
                
                if real_image_pos is None:
                    print("错误：找不到图片字符")
                    return
                
                # 开始编辑块
                cursor.beginEditBlock()
                
                # 删除旧图片
                cursor.setPosition(real_image_pos)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                cursor.removeSelectedText()
                
                # 插入新图片（保持原尺寸或使用新尺寸）
                new_format = QTextImageFormat()
                new_format.setName(new_image_name)
                # 保持原图片的尺寸
                new_format.setWidth(old_image_format.width())
                new_format.setHeight(old_image_format.height())
                new_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignBaseline)
                cursor.insertImage(new_format)
                
                cursor.endEditBlock()
                
                print(f"成功更新公式: {width}x{height}")
                
                # 取消选中状态
                if hasattr(self.text_edit, 'selected_image'):
                    self.text_edit.selected_image = None
                    self.text_edit.selected_image_rect = None
                    self.text_edit.selected_image_cursor = None
                    self.text_edit.viewport().update()
                
            except Exception as e:
                print(f"更新公式时发生错误: {e}")
                import traceback
                traceback.print_exc()
                QMessageBox.warning(self, "错误", f"更新公式失败: {str(e)}")
        else:
            QMessageBox.warning(self, "错误", "公式渲染失败")


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
            ("次方", r"x^{2}"),
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
            # 使用系统默认等宽字体栈，避免引用不存在的字体导致Qt做字体回退带来额外耗时
            self.preview.setHtml(
                f"<p style='font-family: ui-monospace, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace;'>${latex_code}$</p>"
            )
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
            ("次方", "<math><msup><mi>x</mi><mn>2</mn></msup></math>"),
            ("求和", "<math><munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>n</mi></munderover><msub><mi>x</mi><mi>i</mi></msub></math>"),
            ("积分", "<math><msubsup><mo>∫</mo><mi>a</mi><mi>b</mi></msubsup><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mi>d</mi><mi>x</mi></math>"),
            ("矩阵", "<math><mfenced open='(' close=')'><mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi></mtd><mtd><mi>d</mi></mtd></mtr></mtable></mfenced></math>"),
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
