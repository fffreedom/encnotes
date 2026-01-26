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
    QSpinBox, QDialogButtonBox, QColorDialog
)
from PyQt6.QtCore import Qt, QSize, QUrl, QMimeData, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import (
    QTextCursor, QFont, QTextCharFormat, QColor, QAction,
    QTextBlockFormat, QTextListFormat, QTextTableFormat,
    QTextFrameFormat, QTextLength, QImage, QPixmap, QClipboard,
    QTextImageFormat, QTextFormat, QTextDocument
)

from math_renderer import MathRenderer
import os
import uuid
from pathlib import Path
import base64
import html
import re
import logging

logger = logging.getLogger(__name__)


def _select_range(cursor: QTextCursor, start: int, end: int) -> bool:
    """统一的选中字符范围的函数，使用movePosition方式。
    
    Args:
        cursor: QTextCursor对象
        start: 起始位置
        end: 结束位置（不包含）
        
    Returns:
        是否成功选中范围
    """
    cursor.setPosition(start)
    if end <= start:
        return False
    count = end - start
    return cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, count)


def _select_char_at(cursor: QTextCursor, position: int) -> bool:
    """选中指定位置的单个字符（使用movePosition方式）。

    Args:
        cursor: QTextCursor对象（会被修改）
        position: 字符位置

    Returns:
        是否成功选中字符
    """
    cursor.setPosition(position)
    return cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)


def _selected_char_format(
    doc: QTextDocument,
    p: int,
) -> QTextCharFormat | None:
    doc_len = doc.characterCount()
    if doc_len <= 0 or p < 0 or p > doc_len - 1:
        return None

    c0 = QTextCursor(doc)
    if not _select_char_at(c0, p):
        return None

    # 输出选中的字符（调试用）
    selected_char = c0.selectedText()
    print(f"[DEBUG] 位置 {p} 选中的字符: '{selected_char}' (Unicode: {ord(selected_char) if selected_char else 'N/A'})")

    return c0.charFormat()


def _get_char_at(doc: QTextDocument, position: int) -> str:
    """获取文档中指定位置的字符（全局辅助函数）。
    
    Args:
        doc: 文档对象
        position: 字符位置
        
    Returns:
        该位置的字符，如果无法获取则返回空字符串
    """
    c = QTextCursor(doc)
    if not _select_char_at(c, position):
        return ""
    return c.selectedText() or ""


def _is_marked_at(
        doc: QTextDocument,
        p: int,
        tag_prop: int,
        tag_value: str
) -> bool:
    """检查指定位置的字符是否具有指定的标记属性。

    Args:
        doc: 文档对象
        p: 要检查的位置
        tag_prop: 标记属性ID
        tag_value: 标记属性值

    Returns:
        如果该位置字符具有指定标记则返回 True，否则返回 False
    """
    cf0 = _selected_char_format(doc, p)
    return bool(cf0) and cf0.hasProperty(tag_prop) and cf0.property(tag_prop) == tag_value


def _dump_doc_chars(doc: QTextDocument, start: int, end: int) -> str:
    """输出文档指定范围的每个字符及其 codepoint，便于定位不可见字符。"""
    try:
        start = max(0, start)
        end = min(max(0, int(doc.characterCount()) - 1), end)
        items = []
        for i in range(start, end + 1):
            ch = _get_char_at(doc, i)
            if ch == "":
                ch = "∅"
            cp = " ".join([f"U+{ord(x):04X}" for x in ch])
            show = ch.encode("unicode_escape", errors="backslashreplace").decode("ascii")
            show = show.replace("\\u200b", "<ZWSP>").replace("\\u2029", "<PSEP>")
            show = show.replace("\\n", "<LF>").replace("\\r", "<CR>")
            items.append(f"{i}:{show}({cp})")
        return " ".join(items)
    except Exception as e:
        return f"<dump_failed:{e}>"


def _dump_selection_chars(doc: QTextDocument, cur: QTextCursor) -> str:
    """输出 QTextCursor 当前选区的逐字符信息（依赖 doc）。"""
    try:
        s = cur.selectionStart()
        e = cur.selectionEnd()
        if e <= s:
            return "<empty>"
        items = []
        for i in range(s, e):
            ch = _get_char_at(doc, i)
            if ch == "":
                ch = "∅"
            cp = " ".join([f"U+{ord(x):04X}" for x in ch])
            show = ch.encode("unicode_escape", errors="backslashreplace").decode("ascii")
            show = show.replace("\\u200b", "<ZWSP>").replace("\\u2029", "<PSEP>")
            show = show.replace("\\n", "<LF>").replace("\\r", "<CR>")
            items.append(f"{i}:{show}({cp})")
        return " ".join(items)
    except Exception as e:
        return f"<sel_dump_failed:{e}>"

def _find_marked_span(
    doc: QTextDocument,
    pos: int,
    tag_prop: int,
    tag_value: str,
) -> tuple[int, int] | None:
    """返回以 pos 为锚点的连续标记范围 (start, end_exclusive)。

    注意：Qt 的 `QTextCursor.charFormat()` 在"无选区"时返回的是插入点格式，
    不一定等价于该位置字符本身的格式。这里统一采用"先选中 1 个字符再取格式"。

    约定：这里的 pos 只可能是"标记范围起点 start_pos"或"标记范围末端 end_pos"。
    因此优先把 pos 当作 start_pos 向右扩展；若失败再把 pos 当作 end_pos 向左扩展。
    """
    try:
        if not tag_value:
            return None

        doc_len = int(doc.characterCount())
        if doc_len <= 0:
            return None

        max_pos = doc_len - 1

        # 1) 尝试把 pos 当作 start_pos：要求 pos 本身是标记，且 pos-1 不是标记
        if _is_marked_at(doc, pos, tag_prop, tag_value) and \
           (pos <= 0 or not _is_marked_at(doc, pos - 1, tag_prop, tag_value)):
            start = pos
            end_inclusive = pos
            while end_inclusive < max_pos and _is_marked_at(doc, end_inclusive + 1, tag_prop, tag_value):
                end_inclusive += 1
            return (start, end_inclusive + 1)

        # 2) 尝试把 pos 当作 end_pos（即 end_exclusive）：要求 pos-1 是标记，且 pos 本身不是标记
        #    这样 pos 落在标记范围的"右开端点"上（例如插入后 cursor.position()）。
        if pos > 0 and \
           _is_marked_at(doc, pos - 1, tag_prop, tag_value) and \
           not _is_marked_at(doc, pos, tag_prop, tag_value):
            end_inclusive = pos - 1
            start = end_inclusive
            while start > 0 and _is_marked_at(doc, start - 1, tag_prop, tag_value):
                start -= 1
            return (start, end_inclusive + 1)

        return None
    except Exception:
        return None


def _safe_set_cursor_position(doc: QTextDocument, cur: QTextCursor, p: int, where: str) -> None:
    """调试用：记录 setPosition 调用点，便于定位 Qt 的 out-of-range stderr 输出来源。"""
    try:
        try:
            _dl = int(doc.characterCount())
        except Exception:
            _dl = -1
        logger.debug("[cursor-setpos] where=%s pos=%s doc_len=%s", where, p, _dl)
        cur.setPosition(p)
    except Exception as e:
        logger.debug("[cursor-setpos][py-exc] where=%s pos=%s doc_len=%s err=%s", where, p, _dl, e)

class PasteImageTextEdit(QTextEdit):
    """支持粘贴图片的文本编辑器"""

    # 附件整体的特殊标记：附件文本会被解析为若干字符
    # 我们用该标记覆盖"附件展示块"对应的文本范围，确保删除时按整体删除
    ATTACHMENT_TAG_PREFIX = "__encnotes_attachment__"
    ATTACHMENT_TAG_PROP = QTextFormat.Property.UserProperty + 1000
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_editor = parent
        self.setMouseTracking(True)

        # 生成唯一tag名（避免不同编辑器实例冲突）
        self._attachment_tag_name = f"{self.ATTACHMENT_TAG_PREFIX}{uuid.uuid4().hex}"
        self._init_attachment_tag_style()

        
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
        self.mouse_pressed = False  # 跟踪鼠标按钮是否被按下
        
        # 表格选中相关
        self.selected_table = None  # 当前选中的表格
        self.selected_table_cursor = None  # 表格的光标位置
        self.table_select_handle_size = 20  # 表格全选图标的大小
        
        # 边界检测阈值
        self.handle_size = 8
        
        # 监听滚动事件
        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self.on_scroll)

    def _init_attachment_tag_style(self):
        """初始化附件 tag 的样式（只用于标记范围，不改变显示）"""
        try:
            fmt = QTextCharFormat()
            fmt.setProperty(self.ATTACHMENT_TAG_PROP, self._attachment_tag_name)
            # 不改变前景/背景/字体等显示，仅作为范围标记
            self.document().addResource(
                QTextDocument.ResourceType.UserResource,
                QUrl(self._attachment_tag_name),
                QByteArray(),
            )

        except Exception:
            # 标记失败不应影响编辑器可用性
            pass

    def _cursor_is_in_attachment_block(self, cursor: QTextCursor) -> bool:
        """判断光标是否位于附件块的字符范围内（通过 charFormat 的 anchor 属性不可靠，所以用自定义 property 标识）"""
        if not cursor:
            return False

        # 若有选区，任一端点在附件内都视为在附件内
        positions = [cursor.position()]
        if cursor.hasSelection():
            positions.append(cursor.selectionStart())
            positions.append(cursor.selectionEnd())

        doc = self.document()
        for pos in positions:
            if _is_marked_at(doc, pos, self.ATTACHMENT_TAG_PROP, self._attachment_tag_name):
                return True
        return False

    def _select_whole_attachment_span(self, cursor: QTextCursor) -> QTextCursor | None:
        """从光标附近扩展选区，选中整个附件块（通过连续的同一标记范围）。

        这里的"找范围"逻辑统一复用 `_find_marked_span_around()`，确保与其他标记扫描一致。
        """
        if not cursor:
            return None

        doc = self.document()
        pos = cursor.position()
        try:
            span = _find_marked_span(doc, pos, self.ATTACHMENT_TAG_PROP, self._attachment_tag_name)
            # if span is None and pos - 1 >= 0:
            #     span = _find_marked_span_around(doc, pos - 1, self.ATTACHMENT_TAG_PROP, tag_value)
        except Exception:
            span = None

        if span is None:
            return None

        start, end_exclusive = span
        if end_exclusive <= start:
            return None

        try:
            logger.debug(
                "[attachment-select] cursor_pos=%s span=(%s,%s)",
                pos,
                start,
                end_exclusive,
            )
        except Exception:
            pass

        sel = QTextCursor(doc)
        _select_range(sel, start, end_exclusive)
        return sel

    
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
        from PyQt6.QtGui import QTextLength
        
        try:
            # 获取表格格式
            table_format = table.format()
            table_width_length = table_format.width()
            
            # 获取左上角单元格（第一行第一列）
            top_left_cell = table.cellAt(0, 0)
            if not top_left_cell.isValid():
                return None
            
            # 获取右下角单元格（最后一行最后一列）
            bottom_right_cell = table.cellAt(table.rows() - 1, table.columns() - 1)
            if not bottom_right_cell.isValid():
                return None
            
            # 获取左上角单元格的光标矩形（第一个字符位置）
            top_left_cursor = top_left_cell.firstCursorPosition()
            top_left_rect = self.cursorRect(top_left_cursor)
            
            # 获取右下角单元格的光标矩形（最后一个字符位置）
            bottom_right_cursor = bottom_right_cell.lastCursorPosition()
            bottom_right_rect = self.cursorRect(bottom_right_cursor)
            
            # 计算表格边界
            border_width = table_format.border()
            cell_padding = table_format.cellPadding()
            
            left = top_left_rect.left() - border_width - cell_padding
            top = top_left_rect.top() - border_width - cell_padding
            bottom = bottom_right_rect.bottom() + border_width + cell_padding
            
            # 使用表格格式的宽度信息计算右边界
            document = self.document()
            doc_layout = document.documentLayout()
            doc_size = doc_layout.documentSize()
            doc_width = doc_size.width()
            
            # 获取文档的根框架和边距
            root_frame = document.rootFrame()
            root_frame_format = root_frame.frameFormat()
            doc_left_margin = root_frame_format.leftMargin()
            doc_right_margin = root_frame_format.rightMargin()
            
            # 计算内容区域的实际宽度（表格100%宽度的参考）
            content_width = doc_width - doc_left_margin - doc_right_margin
            
            # 根据表格宽度类型计算实际宽度
            if table_width_length.type() == QTextLength.Type.PercentageLength:
                # 百分比宽度 - 相对于内容区域宽度
                percentage = table_width_length.rawValue()
                table_total_width = content_width * percentage / 100.0
            elif table_width_length.type() == QTextLength.Type.FixedLength:
                # 固定宽度
                table_total_width = table_width_length.rawValue()
            else:
                # 可变宽度，使用内容区域宽度
                table_total_width = content_width
            
            # 计算右边界：左边界 + 表格总宽度 - cell_padding
            # 需要减去cell_padding的原因：
            # 1. left的计算中减去了cell_padding，将位置从内容区域回退到了单元格边框内侧
            # 2. table_total_width是Qt计算的表格100%宽度，这个宽度的右边界也是到最后一列单元格边框内侧
            # 3. 因此需要减去一个cell_padding来保持对称性
            right = left + table_total_width - cell_padding
            
            # 创建矩形
            table_rect = QRectF(left, top, right - left, bottom - top)
            
            return table_rect
            
        except Exception as e:
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

                # 如果该附件此前被"延迟删除"挪进回收站，这里自动尝试恢复，确保打开不受影响
                try:
                    note_id = getattr(self.parent_editor, 'current_note_id', None)
                    if note_id:
                        attachment_manager.restore_deferred_attachment(attachment_id, note_id)
                except Exception:
                    pass

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
            _select_char_at(cursor, cursor.position())
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
        _select_char_at(temp_cursor, temp_cursor.position())
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
    
    def focusInEvent(self, event):
        """焦点获得事件"""
        # 如果当前没有笔记，阻止获得焦点
        if hasattr(self, 'parent_editor') and self.parent_editor:
            if not getattr(self.parent_editor, 'current_note_id', None):
                event.ignore()
                return
        
        super().focusInEvent(event)
        
        # 如果光标在第一行且第一行为空，恢复标题格式
        cursor = self.textCursor()
        block_num = cursor.block().blockNumber()
        block_text = cursor.block().text()
        
        if block_num == 0:
            if block_text == "" or block_text == "\u200B":
                # 设置标题格式
                char_fmt = QTextCharFormat()
                char_fmt.setFontPointSize(28)
                char_fmt.setFontWeight(QFont.Weight.Bold)
                self.setCurrentCharFormat(char_fmt)

    def _handle_anchor_click(self, event) -> bool:
        """处理附件链接点击

        Returns:
            如果处理了链接点击返回True，否则返回False
        """
        # 使用 anchorAt 方法精确判断是否点击在链接上
        anchor_href = self.anchorAt(event.pos())
        if anchor_href:
            self.open_attachment(anchor_href)
            event.accept()
            return True
        return False

    def _should_ignore_mouse_event(self) -> bool:
        """检查是否应该忽略鼠标事件（当前没有笔记时）
        
        Returns:
            如果应该忽略返回True，否则返回False
        """
        if hasattr(self, 'parent_editor') and self.parent_editor:
            if not getattr(self.parent_editor, 'current_note_id', None):
                return True
        return False

    def _restore_cursor_visibility(self):
        """恢复光标显示（如果之前被隐藏）"""
        if self.cursorWidth() == 0:
            self.setCursorWidth(1)

    def _handle_table_border_click(self, table, cursor, event) -> bool:
        """处理表格边框点击（选中整个表格）
        
        Returns:
            如果处理了边框点击返回True，否则返回False
        """
        if not self.is_click_on_table_border(event.pos(), table):
            return False
        
        # 点击了边框，选中整个表格
        self.selected_table = table
        self.selected_table_cursor = cursor
        
        # 取消图片选中
        if self.selected_image:
            self.selected_image = None
            self.selected_image_rect = None
            self.selected_image_cursor = None
        
        # 将光标移动到表格外部（表格之后的位置），退出单元格编辑状态
        # 这样在按删除键时，currentTable()会返回None，从而删除整个表格
        clear_cursor = QTextCursor(self.document())
        table_end = table.lastPosition()
        clear_cursor.setPosition(table_end + 1)
        self.setTextCursor(clear_cursor)
        
        self.viewport().update()
        event.accept()
        return True

    def _handle_table_content_click(self, event):
        """处理表格内容点击（清除表格选中状态）"""
        if self.selected_table:
            self.selected_table = None
            self.selected_table_cursor = None
            self.viewport().update()

    def _clear_table_selection(self):
        """清除表格选中状态"""
        if self.selected_table:
            self.selected_table = None
            self.selected_table_cursor = None
            self.viewport().update()

    def _handle_image_resize_handle_click(self, event) -> bool:
        """处理图片缩放控制点点击
        
        Returns:
            如果处理了控制点点击返回True，否则返回False
        """
        if not self.selected_image:
            return False
        
        handle = self.get_handle_at_pos(event.pos())
        if handle:
            # 开始缩放
            self.resizing = True
            self.resize_handle = handle
            self.resize_start_pos = event.pos()
            self.resize_start_size = (self.selected_image.width(), self.selected_image.height())
            event.accept()
            return True
        return False

    def _handle_image_drag_click(self, event) -> bool:
        """处理图片拖动点击
        
        Returns:
            如果处理了拖动点击返回True，否则返回False
        """
        if not self.selected_image:
            return False
        
        # 检查是否点击了图片中心区域（用于拖动移动）
        if self.selected_image_rect and self.selected_image_rect.contains(event.pos()):
            # 开始拖动
            self.dragging = True
            self.drag_start_pos = event.pos()
            self.drag_start_cursor_pos = self.selected_image_cursor.position()
            event.accept()
            return True
        return False

    def _find_real_image_char_position(self, image_cursor) -> int | None:
        """查找真正的图片字符位置（跳过段落分隔符）
        
        Args:
            image_cursor: 指向图片附近的光标
            
        Returns:
            图片字符的位置，如果找不到返回None
        """
        cursor = QTextCursor(image_cursor)
        
        # 从当前位置开始，向右查找最多2个字符，找到真正的图片字符
        for offset in range(2):
            check_pos = image_cursor.position() + offset
            cursor.setPosition(check_pos)
            
            # 向右移动一个字符并选中
            if _select_char_at(cursor, check_pos):
                selected_text = cursor.selectedText()
                char_format = cursor.charFormat()
                
                # 检查是否是真正的图片字符
                if char_format.isImageFormat() and selected_text == '\ufffc':
                    return check_pos
            
            # 清除选区，继续查找
            cursor.clearSelection()
        
        return None

    def _select_image_char(self, image_cursor):
        """选中图片字符（用于删除等操作）
        
        Args:
            image_cursor: 指向图片附近的光标
        """
        cursor = QTextCursor(image_cursor)
        real_image_pos = self._find_real_image_char_position(image_cursor)
        
        if real_image_pos is not None:
            # 选中真正的图片字符
            _select_char_at(cursor, real_image_pos)
            self.setTextCursor(cursor)
        else:
            # 如果找不到真正的图片字符，使用原来的逻辑
            cursor = QTextCursor(image_cursor)
            _select_char_at(cursor, cursor.position())
            self.setTextCursor(cursor)

    def _handle_image_click(self, event) -> bool:
        """处理图片点击（选中图片）
        
        Returns:
            如果处理了图片点击返回True，否则返回False
        """
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
            self._select_image_char(image_cursor)
            
            self.viewport().update()
            event.accept()
            return True
        return False

    def _clear_image_selection(self):
        """清除图片选中状态"""
        if self.selected_image:
            self.selected_image = None
            self.selected_image_rect = None
            self.selected_image_cursor = None
            self.viewport().update()

    def _restore_title_format_if_needed(self):
        """如果光标在第一行且为空，恢复标题格式"""
        cursor = self.textCursor()
        if cursor.block().blockNumber() == 0:
            block_text = cursor.block().text()
            if block_text == "" or block_text == "\u200B":
                # 设置标题格式
                char_fmt = QTextCharFormat()
                char_fmt.setFontPointSize(28)
                char_fmt.setFontWeight(QFont.Weight.Bold)
                self.setCurrentCharFormat(char_fmt)

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        
        # 检查是否应该忽略事件
        if self._should_ignore_mouse_event():
            event.ignore()
            return
        
        # 标记鼠标已按下
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = True
        
        # 恢复光标显示
        self._restore_cursor_visibility()
        
        if event.button() == Qt.MouseButton.LeftButton:
            # 首先检查是否点击了链接（附件）
            if self._handle_anchor_click(event):
                return
            
            # 检查是否点击了表格
            cursor = self.cursorForPosition(event.pos())
            table = cursor.currentTable()
            if table:
                # 检查是否点击了表格边框
                if self._handle_table_border_click(table, cursor, event):
                    return
                # 点击了表格内容区域，取消表格选中，进入编辑模式
                self._handle_table_content_click(event)
                # 使用默认行为，进入单元格编辑模式
                super().mousePressEvent(event)
                return
            # 取消表格选中
            self._clear_table_selection()

            # 检查是否点击了图片缩放控制点
            if self._handle_image_resize_handle_click(event):
                return
            
            # 检查是否点击了图片中心区域（用于拖动移动）
            if self._handle_image_drag_click(event):
                return
            
            # 检查是否点击了图片
            if self._handle_image_click(event):
                return
            # 取消图片选中
            self._clear_image_selection()
        
        super().mousePressEvent(event)
        
        # 如果点击的是第一行且第一行为空，恢复标题格式
        self._restore_title_format_if_needed()
    
    def _handle_image_resizing(self, event) -> bool:
        """处理图片缩放
        
        Returns:
            如果正在缩放返回True，否则返回False
        """
        if not (self.resizing and self.resize_handle and self.resize_start_pos):
            return False
        
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
        return True

    def _handle_image_dragging(self, event) -> bool:
        """处理图片拖动移动
        
        Returns:
            如果正在拖动返回True，否则返回False
        """
        if not (self.dragging and self.drag_start_pos):
            return False
        
        # 更新预览光标位置
        target_pos = event.pos()
        self.drag_preview_cursor = self.cursorForPosition(target_pos)
        
        # 更新光标形状
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        
        # 触发重绘以显示预览指示器
        self.viewport().update()
        
        event.accept()
        return True

    def _update_cursor_for_selected_image(self, event):
        """更新已选中图片的光标形状"""
        handle = self.get_handle_at_pos(event.pos())
        if handle:
            self.viewport().setCursor(self.get_cursor_for_handle(handle))
        else:
            # 检查是否在图片区域内
            if self.selected_image_rect and self.selected_image_rect.contains(event.pos()):
                self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

    def _update_cursor_for_hover(self, event):
        """更新鼠标悬停时的光标形状（未选中图片时）"""
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

    def _handle_text_selection_for_attachments(self):
        """处理文本选择时的附件扩展"""
        # 只在鼠标按下时处理附件扩展
        if not self.mouse_pressed:
            return
        
        cursor = self.textCursor()
        if cursor.hasSelection():
            self._expand_selection_for_attachments(cursor)

    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        # 处理图片缩放
        if self._handle_image_resizing(event):
            return
        
        # 处理图片拖动移动
        if self._handle_image_dragging(event):
            return
        
        # 更新光标形状
        if self.selected_image:
            self._update_cursor_for_selected_image(event)
        else:
            self._update_cursor_for_hover(event)
        
        # 调用父类方法处理默认的文本选择行为
        super().mouseMoveEvent(event)
        
        # 处理附件选择：在拖动过程中实时扩展选择范围
        self._handle_text_selection_for_attachments()

    def _get_check_positions(self, sel_start: int, sel_end: int) -> list:
        """生成需要检查的位置列表
        Args:
            sel_start: 选择起始位置
            sel_end: 选择结束位置
            
        Returns:
            需要检查的位置列表
        """
        check_positions = [sel_start]
        for i in range(sel_start, sel_end):
            check_positions.append(i)

        return check_positions
    
    def _find_attachment_bounds(self, doc: QTextDocument, check_positions: list, tag_value: str) -> tuple:
        """查找所有附件的边界范围
        Args:
            doc: 文档对象
            check_positions: 需要检查的位置列表
            tag_value: 附件标签值
            
        Returns:
            (最小起始位置, 最大结束位置) 元组，如果没有找到附件则返回None
        """
        min_start = None
        max_end = None
        
        for pos in check_positions:
            if pos < 0:
                continue
            try:
                # 检查当前位置是否在附件范围内
                span = _find_marked_span(doc, pos, self.ATTACHMENT_TAG_PROP, tag_value)
                if span:
                    start, end_exclusive = span
                    # 更新边界
                    if min_start is None or start < min_start:
                        min_start = start
                    if max_end is None or end_exclusive > max_end:
                        max_end = end_exclusive
            except Exception:
                pass
        
        if min_start is not None and max_end is not None:
            return (min_start, max_end)
        return None
    
    def _apply_expanded_selection(self, doc: QTextDocument, start: int, end: int):
        """应用扩展后的选择范围
        
        Args:
            doc: 文档对象
            start: 新的起始位置
            end: 新的结束位置
        """
        new_cursor = QTextCursor(doc)
        _select_range(new_cursor, start, end)
        self.setTextCursor(new_cursor)
    
    def _expand_selection_for_attachments(self, cursor: QTextCursor):
        """如果选择范围包含附件，扩展选择到整个附件范围
        
        Args:
            cursor: 当前文本光标
        """
        if not cursor or not cursor.hasSelection():
            return
        
        doc = self.document()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        tag_value = getattr(self, "_attachment_tag_name", "")
        
        if not tag_value:
            return

        # 获取需要检查的位置列表
        check_positions = self._get_check_positions(sel_start, sel_end)
        logger.debug(
            "[expend-selection] selected_pos: start=%s end=%s cursor_pos=%s",
            sel_start,
            sel_end,
            cursor.position()
        )
        # 查找所有附件的边界
        bounds = self._find_attachment_bounds(doc, check_positions, tag_value)
        # 如果找到附件且范围有扩展，更新选择
        if bounds:
            expanded_start, expanded_end = bounds
            logger.debug(
                "[expend-selection] find_bounds: expanded_start=%s expanded_end=%s cursor_pos=%s",
                expanded_start,
                expanded_end,
                cursor.position()
            )
            if expanded_start < sel_start or expanded_end > sel_end:
                self._apply_expanded_selection(doc, min(expanded_start, sel_start), max(expanded_end, sel_end))
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        
        # 标记鼠标已释放
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = False
        
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
    
    def contextMenuEvent(self, event):
        """右键菜单事件 - 为表格单元格提供操作菜单"""
        # 获取鼠标位置的光标
        cursor = self.cursorForPosition(event.pos())
        table = cursor.currentTable()
        
        if table:
            # 在表格内，显示表格操作菜单
            cell = table.cellAt(cursor)
            if cell.isValid():
                menu = QMenu(self)
                
                # 获取当前单元格的行列位置
                row = cell.row()
                col = cell.column()
                
                # 在上方插入一行
                insert_row_above_action = QAction("在上方插入一行", self)
                insert_row_above_action.triggered.connect(lambda: self.insert_table_row(table, row))
                menu.addAction(insert_row_above_action)
                
                # 在下方插入一行
                insert_row_below_action = QAction("在下方插入一行", self)
                insert_row_below_action.triggered.connect(lambda: self.insert_table_row(table, row + 1))
                menu.addAction(insert_row_below_action)
                
                menu.addSeparator()
                
                # 在左侧插入一列
                insert_col_left_action = QAction("在左侧插入一列", self)
                insert_col_left_action.triggered.connect(lambda: self.insert_table_column(table, col))
                menu.addAction(insert_col_left_action)
                
                # 在右侧插入一列
                insert_col_right_action = QAction("在右侧插入一列", self)
                insert_col_right_action.triggered.connect(lambda: self.insert_table_column(table, col + 1))
                menu.addAction(insert_col_right_action)
                
                menu.addSeparator()
                
                # 删除当前行
                delete_row_action = QAction("删除当前行", self)
                delete_row_action.triggered.connect(lambda: self.delete_table_row(table, row))
                # 如果只有一行，禁用删除行功能
                if table.rows() <= 1:
                    delete_row_action.setEnabled(False)
                menu.addAction(delete_row_action)
                
                # 删除当前列
                delete_col_action = QAction("删除当前列", self)
                delete_col_action.triggered.connect(lambda: self.delete_table_column(table, col))
                # 如果只有一列，禁用删除列功能
                if table.columns() <= 1:
                    delete_col_action.setEnabled(False)
                menu.addAction(delete_col_action)
                
                menu.addSeparator()
                
                # 删除整个表格
                delete_table_action = QAction("删除整个表格", self)
                delete_table_action.triggered.connect(lambda: self.delete_entire_table(table))
                menu.addAction(delete_table_action)
                
                # 显示菜单
                menu.exec(event.globalPos())
                return
        
        # 不在表格内，使用默认右键菜单
        super().contextMenuEvent(event)
    
    def insert_table_row(self, table, row):
        """在指定位置插入一行"""
        if table:
            table.insertRows(row, 1)
    
    def insert_table_column(self, table, col):
        """在指定位置插入一列"""
        if table:
            table.insertColumns(col, 1)
    
    def delete_table_row(self, table, row):
        """删除指定行"""
        if table and table.rows() > 1:
            table.removeRows(row, 1)
    
    def delete_table_column(self, table, col):
        """删除指定列"""
        if table and table.columns() > 1:
            table.removeColumns(col, 1)
    
    def delete_entire_table(self, table):
        """删除整个表格"""
        if table:
            cursor = QTextCursor(self.document())
            table_start = table.firstPosition()
            table_end = table.lastPosition()
            
            _select_range(cursor, table_start, table_end + 1)
            cursor.removeSelectedText()
    
    def _handle_first_line_title_format(self, event):
        """处理第一行标题格式设置
        
        返回：(need_restore_format, saved_format) 元组
        """
        need_restore_format = False
        saved_format = None
        
        if not event.text() or event.text().isspace():
            return need_restore_format, saved_format
        
        cursor = self.textCursor()
        block = cursor.block()
        
        if block.blockNumber() != 0:
            return need_restore_format, saved_format
        
        block_text = block.text()
        current_fmt = self.currentCharFormat()
        current_size = current_fmt.fontPointSize()
        
        # 检查是否需要设置标题格式
        need_title_format = False
        
        if block_text == "" or block_text == "\u200B":
            if block_text == "\u200B":
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                self.setTextCursor(cursor)
            need_title_format = True
        elif current_size == 0.0 or current_size < 1.0:
            need_title_format = True
        
        if need_title_format:
            title_fmt = QTextCharFormat()
            title_fmt.setFontPointSize(28)
            title_fmt.setFontWeight(QFont.Weight.Bold)
            self.setCurrentCharFormat(title_fmt)
        
        # 记录是否需要在插入后恢复格式
        if block_text == "" or block_text == "\u200B":
            need_restore_format = True
            saved_format = self.currentCharFormat()
        
        return need_restore_format, saved_format
    
    def _restore_cursor_and_clear_table_selection(self, event):
        """恢复光标显示并清除表格选中状态"""
        if event.key() not in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.cursorWidth() == 0:
                self.setCursorWidth(1)
            if self.selected_table:
                self.selected_table = None
                self.selected_table_cursor = None
                self.viewport().update()
    
    def _log_attachment_delete_before(self, doc, del_key, current_cursor, attachment_sel, marked_span):
        """记录附件删除前的调试信息"""
        try:
            _doc_len = doc.characterCount() if doc is not None else -1
            _cur_pos = current_cursor.position()
            _sel_s = attachment_sel.selectionStart()
            _sel_e = attachment_sel.selectionEnd()
            _win_s = min(_cur_pos, _sel_s) - 40
            _win_e = max(_cur_pos, _sel_e) + 40
            
            logger.debug(
                "[attachment-delete] key=%s doc_len=%s cursor_pos=%s sel=(%s,%s)",
                del_key,
                _doc_len,
                _cur_pos,
                _sel_s,
                _sel_e,
            )
            
            if marked_span is not None:
                _ms, _me = marked_span
                logger.debug(
                    "[attachment-delete][before] marked_span=(%s,%s) len=%s chars=%s",
                    _ms,
                    _me,
                    (_me - _ms),
                    _dump_doc_chars(doc, _ms, _me - 1),
                )
            else:
                logger.debug("[attachment-delete][before] marked_span=<none>")
            
            logger.debug(
                "[attachment-delete][before] window=(%s,%s) chars=%s",
                max(0, _win_s),
                min(max(0, doc.characterCount() - 1), _win_e),
                _dump_doc_chars(doc, _win_s, _win_e)
            )
            logger.debug(
                "[attachment-delete][before] selection_chars=%s",
                _dump_selection_chars(doc, attachment_sel)
            )
        except Exception:
            pass
    
    def _extract_and_defer_delete_attachments(self, attachment_sel):
        """提取附件ID并延迟删除"""
        try:
            selected_html = attachment_sel.selection().toHtml()
            attachment_ids = []
            
            # 从 attachment://xxx 提取附件ID
            try:
                import re
                attachment_ids.extend(re.findall(r"attachment://([a-fA-F0-9\-]{16,})", selected_html))
            except Exception:
                pass
            
            # 去重
            attachment_ids = list(dict.fromkeys([x for x in attachment_ids if x]))
            
            logger.debug("[attachment-delete] extracted_attachment_ids=%s", attachment_ids)
            
            if attachment_ids and self.parent_editor and getattr(self.parent_editor, "note_manager", None):
                note_id = getattr(self.parent_editor, "current_note_id", None)
                am = getattr(self.parent_editor.note_manager, "attachment_manager", None)
                if note_id and am:
                    for aid in attachment_ids:
                        ok, msg = am.defer_delete_attachment(aid, note_id)
                        logger.debug("[attachment-delete] defer_delete_attachment id=%s ok=%s msg=%s", aid, ok, msg)
        except Exception as e:
            logger.exception("[attachment-delete] delete_attachment pre-clean failed: %s", e)
    
    def _log_attachment_delete_after(self, doc, safe_pos):
        """记录附件删除后的调试信息"""
        try:
            _after_len = doc.characterCount()
        except Exception:
            _after_len = -1
        
        logger.debug(
            "[attachment-delete] after_delete safe_pos=%s doc_len=%s",
            safe_pos,
            _after_len,
        )
        
        # 检查是否仍残留被标记范围
        try:
            _marked_span_after = _find_marked_span(
                doc,
                safe_pos,
                self.ATTACHMENT_TAG_PROP,
                getattr(self, "_attachment_tag_name", ""),
            )
            
            if _marked_span_after is not None:
                _ms2, _me2 = _marked_span_after
                logger.debug(
                    "[attachment-delete][after] marked_span=(%s,%s) len=%s chars=%s",
                    _ms2,
                    _me2,
                    (_me2 - _ms2),
                    _dump_doc_chars(doc, _ms2, _me2 - 1),
                )
            else:
                logger.debug("[attachment-delete][after] marked_span=<none>")
        except Exception:
            pass
        
        try:
            _after_win_s = safe_pos - 40
            _after_win_e = safe_pos + 80
            logger.debug(
                "[attachment-delete][after] window=(%s,%s) chars=%s",
                max(0, _after_win_s),
                min(max(0, doc.characterCount() - 1), _after_win_e),
                _dump_doc_chars(doc, _after_win_s, _after_win_e)
            )
        except Exception:
            pass
    
    def _handle_attachment_deletion(self, event, current_cursor):
        """处理附件删除
        
        返回：True 表示已处理，False 表示未处理
        """
        attachment_sel = self._select_whole_attachment_span(current_cursor)
        if attachment_sel is None:
            return False
        
        doc = self.document()
        del_key = "Delete" if event.key() == Qt.Key.Key_Delete else "Backspace"
        
        # 获取标记范围
        _sel_s = attachment_sel.selectionStart()
        _marked_span = _find_marked_span(
            doc,
            _sel_s,
            self.ATTACHMENT_TAG_PROP,
            getattr(self, "_attachment_tag_name", ""),
        )
        
        # 记录删除前信息
        self._log_attachment_delete_before(doc, del_key, current_cursor, attachment_sel, _marked_span)
        
        # 延迟删除附件文件
        self._extract_and_defer_delete_attachments(attachment_sel)
        
        # 删除文本块
        pre_start = attachment_sel.selectionStart()
        attachment_sel.beginEditBlock()
        attachment_sel.removeSelectedText()
        attachment_sel.endEditBlock()
        
        safe_pos = pre_start
        
        # 记录删除后信息
        self._log_attachment_delete_after(doc, safe_pos)
        
        # 恢复光标位置
        try:
            attachment_sel.clearSelection()
            _safe_set_cursor_position(doc, attachment_sel, safe_pos, "attachment-delete:restore-cursor")
            self.setTextCursor(attachment_sel)
        except Exception:
            self.setTextCursor(attachment_sel)
        
        event.accept()
        return True
    
    def _handle_selected_table_deletion(self, event, current_table):
        """处理已选中表格的删除
        
        返回：True 表示已处理，False 表示未处理
        """
        if not self.selected_table or not self.selected_table_cursor:
            return False
        
        # 如果当前光标在表格内，说明用户正在编辑单元格内容
        if current_table == self.selected_table:
            super().keyPressEvent(event)
            return True
        
        # 删除整个表格（第二次按删除键）
        cursor = QTextCursor(self.document())
        table_start = self.selected_table.firstPosition()
        table_end = self.selected_table.lastPosition()
        
        _select_range(cursor, table_start, table_end + 1)
        cursor.removeSelectedText()
        
        # 清除选中状态
        self.selected_table = None
        self.selected_table_cursor = None
        self.setCursorWidth(1)
        self.viewport().update()
        
        event.accept()
        return True
    
    def _handle_table_selection(self, event, cursor_pos):
        """处理表格选中（第一次按删除键）
        
        返回：True 表示已处理，False 表示未处理
        """
        frame = self.document().rootFrame()
        for child_frame in frame.childFrames():
            table = child_frame
            if not hasattr(table, 'firstPosition'):
                continue
            
            table_start = table.firstPosition()
            table_end = table.lastPosition()
            
            # 检查光标是否紧邻表格
            is_before_table = (event.key() == Qt.Key.Key_Delete and 
                              cursor_pos <= table_start and cursor_pos >= table_start - 2)
            is_after_table = (event.key() == Qt.Key.Key_Backspace and 
                             cursor_pos >= table_end + 1 and cursor_pos <= table_end + 3)
            
            if is_before_table or is_after_table:
                # 选中表格
                self.selected_table = table
                self.selected_table_cursor = QTextCursor(self.document())
                self.selected_table_cursor.setPosition(table_start)
                
                # 移动光标到表格外部
                clear_cursor = QTextCursor(self.document())
                if is_before_table:
                    clear_cursor.setPosition(table_start - 1 if table_start > 0 else 0)
                else:
                    clear_cursor.setPosition(table_end + 1)
                clear_cursor.clearSelection()
                self.setTextCursor(clear_cursor)
                
                # 隐藏光标
                self.setCursorWidth(0)
                self.viewport().update()
                
                event.accept()
                return True
        
        return False
    
    def keyPressEvent(self, event):
        """键盘事件 - 使用默认行为，允许删除选区中的所有内容（包括图片）"""
        # 处理第一行标题格式
        need_restore_format, saved_format = self._handle_first_line_title_format(event)
        
        # 恢复光标显示并清除表格选中状态
        self._restore_cursor_and_clear_table_selection(event)
        
        # 处理删除键
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            current_cursor = self.textCursor()
            
            # 先处理附件删除
            if self._handle_attachment_deletion(event, current_cursor):
                return
            
            current_table = current_cursor.currentTable()
            
            # 处理已选中表格的删除
            if self._handle_selected_table_deletion(event, current_table):
                return
            
            # 处理表格选中（第一次按删除键）
            cursor_pos = current_cursor.position()
            if self._handle_table_selection(event, cursor_pos):
                return
        
        # 使用默认行为
        super().keyPressEvent(event)
        
        # 恢复格式
        if need_restore_format and saved_format:
            self.setCurrentCharFormat(saved_format)
    
    def inputMethodEvent(self, event):
        """输入法事件 - 处理中文等输入法输入"""
        # 获取输入的文本
        commit_string = event.commitString()
        
        if commit_string:  # 有实际输入的文本
            cursor = self.textCursor()
            block = cursor.block()
            block_number = block.blockNumber()
            
            # 如果在第一行
            if block_number == 0:
                # 检查第一行是否为空或只有零宽度空格
                block_text = block.text()
                
                if block_text == "" or block_text == "\u200B":
                    # 设置标题格式
                    title_fmt = self.currentCharFormat()
                    title_fmt.setFontPointSize(28)
                    title_fmt.setFontWeight(QFont.Weight.Bold)
                    self.setCurrentCharFormat(title_fmt)
        
        # 调用父类方法处理输入法事件
        super().inputMethodEvent(event)
        
        # 输入完成后，触发格式检查
        if commit_string:
            # 调用父对象（NoteEditor）的 auto_format_first_line 方法
            parent = self.parent()
            if parent and hasattr(parent, 'auto_format_first_line'):
                parent.auto_format_first_line()
    
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
            if _select_char_at(cursor, check_pos):
                selected_text = cursor.selectedText()
                char_format = cursor.charFormat()
                
                # 检查是否是真正的图片字符
                if char_format.isImageFormat() and selected_text == '\ufffc':
                    real_image_pos = check_pos
                    
                    # 检查图片字符前面是否有段落分隔符
                    if real_image_pos > 0:
                        _select_char_at(cursor, real_image_pos - 1)
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
        _select_char_at(cursor, cursor.position())
        
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
        _select_char_at(cursor, cursor.position())
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
            if _select_char_at(cursor, check_pos):
                selected_text = cursor.selectedText()
                char_format = cursor.charFormat()
                
                # 检查是否是真正的图片字符
                if char_format.isImageFormat() and selected_text == '\ufffc':
                    real_image_pos = check_pos
                    
                    # 检查图片字符前面是否有段落分隔符
                    if real_image_pos > 0:
                        _select_char_at(cursor, real_image_pos - 1)
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
        
        # 选中需要删除的字符范围（段落分隔符 + 图片字符，或只有图片字符）
        _select_range(cursor, delete_start_pos, delete_start_pos + delete_count)
        
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
        
        # 保存格式菜单的引用，用于更新状态
        self.format_menu = format_menu
        
        # 标题样式（平铺在格式菜单下）
        self.title_action = QAction("标题", self)
        self.title_action.setCheckable(True)
        self.title_action.triggered.connect(lambda: self.apply_heading(1))
        format_menu.addAction(self.title_action)
        
        self.heading_action = QAction("小标题", self)
        self.heading_action.setCheckable(True)
        self.heading_action.triggered.connect(lambda: self.apply_heading(2))
        format_menu.addAction(self.heading_action)
        
        self.subheading_action = QAction("副标题", self)
        self.subheading_action.setCheckable(True)
        self.subheading_action.triggered.connect(lambda: self.apply_heading(3))
        format_menu.addAction(self.subheading_action)
        
        format_menu.addSeparator()
        
        # 文本样式
        self.bold_action = QAction("粗体", self)
        self.bold_action.setCheckable(True)
        self.bold_action.setShortcut("Ctrl+B")
        self.bold_action.triggered.connect(self.toggle_bold)
        format_menu.addAction(self.bold_action)
        
        self.italic_action = QAction("斜体", self)
        self.italic_action.setCheckable(True)
        self.italic_action.setShortcut("Ctrl+I")
        self.italic_action.triggered.connect(self.toggle_italic)
        format_menu.addAction(self.italic_action)
        
        self.underline_action = QAction("下划线", self)
        self.underline_action.setCheckable(True)
        self.underline_action.setShortcut("Ctrl+U")
        self.underline_action.triggered.connect(self.toggle_underline)
        format_menu.addAction(self.underline_action)
        
        self.strikethrough_action = QAction("删除线", self)
        self.strikethrough_action.setCheckable(True)
        self.strikethrough_action.triggered.connect(self.toggle_strikethrough)
        format_menu.addAction(self.strikethrough_action)
        
        format_menu.addSeparator()
        
        # 字体颜色
        text_color_action = QAction("字体颜色...", self)
        text_color_action.triggered.connect(self.choose_text_color)
        format_menu.addAction(text_color_action)
        
        # 背景色
        bg_color_action = QAction("背景色...", self)
        bg_color_action.triggered.connect(self.choose_background_color)
        format_menu.addAction(bg_color_action)
        
        format_menu.addSeparator()
        
        # 正文
        body_action = QAction("正文", self)
        body_action.triggered.connect(self.apply_body_text)
        format_menu.addAction(body_action)
        
        format_menu.addSeparator()
        
        # 列表子菜单（移到格式菜单下）
        list_menu = format_menu.addMenu("列表")
        
        self.bullet_action = QAction("• 项目符号列表", self)
        self.bullet_action.setCheckable(True)
        self.bullet_action.triggered.connect(self.toggle_bullet_list)
        list_menu.addAction(self.bullet_action)
        
        self.number_action = QAction("1. 编号列表", self)
        self.number_action.setCheckable(True)
        self.number_action.triggered.connect(self.toggle_numbered_list)
        list_menu.addAction(self.number_action)
        
        # 连接格式菜单的aboutToShow信号，在显示前更新状态
        format_menu.aboutToShow.connect(self.update_format_menu_state)
        
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

        try:
            logger.debug(
                "[attachment-remark] setHtml called note_id=%s html_len=%s plain_len=%s has_attachment_url=%s tag=%s",
                getattr(self, "current_note_id", None),
                len(html_content or ""),
                len(self.text_edit.toPlainText() or ""),
                ("attachment://" in (html_content or "")),
                getattr(self.text_edit, "_attachment_tag_name", None),
            )
        except Exception:
            pass

        # 重新打标记：附件块的 QTextCharFormat 自定义属性不会持久化到 HTML。
        # 因此应用重启后加载笔记时，需要根据 HTML 中的 attachment:// 链接重新识别附件块，
        # 使其在 Delete/Backspace 时仍能整体删除。
        try:
            self._remark_attachment_blocks_after_load()
        except Exception as e:
            logger.exception("[attachment-remark] remark failed: %s", e)
        
        # 重新渲染所有数学公式
        self.rerender_formulas()

    def _remark_attachment_blocks_after_load(self):
        """扫描文档，给附件展示块重新打标记（用于整体删除）。

        关键原则：
        - **只标记真正的附件展示片段**（文件名链接 + 空格 + size 文本），不要把整个 block 都打上标记。
          否则会把 block 内的 ZWSP/PSEP 或用户后续输入内容一并标记，导致删除范围漂移、误删换行。
        """
        doc = self.text_edit.document()
        
        total_blocks = 0
        matched_blocks = 0
        marked_chars = 0
        
        block = doc.firstBlock()
        while block.isValid():
            total_blocks += 1
            
            if self._block_has_attachment(block, doc):
                matched_blocks += 1
                marked_chars += self._mark_attachment_segments_in_block(block, doc)
            
            block = block.next()
        
        # 验证标记结果
        tagged_chars = self._verify_tagged_chars(doc)
        
        logger.debug(
            "[attachment-remark] done blocks_total=%s blocks_matched=%s marked_chars=%s "
            "tagged_chars=%s",
            total_blocks,
            matched_blocks,
            marked_chars,
            tagged_chars,
        )
    
    def _is_attachment_anchor_at(self, doc, position: int) -> bool:
        """检查指定位置是否是附件anchor。
        
        采用选中字符再检查格式的方式，避免丢失第一个字符。
        """
        try:
            if position < 0 or position > max(0, doc.characterCount() - 1):
                return False

            cf = _selected_char_format(doc, position)
            if cf is None or not cf.isAnchor():
                return False
            
            href = cf.anchorHref() or ""
            is_attachment = href.startswith("attachment://")
            
            if is_attachment:
                # 获取该位置的字符
                char = self._char_at(doc, position)
                logger.debug(
                    "[attachment-anchor] found at pos=%s char=%r href=%s",
                    position,
                    char,
                    href,
                )
            return is_attachment
        except Exception:
            return False
    
    def _char_at(self, doc, position: int) -> str:
        """获取指定位置的字符。"""
        return _get_char_at(doc, position)
    
    def _is_trailing_separator(self, doc, position: int) -> bool:
        """检查指定位置是否是尾随分隔符（空格、制表符、零宽空格）。
        
        只允许把"附件展示片段"右侧紧邻的少量空白纳入标记范围（用于 Backspace/Delete 整块删除）。
        禁止把段落边界（\\u2029 / \\n / \\r）纳入标记范围。
        """
        try:
            t = self._char_at(doc, position)
            return t in (" ", "\t", "\u200b")
        except Exception:
            return False
    
    def _block_has_attachment(self, block, doc) -> bool:
        """检查block是否包含附件。
        扫描 block 的 fragment HTML 是否包含 `attachment://`
        """
        block_cursor = QTextCursor(block)
        block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        try:
            block_html = block_cursor.selection().toHtml() or ""
        except Exception:
            block_html = ""
        
        return "attachment://" in block_html
    
    def _mark_attachment_segments_in_block(self, block, doc) -> int:
        """在block内找出所有附件anchor的连续片段，并对每个片段单独打标。
        
        返回：标记的字符数
        """
        marked_chars = 0
        
        try:
            block_start = block.position()
            block_inclusive = min(max(0, doc.characterCount() - 1), max(0, block_start + block.length() - 1))
            
            i = block_start
            while i <= block_inclusive:
                if not self._is_attachment_anchor_at(doc, i):
                    i += 1
                    continue
                
                # 直接使用_find_attachment_segment_bounds查找附件的完整范围
                # 这个函数会找到：anchor文本 + size文本 + 尾随分隔空格
                # 不依赖已有的标记，适用于重启后的重新标记场景
                seg_start, seg_end = self._find_attachment_segment_bounds(doc, i, block_start, block_inclusive)
                
                # 日志：输出找到的附件范围
                logger.debug(
                    "[attachment-remark] found attachment segment: start=%s end=%s (length=%s)",
                    seg_start,
                    seg_end,
                    seg_end - seg_start + 1,
                )
                
                # 对完整范围打标记
                self._apply_attachment_mark(doc, seg_start, seg_end)
                
                marked_chars += max(0, (seg_end + 1) - seg_start)
                
                # 跳过该片段，继续查找下一个附件
                i = seg_end + 1
            
            # 获取block_html用于日志
            block_cursor = QTextCursor(block)
            block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            try:
                block_html = block_cursor.selection().toHtml() or ""
            except Exception:
                block_html = ""
            
            logger.debug(
                "[attachment-remark] marked block=%s marked_start_pos=%s len=%s html_has_attachment=%s marked_chars=%s",
                block.blockNumber(),
                seg_start,
                seg_end + 1,
                ("attachment://" in block_html),
                marked_chars,
            )
        
        except Exception as e:
            logger.debug("[attachment-remark] mark block failed: %s", e)
        
        return marked_chars
    
    def _find_attachment_segment_bounds(self, doc, start_pos: int, block_start: int, block_end: int) -> tuple:
        """找到附件片段的起始和结束位置。
        
        包括：anchor文本 + size文本 + 尾随分隔空格
        
        返回：(seg_start, seg_end) inclusive
        """
        # anchor 起点（向左扩展同 href 的连续范围）
        seg_start = start_pos
        while seg_start > block_start and self._is_attachment_anchor_at(doc, seg_start - 1):
            seg_start -= 1
        
        # anchor 终点（向右扩展同 href 的连续范围）
        seg_end = start_pos
        while seg_end < block_end and self._is_attachment_anchor_at(doc, seg_end + 1):
            seg_end += 1

        return seg_start, seg_end
    
    def _apply_attachment_mark(self, doc, seg_start: int, seg_end: int):
        """对指定范围应用附件标记。
        
        参数：
            seg_start: 起始位置（inclusive）
            seg_end: 结束位置（inclusive）
        """
        mark_format = QTextCharFormat()
        mark_format.setProperty(
            self.text_edit.ATTACHMENT_TAG_PROP,
            self.text_edit._attachment_tag_name,
        )
        mark_cursor = QTextCursor(doc)
        _select_range(mark_cursor, seg_start, seg_end + 1)
        mark_cursor.mergeCharFormat(mark_format)
    
    def _verify_tagged_chars(self, doc) -> int:
        """验证：扫描全文，看最终有多少字符真的带上了标记。
        
        返回：带标记的字符数
        """
        tagged_chars = 0
        try:
            doc_len = doc.characterCount()
            max_pos = max(0, doc_len - 1)
            for i in range(max_pos + 1):
                cf = _selected_char_format(doc, i)
                if ( cf is not None and cf.hasProperty(self.text_edit.ATTACHMENT_TAG_PROP)
                    and cf.property(self.text_edit.ATTACHMENT_TAG_PROP) == self.text_edit._attachment_tag_name
                ):
                    tagged_chars += 1
        except Exception as e:
            logger.debug("[attachment-remark] verify scan failed: %s", e)
        
        return tagged_chars
    
    def clear(self):
        self.text_edit.clear()
        self.attachments.clear()
        
        # 获取光标
        cursor = self.text_edit.textCursor()
        
        # 创建标题字符格式
        title_char_fmt = QTextCharFormat()
        title_char_fmt.setFontPointSize(28)
        title_char_fmt.setFontWeight(QFont.Weight.Bold)
        
        # 关键：插入一个零宽度空格，这样块格式才能生效
        # 零宽度空格 (U+200B) 不可见但能撑起光标高度
        cursor.insertText('\u200B', title_char_fmt)
        
        # 将光标移回开头
        cursor.movePosition(cursor.MoveOperation.Start)
        
        # 应用光标
        self.text_edit.setTextCursor(cursor)
        
        # 设置当前输入格式
        self.text_edit.setCurrentCharFormat(title_char_fmt)
    
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
            # 创建标题字符格式
            title_char_fmt = QTextCharFormat()
            title_char_fmt.setFontPointSize(28)
            title_char_fmt.setFontWeight(QFont.Weight.Bold)
            
            # 获取光标并插入零宽度空格
            cursor = self.text_edit.textCursor()
            cursor.insertText('\u200B', title_char_fmt)
            
            # 将光标移回开头
            cursor.movePosition(cursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor)
            
            # 设置当前输入格式
            self.text_edit.setCurrentCharFormat(title_char_fmt)
            return
        
        # 获取当前光标
        current_cursor = self.text_edit.textCursor()
        
        # 如果当前有选区（用户正在拖选），不要执行格式化
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
            # 获取第一行的文本内容
            first_line_text = first_block.text()
            
            # 设置字符格式
            new_char_fmt = QTextCharFormat()
            new_char_fmt.setFontPointSize(28)
            new_char_fmt.setFontWeight(QFont.Weight.Bold)
            
            # 如果第一行为空或只有零宽度空格，不要重新插入，直接设置当前输入格式即可
            if first_line_text == "" or first_line_text == "\u200B":
                # 不做任何操作，让后面的代码设置当前输入格式
                pass
            else:
                # 应用格式到第一行已有文本
                # 阻止信号，避免递归
                self.text_edit.blockSignals(True)
                first_cursor.mergeCharFormat(new_char_fmt)
                # 恢复信号
                self.text_edit.blockSignals(False)
        
        # 根据光标所在行设置当前输入格式
        if current_block_number == 0:
            # 光标在第一行（标题），设置标题格式为当前输入格式
            # 获取当前光标的字符格式，保留其他属性
            current_fmt = self.text_edit.currentCharFormat()
            current_fmt.setFontPointSize(28)
            current_fmt.setFontWeight(QFont.Weight.Bold)
            self.text_edit.setCurrentCharFormat(current_fmt)
        else:
            # 光标在第二行或之后（正文），设置正文格式为当前输入格式
            body_fmt = QTextCharFormat()
            body_fmt.setFontPointSize(14)
            body_fmt.setFontWeight(QFont.Weight.Normal)
            
            # 如果当前行为空，插入一个零宽度空格，让光标有正确的格式依附
            if current_block.text() == "":
                self.text_edit.blockSignals(True)
                current_cursor.setCharFormat(body_fmt)
                current_cursor.insertText("\u200B")  # 零宽度空格
                # 将光标移回零宽度空格之后
                current_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                self.text_edit.setTextCursor(current_cursor)
                self.text_edit.blockSignals(False)
            
            self.text_edit.setCurrentCharFormat(body_fmt)
    
    # 格式化方法
    def apply_heading(self, level):
        """应用标题格式，如果已经是该格式则取消"""
        cursor = self.text_edit.textCursor()
        
        # 获取当前字符格式
        current_fmt = cursor.charFormat()
        current_size = current_fmt.fontPointSize()
        current_weight = current_fmt.fontWeight()
        
        # 判断当前是否已经是该标题格式
        is_current_format = False
        if level == 1 and current_size == 28 and current_weight == QFont.Weight.Bold:
            is_current_format = True
        elif level == 2 and current_size == 22 and current_weight == QFont.Weight.Bold:
            is_current_format = True
        elif level == 3 and current_size == 18 and current_weight == QFont.Weight.Bold:
            is_current_format = True
        
        cursor.beginEditBlock()
        
        if is_current_format:
            # 如果已经是该格式，则恢复为正文格式
            self.apply_body_text()
        else:
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
    
    def choose_text_color(self):
        """选择字体颜色"""
        cursor = self.text_edit.textCursor()
        
        # 获取当前字体颜色作为初始颜色
        current_format = cursor.charFormat()
        current_color = current_format.foreground().color()
        
        # 打开颜色选择对话框
        color = QColorDialog.getColor(current_color, self, "选择字体颜色")
        
        if color.isValid():
            # 应用选择的颜色
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            
            # 如果有选中文本，应用到选中文本
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                # 如果没有选中文本，设置当前格式（影响后续输入）
                self.text_edit.setCurrentCharFormat(fmt)
    
    def choose_background_color(self):
        """选择背景色"""
        cursor = self.text_edit.textCursor()
        
        # 获取当前背景色作为初始颜色
        current_format = cursor.charFormat()
        current_color = current_format.background().color()
        
        # 打开颜色选择对话框
        color = QColorDialog.getColor(current_color, self, "选择背景色")
        
        if color.isValid():
            # 应用选择的颜色
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            
            # 如果有选中文本，应用到选中文本
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                # 如果没有选中文本，设置当前格式（影响后续输入）
                self.text_edit.setCurrentCharFormat(fmt)
    
    def insert_bullet_list(self):
        """插入项目符号列表"""
        cursor = self.text_edit.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDisc)
    
    def insert_numbered_list(self):
        """插入编号列表"""
        cursor = self.text_edit.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDecimal)
    
    def toggle_bullet_list(self):
        """切换项目符号列表"""
        cursor = self.text_edit.textCursor()
        current_list = cursor.currentList()
        
        if current_list and current_list.format().style() == QTextListFormat.Style.ListDisc:
            # 如果已经是项目符号列表，则移除列表
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
        else:
            # 否则创建项目符号列表
            if cursor.hasSelection():
                # 如果有选中文字，保存选中的文字并转换为列表
                selected_text = cursor.selectedText()
                cursor.insertList(QTextListFormat.Style.ListDisc)
                cursor.insertText(selected_text)
            else:
                cursor.insertList(QTextListFormat.Style.ListDisc)
    
    def toggle_numbered_list(self):
        """切换编号列表"""
        cursor = self.text_edit.textCursor()
        current_list = cursor.currentList()
        
        if current_list and current_list.format().style() == QTextListFormat.Style.ListDecimal:
            # 如果已经是编号列表，则移除列表
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
        else:
            # 否则创建编号列表
            if cursor.hasSelection():
                # 如果有选中文字，保存选中的文字并转换为列表
                selected_text = cursor.selectedText()
                cursor.insertList(QTextListFormat.Style.ListDecimal)
                cursor.insertText(selected_text)
            else:
                cursor.insertList(QTextListFormat.Style.ListDecimal)
    
    def update_format_menu_state(self):
        """更新格式菜单的状态（显示当前格式）"""
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        
        # 获取当前字体大小和粗细
        font_size = fmt.fontPointSize()
        font_weight = fmt.fontWeight()
        
        # 更新标题状态
        self.title_action.setChecked(font_size == 28 and font_weight == QFont.Weight.Bold)
        self.heading_action.setChecked(font_size == 22 and font_weight == QFont.Weight.Bold)
        self.subheading_action.setChecked(font_size == 18 and font_weight == QFont.Weight.Bold)
        
        # 更新文本样式状态
        self.bold_action.setChecked(font_weight == QFont.Weight.Bold)
        self.italic_action.setChecked(fmt.fontItalic())
        self.underline_action.setChecked(fmt.fontUnderline())
        self.strikethrough_action.setChecked(fmt.fontStrikeOut())
        
        # 更新列表状态
        current_list = cursor.currentList()
        if current_list:
            list_style = current_list.format().style()
            self.bullet_action.setChecked(list_style == QTextListFormat.Style.ListDisc)
            self.number_action.setChecked(list_style == QTextListFormat.Style.ListDecimal)
        else:
            self.bullet_action.setChecked(False)
            self.number_action.setChecked(False)
    
    def insert_table(self):
        """插入表格（默认 3x3，不弹出对话框）"""
        rows, cols = 3, 3
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
            _select_char_at(cursor, cursor.position())
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
                    _select_char_at(edit_cursor, pos)
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
    
    def _format_file_size(self, file_size):
        """格式化文件大小为可读字符串"""
        if file_size < 1024:
            return f"{file_size} B"
        elif file_size < 1024 * 1024:
            return f"{file_size / 1024:.1f} KB"
        else:
            return f"{file_size / (1024 * 1024):.1f} MB"
    
    def _add_attachment_to_manager(self, file_path, file_name, file_size):
        """将附件添加到附件管理器
        
        返回：(success, attachment_id) 或 (False, None)
        """
        success, message, attachment_id = self.note_manager.attachment_manager.add_attachment(
            file_path, self.current_note_id
        )
        
        if not success:
            QMessageBox.warning(self, "添加附件失败", message)
            return False, None
        
        return True, attachment_id
    
    def _create_attachment_html(self, attachment_id, file_name, size_str):
        """创建附件的HTML代码"""
        attachment_url = f"attachment://{attachment_id}"
        return f'<a href="{attachment_url}" style="color: #0066cc;">{file_name} ({size_str})</a>'
    
    def _log_attachment_insert_before(self, start_pos, file_name, size_str, attachment_id):
        """记录附件插入前的日志"""
        try:
            doc = self.text_edit.document()
            doc_len = int(doc.characterCount())
            doc_content = _dump_doc_chars(doc, 0, doc_len - 1)
            logger.debug(
                "[attachment-insert][before] start_pos=cursor_pos=%s doc_len=%s file=%s size=%s attachment_id=%s doc_content=%s",
                start_pos,
                doc_len,
                file_name,
                size_str,
                attachment_id,
                doc_content,
            )
        except Exception:
            pass
    
    def _log_attachment_insert_after(self, end_pos, start_pos):
        """记录附件插入后的日志"""
        try:
            doc = self.text_edit.document()
            doc_len = int(doc.characterCount())
            doc_content = _dump_doc_chars(doc, 0, doc_len - 1)
            logger.debug(
                "[attachment-insert][after] start_pos=%s cursor_pos=end_pos=%s doc_len=%s doc_content=%s",
                start_pos,
                end_pos,
                doc_len,
                doc_content,
            )
        except Exception:
            pass
    
    def _mark_inserted_attachment(self, doc, start_pos, end_pos):
        """对插入的附件打标记"""
        if end_pos <= start_pos:
            return
        
        mark_cursor = QTextCursor(doc)
        _select_range(mark_cursor, start_pos, end_pos)
        
        try:
            logger.debug(
                "[attachment-insert][mark][before] start_pos=%s end_pos=%s doc_len=%s start_char=%s",
                start_pos,
                end_pos,
                int(doc.characterCount()),
                _dump_doc_chars(doc, start_pos, min(end_pos - 1, start_pos)),
            )
        except Exception:
            pass
        
        mark_format = QTextCharFormat()
        mark_format.setProperty(
            self.text_edit.ATTACHMENT_TAG_PROP,
            self.text_edit._attachment_tag_name,
        )
        mark_cursor.mergeCharFormat(mark_format)
        
        # 验证标记范围
        self._verify_attachment_mark(doc, start_pos)
    
    def _verify_attachment_mark(self, doc, start_pos):
        """验证附件标记范围"""
        try:
            marked = _find_marked_span(
                doc,
                start_pos,
                self.text_edit.ATTACHMENT_TAG_PROP,
                getattr(self.text_edit, "_attachment_tag_name", ""),
            )
            if marked is not None:
                ms, me = marked
                logger.debug(
                    "[attachment-insert][mark][after] span=(%s,%s) len=%s span chars=%s, all file chars=%s",
                    ms,
                    me,
                    (me - ms),
                    _dump_doc_chars(doc, ms, me - 1),
                    _dump_doc_chars(doc, 0, int(doc.characterCount()) - 1),
                )
        except Exception:
            pass
    
    def _reset_cursor_format(self, cursor):
        """重置光标格式，避免后续输入继承附件标记"""
        try:
            cursor.setCharFormat(QTextCharFormat())
            self.text_edit.setTextCursor(cursor)
            self.text_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass
    
    def _insert_attachment_with_path(self, file_path):
        """插入附件链接 - 使用附件管理器加密存储"""
        try:
            import os
            
            # 检查是否有note_manager和当前笔记ID
            if not self.note_manager or not self.current_note_id:
                QMessageBox.warning(self, "错误", "无法添加附件：笔记未保存")
                return
            
            # 获取文件信息
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            size_str = self._format_file_size(file_size)
            
            # 添加附件到管理器
            success, attachment_id = self._add_attachment_to_manager(file_path, file_name, file_size)
            if not success:
                return
            
            # 创建附件HTML
            attachment_html = self._create_attachment_html(attachment_id, file_name, size_str)
            
            # 插入附件HTML
            cursor = self.text_edit.textCursor()
            start_pos = cursor.position()
            
            self._log_attachment_insert_before(start_pos, file_name, size_str, attachment_id)
            cursor.insertHtml(attachment_html)
            end_pos = cursor.position()
            self._log_attachment_insert_after(end_pos, start_pos)
            
            # 标记插入的附件
            try:
                doc = self.text_edit.document()
                self._mark_inserted_attachment(doc, start_pos, end_pos)
            except Exception:
                pass
            
            # 重置光标格式
            self._reset_cursor_format(cursor)
            
            print(f"成功插入附件: {file_name} ({size_str}), ID: {attachment_id}")
            
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
                    
                    if _select_char_at(cursor, check_pos):
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
                _select_char_at(cursor, real_image_pos)
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