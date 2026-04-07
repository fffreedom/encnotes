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
    QSpinBox, QDialogButtonBox, QColorDialog, QToolButton, QWidgetAction,
    QProxyStyle, QStyleOptionMenuItem
)
from PyQt6.QtWidgets import QStyle
from PyQt6.QtCore import Qt, QSize, QUrl, QMimeData, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import (
    QTextCursor, QFont, QTextCharFormat, QColor, QAction,
    QTextBlockFormat, QTextListFormat, QTextTableFormat,
    QTextFrameFormat, QTextLength, QImage, QPixmap, QClipboard,
    QTextImageFormat, QTextFormat, QTextDocument, QIcon, QPainter
)

from math_renderer import MathRenderer
import os
import uuid
from pathlib import Path
import base64
import html
import re
import logging
import traceback

logger = logging.getLogger(__name__)

# ── 编辑器字体大小常量 ──────────────────────────────────────────────────────────
FONT_SIZE_NOTE_TITLE = 28   # 笔记第一行标题（自动应用）
FONT_SIZE_HEADING1   = 22   # 格式菜单：标题
FONT_SIZE_HEADING2   = 18   # 格式菜单：小标题
FONT_SIZE_HEADING3   = 15   # 格式菜单：副标题
FONT_SIZE_BODY       = 14   # 正文
# ────────────────────────────────────────────────────────────────────────────────


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
    # print(f"[DEBUG] 位置 {p} 选中的字符: '{selected_char}' (Unicode: {ord(selected_char) if selected_char else 'N/A'})")

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

        # 表格拖动相关
        self.table_dragging = False
        self.table_drag_start_pos = None
        self.table_drag_preview_cursor = None  # 表格拖动预览光标位置

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

        # 监听光标位置变化信号，自动格式化第一行
        # Qt中信号通过emit发出，通过connect连接到槽函数，可以被blockSignals()阻止
        # Qt中事件由Qt事件系统直接调用，通过重写事件处理函数来处理，如focusInEvent等，不受blockSignals()影响
        self.cursorPositionChanged.connect(self.update_title_and_input_format)

        # 自定义光标闪烁控制（用于空行大字体时绘制正确高度的光标）
        from PyQt6.QtCore import QTimer
        self._cursor_blink_visible = True  # 当前闪烁状态：True=显示，False=隐藏
        self._cursor_blink_timer = QTimer(self)
        self._cursor_blink_timer.timeout.connect(self._on_cursor_blink)
        # 手动设置格式后记录目标字号（pt），用于下一次光标绘制时使用正确高度，绘制后清除
        self._manual_format_pt = 0
        # 隐藏 Qt 原生光标，由自己完全接管绘制
        self.setCursorWidth(0)

    def _on_cursor_blink(self):
        """光标闪烁定时器回调，切换显示/隐藏状态并触发重绘"""
        self._cursor_blink_visible = not self._cursor_blink_visible
        # logger.debug(f"[cursor_blink_timer] 定时器触发，切换状态 -> _cursor_blink_visible={self._cursor_blink_visible}")
        self.viewport().update()

    def _start_cursor_blink(self):
        """获得焦点时启动光标闪烁"""
        from PyQt6.QtWidgets import QApplication
        self._cursor_blink_visible = True
        # 获取系统光标闪烁时间，如果为0则不闪烁，单位是毫秒
        flash_time = QApplication.cursorFlashTime()
        if flash_time > 0:
            self._cursor_blink_timer.start(flash_time // 2)
        else:
            self._cursor_blink_timer.stop()
            self._cursor_blink_visible = True
        self.viewport().update()

    def _stop_cursor_blink(self):
        """失去焦点时停止光标闪烁"""
        self._cursor_blink_timer.stop()
        self._cursor_blink_visible = False
        self.viewport().update()

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

    def _get_current_note_id(self):
        """获取当前笔记ID
        
        通过调用parent_editor的_get_current_note_id方法来获取当前的笔记id
        
        Returns:
            int or None: 当前笔记ID，如果没有parent_editor或parent_editor没有该方法则返回None
        """
        if self.parent_editor and hasattr(self.parent_editor, '_get_current_note_id'):
            return self.parent_editor._get_current_note_id()
        return None

    def _create_title_format(self):
        """创建标题字符格式（28号粗体）"""
        title_fmt = QTextCharFormat()
        title_fmt.setFontPointSize(FONT_SIZE_NOTE_TITLE)
        title_fmt.setFontWeight(QFont.Weight.Bold)
        return title_fmt
    
    def _create_body_format(self):
        """创建正文字符格式（14号普通）"""
        body_fmt = QTextCharFormat()
        body_fmt.setFontPointSize(FONT_SIZE_BODY)
        body_fmt.setFontWeight(QFont.Weight.Normal)
        return body_fmt

    def set_input_format(self, current_cursor, current_block, is_title_format=False):
        """设置输入格式，根据is_title_format决定设置标题格式还是正文格式
        
        Args:
            current_cursor: 当前光标
            current_block: 当前文本块
            is_title_format: True表示设置标题格式，False表示设置正文格式
        """
        fmt = self._create_title_format() if is_title_format else self._create_body_format()
        format_name = "标题" if is_title_format else "正文"
        block_text = current_block.text()

        # 如果当前行为空，插入零宽度空格让光标有正确的格式依附
        if block_text == "":
            # 立即设置后续输入字符格式（不修改文档，不会影响回车操作）
            self.setCurrentCharFormat(fmt)
            logger.debug(f"[set_input_format] >>> 调用 setCurrentCharFormat({format_name}格式)，"
                         f"currentCharFormat font size={self.currentCharFormat().font().pointSize()}pt")

            # setBlockFormat 和 setBlockCharFormat 会修改文档，如果在 cursorPositionChanged 信号处理函数里
            # 同步调用，会导致 Qt 内部撤销正在进行的回车操作（换行丢失）。
            # 使用 QTimer.singleShot(0) 延迟到当前事件处理完成后再执行，避免干扰回车操作。
            from PyQt6.QtCore import QTimer
            from PyQt6.QtGui import QFontMetrics
            _font = fmt.font()
            if _font.pointSize() <= 0 and _font.pixelSize() <= 0:
                _font = self.document().defaultFont()
            _line_height = QFontMetrics(_font).height()
            _fmt_copy = QTextCharFormat(fmt)
            _block_number = current_block.blockNumber()

            def _apply_block_format():
                c = self.textCursor()
                b = c.block()
                doc_block_count = self.document().blockCount()
                logger.debug(f"[_apply_block_format] 延迟回调触发: 当前block_number={b.blockNumber()}, "
                             f"期望block_number={_block_number}, block_text={repr(b.text())}, "
                             f"文档总行数={doc_block_count}, cursor_pos={c.position()}")
                # 只在光标仍在同一块且块仍为空时才应用格式，避免误操作
                if b.blockNumber() == _block_number and b.text() == "":
                    block_fmt = QTextBlockFormat()
                    block_fmt.setLineHeight(_line_height, QTextBlockFormat.LineHeightTypes.MinimumHeight.value)
                    logger.debug(f"[_apply_block_format] 条件满足，执行 setBlockFormat，_line_height={_line_height}")
                    self.blockSignals(True)
                    c.setBlockFormat(block_fmt)
                    c.setBlockCharFormat(_fmt_copy)
                    self.setTextCursor(c)
                    self.setCurrentCharFormat(_fmt_copy)
                    self.blockSignals(False)
                    logger.debug(f"[_apply_block_format] 执行完毕，文档总行数={self.document().blockCount()}, "
                                 f"cursor_pos={self.textCursor().position()}")
                else:
                    logger.debug(f"[_apply_block_format] 条件不满足，跳过格式设置: "
                                 f"block_number={b.blockNumber()} vs {_block_number}, "
                                 f"block_text={repr(b.text())}, 文档总行数={doc_block_count}")

            QTimer.singleShot(0, _apply_block_format)
            logger.debug(f"[set_input_format] {format_name}行为空，已设置输入格式，延迟执行 setBlockFormat，"
                         f"block_text={repr(block_text)}")
        else:
            logger.debug(f"[set_input_format] {format_name}行不为空，不需要真正设置格式， "
                         f"block_text={repr(block_text[:50])}")

    def setCursorPosition(self, position):
        """设置光标位置的封装方法
        
        Args:
            position: 要设置的光标位置（整数）
        
        功能：
            1. 确保位置不超过文档长度
            2. 设置光标到指定位置，触发 cursorPositionChanged 信号（如果位置发生变化）
            3. 设置光标焦点，触发focusInEvent事件
        """
        # 确保位置不超过文档长度
        max_position = len(self.toPlainText())
        safe_position = min(int(position), max_position)
        
        logger.debug(f"[setCursorPosition] 设置光标位置: requested={position}, "
                     f"max={max_position}, final={safe_position}")
        
        # 创建新光标并设置位置
        cursor = self.textCursor()
        cursor.setPosition(safe_position)

        # 这儿设置光标，如果位置发生变化，会触发cursorPositionChanged事件，调用update_title_and_input_format函数

        self.blockSignals(True)
        self.setTextCursor(cursor)
        self.blockSignals(False)
        
        # 应用光标并设置焦点，不设置焦点光标不会闪烁，会触发focusInEvent事件，调用update_title_and_input_format函数
        logger.debug(f"[setCursorPosition] 设置光标焦点")
        self.setFocus()
    # 1. cursorPositionChanged事件处理函数，设置光位位置或者键盘、鼠标输入事件触发
    # 2. 在新加载note时，如果文档是空的光标默认设置到标题行结尾（位置0）时需要手工触发（因为这时候不会触发cursorPositionChanged事件）
    def update_title_and_input_format(self):
        """根据光标位置设置输入格式
        
        触发时机：
        1. cursorPositionChanged 事件触发时（光标位置改变、键盘/鼠标输入）
        2. 新加载 note 时，如果文档为空且光标在标题行结尾时需手动触发
        
        功能说明：
        - 如果光标有选区，跳过格式设置（避免影响选区内容）
        - 如果光标在标题行（第0行）并且标题行为空，设置标题输入格式（28pt 粗体）
        - 如果光标在正文第一行（第1行）并且内容为空，设置正文输入格式（继承当前块格式）
        - 如果光标在正文其他行（第2行及以后），跳过格式设置（不做任何操作）
        
        注意：此函数仅设置输入格式，不修改已有文本的格式
        """
        # Debug: 打印调用栈
        logger.debug("=== update_title_and_input_format called ===")
        # logger.debug("Backtrace:\n%s", ''.join(traceback.format_stack()))

        # 获取当前光标
        current_cursor = self.textCursor()
        cursor_position = current_cursor.position()
        
        # 如果有选区，不执行格式化（避免影响选区内容）
        if current_cursor.hasSelection():
            logger.debug(f"[update_title_and_input_format] 光标有选区，跳过格式化: position={cursor_position}, "
                         f"selection_start={current_cursor.selectionStart()}, "
                         f"selection_end={current_cursor.selectionEnd()}")
            return
        
        current_block = current_cursor.block()
        current_block_number = current_block.blockNumber()
        current_block_text = current_block.text()
        
        logger.debug(f"[update_title_and_input_format] 光标信息: position={cursor_position}, "
                     f"block_number={current_block_number}, block_text='{repr(current_block_text[:50])}...' (前50字符)")

        # 根据光标位置设置当前输入格式
        if current_block_number == 0:
            logger.debug("[update_title_and_input_format] 光标在第一行，尝试设置标题输入格式")
            self.set_input_format(current_cursor, current_block, True)
        elif current_block_number == 1:
            logger.debug(f"[update_title_and_input_format] 光标在正文第一行（第{current_block_number}行），尝试设置正文输入格式")
            self.set_input_format(current_cursor, current_block, False)
        else:
            logger.debug(f"[update_title_and_input_format] 光标在正文其他行（第{current_block_number}行），跳过格式设置, "
                         f"block_text={repr(current_block_text[:50])}...")

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
            # 获取表格宽度信息
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
            
            # 计算表格边界
            border_width = table_format.border()
            cell_padding = table_format.cellPadding()
            
            left = top_left_rect.left() - border_width - cell_padding
            top = top_left_rect.top() - border_width - cell_padding
            # 遍历最后一行所有单元格，取最大 bottom（避免嵌套表格撑高某列导致右下角单元格bottom偏小）
            last_row = table.rows() - 1
            raw_bottom = 0
            for col in range(table.columns()):
                cell = table.cellAt(last_row, col)
                if cell.isValid():
                    cell_last_rect = self.cursorRect(cell.lastCursorPosition())
                    if cell_last_rect.bottom() > raw_bottom:
                        raw_bottom = cell_last_rect.bottom()
            bottom = raw_bottom + border_width + cell_padding
            # 计算右边界
            document = self.document()
            root_frame = document.rootFrame()
            parent_frame = table.parentFrame()
            is_nested = parent_frame and parent_frame != root_frame

            if is_nested:
                from PyQt6.QtGui import QTextTable
                parent_table = None
                frame = parent_frame
                while frame and frame != root_frame:
                    if isinstance(frame, QTextTable):
                        parent_table = frame
                        break
                    frame = frame.parentFrame()
                # 嵌套表格：直接通过父单元格的最后字符的光标矩形右边界作为nested表格的右边界
                parent_cell_last_rect = self.cursorRect(parent_table.cellAt(top_left_cursor).lastCursorPosition())
                right = parent_cell_last_rect.right()
            else:
                # 顶层表格：使用文档宽度计算
                doc_layout = document.documentLayout()
                doc_size = doc_layout.documentSize()
                doc_width = doc_size.width()

                root_frame_format = root_frame.frameFormat()
                # 获取文档左右边距
                doc_left_margin = root_frame_format.leftMargin()
                doc_right_margin = root_frame_format.rightMargin()
                # 获取文档内容最大宽度
                content_width = doc_width - doc_left_margin - doc_right_margin

                # 根据表格宽度类型计算实际宽度
                if table_width_length.type() == QTextLength.Type.PercentageLength:
                    percentage = table_width_length.rawValue()
                    table_total_width = content_width * percentage / 100.0
                elif table_width_length.type() == QTextLength.Type.FixedLength:
                    table_total_width = table_width_length.rawValue()
                else:
                    table_total_width = content_width

                right = left + table_total_width - cell_padding

            # 创建矩形
            table_rect = QRectF(left, top, right - left, bottom - top)
            
            return table_rect
            
        except Exception as e:
            print(f"[ERROR] get_table_rect exception: {e}")
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
                    note_id = self._get_current_note_id()
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
    # 窗口显示、被遮挡后重新显示、窗口大小变化、滚动内容、系统主题/DPI变化（系统外观变化导致控件需要重绘）、代码调用update()、repaint()
    # 等情况时都触发重绘，在选择表格self.selected_table时会调用self.viewport().update()来触发重绘，在点击图片、取消选中、
    # 编辑器内容变化、鼠标移动/滚动（Qt内部判断是否需要重绘）等情况时会触发重绘
    def paintEvent(self, event):
        """绘制事件 - 绘制选中图片的边界框，以及修正空行光标高度"""
        # import traceback
        # caller_stack = ''.join(traceback.format_stack(limit=6)[:-1])  # 取最近5层调用栈
        # logger.debug(f"[paintEvent] 触发重绘，_cursor_blink_visible={self._cursor_blink_visible}\n调用栈:\n{caller_stack}")
        # 提前收集自定义光标信息（必须在 super().paintEvent() 之前，此时 cursor_rect 位置准确）
        cursor_draw_info = self._collect_cursor_draw_info()
        super().paintEvent(event)

        self._paint_custom_cursor(cursor_draw_info)
        self._paint_selected_table()
        self._paint_selected_image()
        self._paint_drag_preview()
        self._paint_bullet_dots()
        self._paint_checklist_circles()

    def _collect_cursor_draw_info(self):
        """收集自定义光标的绘制信息（需在 super().paintEvent() 之前调用）
        Returns:
            tuple: (cursor_rect, draw_height, draw_top) 或 None
        """
        from PyQt6.QtGui import QFontMetrics

        if not self.hasFocus() or self.isReadOnly():
            return None

        # 表格选中时不绘制光标
        if self.selected_table:
            return None

        cursor = self.textCursor()
        if cursor.hasSelection():
            return None

        cursor_rect = self.cursorRect(cursor)
        block_number = cursor.block().blockNumber()
        if (block_number == 0 or block_number == 1) and cursor.block().text() == "":
            fmt = self.currentCharFormat()
            font = fmt.font()
            block_char_fmt = cursor.blockCharFormat()
            block_char_font = block_char_fmt.font()
            logger.debug(f"[paintEvent] >>> 空行字体信息: "
                         f"currentCharFormat font={font.family()} size={font.pointSize()}pt pixelSize={font.pixelSize()}px | "
                         f"blockCharFormat font={block_char_font.family()} size={block_char_font.pointSize()}pt pixelSize={block_char_font.pixelSize()}px")
            if font.pointSize() <= 0 and font.pixelSize() <= 0:
                font = self.document().defaultFont()
                logger.debug(f"[paintEvent] currentCharFormat 字体未设置，使用文档默认字体: "
                             f"{font.family()} {font.pointSize()}pt")
            fm = QFontMetrics(font)
            font_height = fm.height()
            line_height = cursor_rect.height()
            # logger.debug(f"[paintEvent] font={font.family()} size={font.pointSize()}pt "
            #              f"pixelSize={font.pixelSize()}px, font_height={font_height}, "
            #              f"line_height={line_height}")
            # 行内容为空时，光标高度可能因为还没有输入字符导致比要输入的字符格式小，所以要按字符格式大小重绘
            if font_height > line_height:
                # 大光标：顶部对齐，向下延伸 font_height
                cursor_rect.setBottom(cursor_rect.top() + font_height - 1)
            return cursor_rect, font_height, cursor_rect.top()
        else:
            # 有文字的行：
            # - 正常移动光标时，使用 currentCharFormat（跟随光标左侧字符格式）
            # - 手动设置格式后（_manual_format_pt > 0），使用记录的目标字号，绘制后清除标志
            if self._manual_format_pt > 0:
                # 手动设置格式场景：使用目标字号构造字体
                font = QFont(self.document().defaultFont())
                font.setPointSize(self._manual_format_pt)
                self._manual_format_pt = 0  # 消费后立即清除，下次移动光标恢复正常逻辑
            else:
                # 正常移动光标场景：跟随光标左侧字符格式
                fmt = self.currentCharFormat()
                font = fmt.font()
                if font.pointSize() <= 0 and font.pixelSize() <= 0:
                    font = self.document().defaultFont()

            fm = QFontMetrics(font)
            font_height = fm.height()
            line_height = cursor_rect.height()
            if font_height < line_height:
                # 光标字体比行高小：基于文字基线居中，使光标中心与文字中心对齐
                draw_top = cursor_rect.bottom() - fm.descent() - fm.ascent() // 2 - font_height // 2
                return cursor_rect, font_height, draw_top
            elif font_height > line_height:
                # 光标字体比行高大（如手动设置标题格式但行内容还是正文行高）：垂直居中于当前行
                draw_top = cursor_rect.top() + (line_height - font_height) // 2
                return cursor_rect, font_height, draw_top
            return cursor_rect, font_height, cursor_rect.top()

    def _paint_custom_cursor(self, cursor_draw_info):
        """绘制自定义光标

        Args:
            cursor_draw_info: _collect_cursor_draw_info() 返回的元组，或 None
        """
        from PyQt6.QtGui import QPainter

        if cursor_draw_info is None:
            return

        cursor_rect, draw_height, draw_top = cursor_draw_info
        cursor_color = self.palette().color(self.palette().ColorRole.Text)
        painter = QPainter(self.viewport())
        # logger.debug(f"[_paint_custom_cursor] _cursor_blink_visible={self._cursor_blink_visible}，{'绘制' if self._cursor_blink_visible else '跳过'}光标")
        if self._cursor_blink_visible:
            # logger.debug(f"[paintEvent] 绘制光标: left={cursor_rect.left()}, top={draw_top}, height={draw_height}")
            painter.fillRect(cursor_rect.left(), draw_top, 1, draw_height, cursor_color)
        painter.end()

    def _paint_selected_table(self):
        """绘制选中表格的蓝色边界框"""
        from PyQt6.QtGui import QPainter, QPen, QColor

        if not self.selected_table or not self.selected_table_cursor:
            return

        table_rect = self.get_table_rect(self.selected_table)
        if not table_rect:
            return

        painter = QPainter(self.viewport())
        pen = QPen(QColor("#007AFF"), 3)
        painter.setPen(pen)
        painter.drawRect(table_rect)
        painter.end()

    def _paint_selected_image(self):
        """绘制选中图片的边界框和8个缩放控制点"""
        from PyQt6.QtGui import QPainter, QPen, QColor

        if not self.selected_image or not self.selected_image_cursor:
            return

        # 实时计算图片位置（确保滚动时位置正确）
        self.selected_image_rect = self.get_image_rect_at_cursor(self.selected_image_cursor)
        if not self.selected_image_rect:
            return

        painter = QPainter(self.viewport())

        # 绘制边界框
        pen = QPen(QColor("#007AFF"), 2)
        painter.setPen(pen)
        painter.drawRect(self.selected_image_rect)

        # 绘制8个控制点
        painter.setBrush(QColor("#007AFF"))
        for handle_rect in self.get_resize_handles().values():
            painter.drawRect(handle_rect)

        painter.end()

    def _paint_drag_preview(self):
        """绘制拖动预览指示器（虚线 + 两端三角箭头）"""
        from PyQt6.QtGui import QPainter, QPen, QColor, QPolygon
        from PyQt6.QtCore import QPoint

        # 图片拖动预览：垂直虚线（行内插入位置）
        if self.dragging and self.drag_preview_cursor:
            self._paint_image_drop_indicator(self.drag_preview_cursor)

        # 表格拖动预览：水平虚线（块级插入位置）
        if self.table_dragging and self.table_drag_preview_cursor:
            self._paint_table_drop_indicator(self.table_drag_preview_cursor)

    def _paint_image_drop_indicator(self, preview_cursor):
        """绘制图片拖放指示器（垂直虚线 + 两端三角箭头）"""
        from PyQt6.QtGui import QPainter, QPen, QColor, QPolygon
        from PyQt6.QtCore import QPoint

        preview_rect = self.cursorRect(preview_cursor)
        x = preview_rect.left()
        y_start = preview_rect.top() - 5
        y_end = preview_rect.bottom() + 5

        painter = QPainter(self.viewport())

        # 绘制垂直虚线，表示图片将被插入的字符位置
        pen = QPen(QColor("#007AFF"), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPoint(x, y_start), QPoint(x, y_end))

        # 在指示线两端绘制小三角形
        painter.setBrush(QColor("#007AFF"))
        painter.setPen(Qt.PenStyle.NoPen)
        top_triangle = QPolygon([
            QPoint(x, y_start),
            QPoint(x - 4, y_start - 6),
            QPoint(x + 4, y_start - 6)
        ])
        painter.drawPolygon(top_triangle)

        bottom_triangle = QPolygon([
            QPoint(x, y_end),
            QPoint(x - 4, y_end + 6),
            QPoint(x + 4, y_end + 6)
        ])
        painter.drawPolygon(bottom_triangle)

        painter.end()

    def _paint_table_drop_indicator(self, preview_cursor):
        """绘制表格拖放指示器（水平虚线 + 左端三角箭头）"""
        from PyQt6.QtGui import QPainter, QPen, QColor, QPolygon
        from PyQt6.QtCore import QPoint

        preview_rect = self.cursorRect(preview_cursor)
        # 获取目标行的完整宽度范围
        block = preview_cursor.block()
        block_cursor = QTextCursor(block)
        block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        block_start_rect = self.cursorRect(block_cursor)

        y = preview_rect.top() - 2  # 在目标行上方绘制水平线
        x_start = block_start_rect.left()
        x_end = self.viewport().width() - 10

        painter = QPainter(self.viewport())

        # 绘制水平虚线，表示表格将被插入的行位置
        pen = QPen(QColor("#007AFF"), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPoint(x_start, y), QPoint(x_end, y))

        # 在指示线左端绘制小三角形（向右的箭头）
        painter.setBrush(QColor("#007AFF"))
        painter.setPen(Qt.PenStyle.NoPen)
        left_triangle = QPolygon([
            QPoint(x_start, y),
            QPoint(x_start - 6, y - 4),
            QPoint(x_start - 6, y + 4)
        ])
        painter.drawPolygon(left_triangle)

        painter.end()
    
    def _iter_list_blocks(self, prefixes):
        """遍历文档中以指定前缀开头的可见块，返回 (block, char_rect, fm, prefix) 迭代器"""
        from PyQt6.QtGui import QFontMetrics

        doc = self.document()
        viewport_height = self.viewport().rect().height()
        block = doc.begin()
        while block.isValid():
            t = block.text()
            prefix = next((p for p in prefixes if t.startswith(p)), None)
            if prefix is None:
                block = block.next()
                continue

            tmp_cursor = QTextCursor(block)
            tmp_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            char_rect = self.cursorRect(tmp_cursor)

            if char_rect.bottom() < 0 or char_rect.top() > viewport_height:
                block = block.next()
                continue

            char_font = tmp_cursor.charFormat().font()
            if not char_font.family():
                char_font = self.document().defaultFont()
            fm = QFontMetrics(char_font)

            yield block, char_rect, fm, prefix
            block = block.next()

    def _calc_circle_rect(self, char_rect, fm, size):
        """根据行首 cursorRect 和字体度量计算圆形绘制区域"""
        from PyQt6.QtCore import QRectF
        font_height = fm.height()
        baseline_y = char_rect.bottom() - fm.descent()
        x = char_rect.left() + 1
        y = baseline_y - fm.ascent() + (font_height - size) / 2
        return QRectF(x, y, size, size)

    def _ensure_prefix_transparent(self, block, prefix):
        """确保前缀字符颜色为透明（处理从文件加载的旧数据）"""
        from PyQt6.QtGui import QColor
        tmp_cursor = QTextCursor(block)
        tmp_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        tmp_cursor.movePosition(
            QTextCursor.MoveOperation.NextCharacter,
            QTextCursor.MoveMode.KeepAnchor,
            len(prefix)
        )
        if tmp_cursor.charFormat().foreground().color() != QColor(0, 0, 0, 0):
            fix_fmt = QTextCharFormat()
            fix_fmt.setForeground(QColor(0, 0, 0, 0))
            tmp_cursor.mergeCharFormat(fix_fmt)

    def _fix_all_list_prefix_colors(self):
        """加载笔记后一次性修复所有列表前缀颜色为透明。

        此方法应在 setHtml 之后调用，而不是在 paintEvent 中调用，
        避免在绘制期间修改文档内容导致无限重绘循环。
        """
        PREFIXES = ["\u2022 ", "\u25cb ", "\u25cf "]  # • ○ ●
        from PyQt6.QtGui import QColor
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            t = block.text()
            prefix = next((p for p in PREFIXES if t.startswith(p)), None)
            if prefix is not None:
                self._ensure_prefix_transparent(block, prefix)
            block = block.next()

    def _reset_transparent_cursor_fmt(self, prefixes):
        """若光标紧跟在列表前缀末尾且格式为透明色，重置为正常颜色，防止后续输入不可见"""
        from PyQt6.QtGui import QColor
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        cur_block = cursor.block()
        t = cur_block.text()
        prefix = next((p for p in prefixes if t.startswith(p)), None)
        if prefix is None:
            return
        pos_in_block = cursor.position() - cur_block.position()
        if pos_in_block == len(prefix):
            if cursor.charFormat().foreground().color() == QColor(0, 0, 0, 0):
                normal_fmt = QTextCharFormat()
                normal_fmt.setForeground(self.palette().color(self.palette().ColorRole.Text))
                self.setCurrentCharFormat(normal_fmt)

    def _paint_bullet_dots(self):
        """在项目符号列表行首绘制更大的实心圆点（覆盖原 • 字符）"""
        from PyQt6.QtGui import QPainter, QColor, QBrush

        BULLET_PREFIX = "\u2022 "  # • 

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for block, char_rect, fm, prefix in self._iter_list_blocks([BULLET_PREFIX]):
            # 圆点直径：字体高度的 38%，最小5px，最大10px
            font_height = fm.height()
            dot_size = max(5, min(10, int(font_height * 0.38)))
            # 圆点水平位置居中于前缀半宽，x 偏移与 _calc_circle_rect 不同，单独计算
            baseline_y = char_rect.bottom() - fm.descent()
            dot_x = char_rect.left() + (font_height * 0.5 - dot_size) / 2 + 1
            dot_y = baseline_y - fm.ascent() + (font_height - dot_size) / 2
            from PyQt6.QtCore import QRectF
            dot_rect = QRectF(dot_x, dot_y, dot_size, dot_size)

            # 取正文部分文字颜色（跳过 • 字符，取后面的文字颜色）
            text_cursor = QTextCursor(block)
            text_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            text_cursor.movePosition(
                QTextCursor.MoveOperation.NextCharacter,
                QTextCursor.MoveMode.MoveAnchor,
                len(prefix)
            )
            text_color = text_cursor.charFormat().foreground().color()
            if not text_color.isValid() or text_color == QColor(0, 0, 0, 0):
                text_color = self.palette().color(self.palette().ColorRole.Text)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(text_color))
            painter.drawEllipse(dot_rect)

        painter.end()
        self._reset_transparent_cursor_fmt([BULLET_PREFIX])

    def _paint_checklist_circles(self):
        """在核对清单行首绘制高质量圆圈图标（覆盖原Unicode字符）"""
        from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath

        UNCHECKED = "○ "
        CHECKED = "● "

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for block, char_rect, fm, prefix in self._iter_list_blocks([UNCHECKED, CHECKED]):
            font_height = fm.height()
            circle_size = min(font_height - 2, 16)  # 圆圈直径，最大16px
            circle_rect = self._calc_circle_rect(char_rect, fm, circle_size)

            if prefix == CHECKED:
                # 选中状态：黄色实心圆 + 白色对号
                painter.setPen(QPen(QColor("#FFB800"), 1.5))
                painter.setBrush(QBrush(QColor("#FFB800")))
                painter.drawEllipse(circle_rect)

                # 绘制白色对号
                pen = QPen(QColor("white"), circle_size * 0.13, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                cx = circle_rect.center().x()
                cy = circle_rect.center().y()
                r = circle_size / 2
                path = QPainterPath()
                path.moveTo(cx - r * 0.38, cy)
                path.lineTo(cx - r * 0.05, cy + r * 0.32)
                path.lineTo(cx + r * 0.42, cy - r * 0.28)
                painter.drawPath(path)
            else:
                # 未选中状态：白色背景 + 灰色圆形边框
                painter.setBrush(QBrush(QColor("white")))
                painter.setPen(QPen(QColor("#AAAAAA"), 1.5))
                painter.drawEllipse(circle_rect)

        painter.end()
        self._reset_transparent_cursor_fmt([UNCHECKED, CHECKED])

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
    
    # 重写的焦点获得事件处理函数，当编辑器获得焦点时会触发（第一次加载后设置光标或者鼠标点击时触发）
    # 编辑器获得焦点后，再点击鼠标就不再会触发了，只会触发mousePressEvent
    def focusInEvent(self, event):
        """焦点获得事件：验证笔记状态并恢复标题格式"""
        logger.debug("[focusInEvent] 焦点获得事件触发")
        
        # 验证是否允许获得焦点
        if not self._can_accept_focus():
            logger.debug("[focusInEvent] 拒绝焦点：没有打开的笔记")
            event.ignore()
            return

        # 调用父类处理
        super().focusInEvent(event)

        # 如果光标在空的第一行，恢复标题格式
        self.update_title_and_input_format()

        # 启动自定义光标闪烁
        self._start_cursor_blink()
        logger.debug("[focusInEvent] 焦点处理完成")

    def focusOutEvent(self, event):
        """焦点失去事件：停止光标闪烁"""
        super().focusOutEvent(event)
        self._stop_cursor_blink()
        logger.debug("[focusOutEvent] 焦点失去，停止光标闪烁")

    def _can_accept_focus(self) -> bool:
        """检查编辑器是否可以接受焦点
        
        Returns:
            如果当前有打开的笔记返回True，否则返回False
        """
        if not (hasattr(self, 'parent_editor') and self.parent_editor):
            return True
        
        return bool(self._get_current_note_id())
    
    # def _restore_title_format_if_needed(self):
    #     """如果光标在空的第一行，恢复标题格式"""
    #     cursor = self.textCursor()
    #
    #     # 只处理第一行
    #     if cursor.block().blockNumber() != 0:
    #         return
    #
    #     # 检查第一行是否为空（包括零宽字符）
    #     block_text = cursor.block().text()
    #     if not self._is_empty_title_line(block_text):
    #         return
    #
    #     # 应用标题格式
    #     self._apply_title_format()
    
    # def _is_empty_title_line(self, text: str) -> bool:
    #     """判断是否为空的标题行
    #
    #     Args:
    #         text: 行文本内容
    #
    #     Returns:
    #         如果是空行或只包含零宽字符返回True
    #     """
    #     return text == "" or text == "\u200B"
    
    # def _apply_title_format(self):
    #     """应用标题格式（28pt + 粗体）"""
    #     char_fmt = QTextCharFormat()
    #     char_fmt.setFontPointSize(28)  # 标题字号
    #     char_fmt.setFontWeight(QFont.Weight.Bold)  # 粗体
    #     self.setCurrentCharFormat(char_fmt)

    def _handle_checklist_click(self, event) -> bool:
        """检测鼠标是否点击了核对清单行首的复选框字符，如果是则切换选中状态

        Returns:
            如果处理了复选框点击返回True，否则返回False
        """
        UNCHECKED = "○ "
        CHECKED = "● "
        cursor = self.cursorForPosition(event.pos())
        block = cursor.block()
        t = block.text()
        if not (t.startswith(UNCHECKED) or t.startswith(CHECKED)):
            return False
        # 判断点击位置是否在行首圆圈字符范围内（前2个字符）
        block_start = block.position()
        click_pos = cursor.position() - block_start
        if click_pos < len(UNCHECKED):
            # 点击了圆圈区域（不含后面的空格），切换状态
            c = QTextCursor(block)
            # 透明格式（圆圈字符不可见，由paintEvent绘制）
            invis_fmt = QTextCharFormat()
            invis_fmt.setForeground(QColor(0, 0, 0, 0))
            invis_fmt.setBackground(Qt.GlobalColor.transparent)
            if t.startswith(UNCHECKED):
                # 切换为选中：替换○为●
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.movePosition(QTextCursor.MoveOperation.NextCharacter,
                               QTextCursor.MoveMode.KeepAnchor, len(UNCHECKED))
                c.removeSelectedText()
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.setCharFormat(invis_fmt)
                c.insertText(CHECKED)
            else:
                # 切换为未选中：替换●为○
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.movePosition(QTextCursor.MoveOperation.NextCharacter,
                               QTextCursor.MoveMode.KeepAnchor, len(CHECKED))
                c.removeSelectedText()
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.setCharFormat(invis_fmt)
                c.insertText(UNCHECKED)
            self.viewport().update()
            return True
        return False

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
            if not self._get_current_note_id():
                return True
        return False

    def _restore_cursor_visibility(self):
        # 恢复自定义光标闪烁（例如从表格选中状态恢复后）
        if not self._cursor_blink_timer.isActive():
            self._start_cursor_blink()

    def _handle_table_border_click(self, table, cursor, event) -> bool:
        """处理表格边框点击（选中整个表格，或开始拖动已选中的表格）
        
        Returns:
            如果处理了边框点击返回True，否则返回False
        """
        if not self.is_click_on_table_border(event.pos(), table):
            return False
        
        # 如果点击的是已选中的表格边框，开始拖动
        if self.selected_table and self.selected_table == table:
            self.table_dragging = True
            self.table_drag_start_pos = event.pos()
            self.table_drag_preview_cursor = None
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return True

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

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        button_name = event.button().name if hasattr(event.button(), 'name') else str(event.button())
        pos = event.pos()
        logger.debug(f"[mousePressEvent] 鼠标按下事件触发 - 按钮: {button_name}, 位置: ({pos.x()}, {pos.y()})")
        
        # 检查是否应该忽略事件
        if self._should_ignore_mouse_event():
            logger.debug("[mousePressEvent] 忽略鼠标事件：没有打开的笔记")
            event.ignore()
            return
        
        # 标记鼠标已按下
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = True
            logger.debug("[mousePressEvent] 标记鼠标左键已按下")
        
        # 恢复光标显示
        self._restore_cursor_visibility()
        
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击了核对清单的圆圈
            if self._handle_checklist_click(event):
                logger.debug("[mousePressEvent] 处理核对清单复选框点击，事件结束")
                return

            # 首先检查是否点击了链接（附件）
            if self._handle_anchor_click(event):
                logger.debug("[mousePressEvent] 处理链接点击，事件结束")
                return
            
            # 检查是否点击了表格
            cursor = self.cursorForPosition(event.pos())
            table = cursor.currentTable()
            if table:
                logger.debug("[mousePressEvent] 点击了表格区域")
                # 检查是否点击了表格边框
                if self._handle_table_border_click(table, cursor, event):
                    logger.debug("[mousePressEvent] 处理表格边框点击，事件结束")
                    return
                # 点击了表格内容区域，取消表格选中，进入编辑模式
                logger.debug("[mousePressEvent] 处理表格内容点击")
                self._handle_table_content_click(event)
                # 使用默认行为，进入单元格编辑模式
                super().mousePressEvent(event)
                return
            # 取消表格选中
            self._clear_table_selection()

            # 检查是否点击了图片缩放控制点
            if self._handle_image_resize_handle_click(event):
                logger.debug("[mousePressEvent] 处理图片缩放控制点点击，事件结束")
                return
            
            # 检查是否点击了图片中心区域（用于拖动移动）
            if self._handle_image_drag_click(event):
                logger.debug("[mousePressEvent] 处理图片拖动点击，事件结束")
                return
            
            # 检查是否点击了图片
            if self._handle_image_click(event):
                logger.debug("[mousePressEvent] 处理图片点击，事件结束")
                return
            # 取消图片选中
            self._clear_image_selection()
            logger.debug("[mousePressEvent] 点击了普通文本区域")
        # QTextEdit 默认处理，如果光标位置发生了变化会触发cursorPositionChanged事件，
        # 从而调用update_title_and_input_format设置格式
        super().mousePressEvent(event)

        logger.debug("[mousePressEvent] 鼠标按下事件处理完成")
    
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

    def _handle_table_dragging(self, event) -> bool:
        """处理表格拖动移动

        Returns:
            如果正在拖动表格返回True，否则返回False
        """
        if not (self.table_dragging and self.table_drag_start_pos):
            return False

        # 更新预览光标位置
        self.table_drag_preview_cursor = self.cursorForPosition(event.pos())

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
        # 先用光标位置做局部检测，避免全文档遍历
        # 通过鼠标位置获取光标，检查附近是否有图片字符（O(1) 而非 O(n)）
        hover_cursor = self.cursorForPosition(event.pos())
        is_on_image = False
        # 检查光标位置及其前后各1个字符是否是图片字符
        for offset in range(-1, 2):
            check_pos = hover_cursor.position() + offset
            if check_pos < 0:
                continue
            cf = _selected_char_format(self.document(), check_pos)
            if cf and cf.isImageFormat():
                # 进一步确认鼠标确实在图片矩形内
                tmp_cursor = QTextCursor(self.document())
                tmp_cursor.setPosition(check_pos)
                img_rect = self.get_image_rect_at_cursor(tmp_cursor)
                if img_rect and img_rect.contains(event.pos()):
                    is_on_image = True
                    break
        if is_on_image:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            # 检查是否悬停在表格上
            cursor = hover_cursor
            table = cursor.currentTable()
            if table:
                # 检查是否悬停在表格边框上
                if self.is_click_on_table_border(event.pos(), table):
                    # 如果是已选中的表格，显示移动光标
                    if self.selected_table and self.selected_table == table:
                        self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
                    else:
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

        # 处理表格拖动移动
        if self._handle_table_dragging(event):
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

        if self.table_dragging:
            # 计算鼠标移动的距离
            delta = event.pos() - self.table_drag_start_pos

            # 如果移动距离足够大，执行表格移动
            if abs(delta.x()) > 5 or abs(delta.y()) > 5:
                target_cursor = self.cursorForPosition(event.pos())
                self.move_table_to_cursor(target_cursor)

            # 重置拖动状态
            self.table_dragging = False
            self.table_drag_start_pos = None
            self.table_drag_preview_cursor = None
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            self.viewport().update()

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
    
    def _parse_math_formula_metadata(self, image_name):
        """解析公式图片的元数据
        
        Args:
            image_name: 图片名称，格式为 "xxx|||MATH:type:code"
            
        Returns:
            tuple: (formula_type, code) 或 (None, None)
        """
        if '|||MATH:' not in image_name:
            return None, None
        
        parts = image_name.split('|||', 1)
        if len(parts) != 2:
            return None, None
        
        metadata = parts[1]  # MATH:type:code
        
        # 解析元数据
        if not metadata.startswith('MATH:'):
            return None, None
        
        metadata_parts = metadata[5:].split(':', 1)  # 去掉 'MATH:' 前缀
        if len(metadata_parts) != 2:
            return None, None
        
        formula_type = metadata_parts[0]
        escaped_code = metadata_parts[1]
        # 反转义HTML实体
        code = html.unescape(escaped_code)
        
        return formula_type, code
    
    def _handle_math_formula_double_click(self, image_format, image_cursor):
        """处理双击公式图片
        
        Args:
            image_format: 图片格式对象
            image_cursor: 图片光标位置
            
        Returns:
            bool: 是否成功处理
        """
        image_name = image_format.name()
        formula_type, code = self._parse_math_formula_metadata(image_name)
        
        if formula_type and code and self.parent_editor:
            self.parent_editor.edit_math_formula(
                code, formula_type, image_cursor, image_format
            )
            return True
        
        return False
    
    def _handle_image_double_click(self, event):
        """处理双击图片事件
        
        Args:
            event: 鼠标事件
            
        Returns:
            bool: 是否处理了图片双击
        """
        image_format, image_cursor, image_rect = self.find_image_at_position(event.pos())
        
        if not (image_format and image_cursor):
            return False
        
        # 检查是否是公式图片
        if self._handle_math_formula_double_click(image_format, image_cursor):
            event.accept()
            return True
        
        # 普通图片，只选中图片，不执行其他操作
        self.selected_image = image_format
        self.selected_image_cursor = image_cursor
        self.selected_image_rect = image_rect
        self.viewport().update()
        # 阻止默认的双击行为（选中文字等）
        event.accept()
        return True
    
    def _handle_anchor_double_click(self, event):
        """处理双击链接（附件）事件
        
        Args:
            event: 鼠标事件
            
        Returns:
            bool: 是否处理了链接双击
        """
        cursor = self.cursorForPosition(event.pos())
        char_format = cursor.charFormat()
        
        if not char_format.isAnchor():
            return False
        
        anchor_href = char_format.anchorHref()
        if anchor_href:
            self.open_attachment(anchor_href)
            event.accept()
            return True
        
        return False
    
    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件 - 防止双击图片时被删除"""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        
        # 处理双击图片
        if self._handle_image_double_click(event):
            return
        
        # 处理双击链接（附件）
        if self._handle_anchor_double_click(event):
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

            # 使用 setPosition + KeepAnchor 方式，可以跨越 frame 边界选中整个表格
            # movePosition 无法跨越 frame 边界，会导致选区不完整
            # Qt的富文本文档模型（QTextDocument）中，文档内容被组织成一棵树形结构，QTextFrame 是这棵树中的一个容器节点，
            # 用于将一段内容"框"起来，与文档的其他部分隔离。QTextDocument文档结构如下：
            # QTextDocument
            # └── QTextFrame (根 frame，整个文档)
            #     ├── QTextBlock (普通段落)
            #     ├── QTextBlock (普通段落)
            #     ├── QTextTable (继承自 QTextFrame) ← 表格
            #     │   ├── QTextTableCell
            #     │   │   └── QTextBlock
            #     │   └── QTextTableCell
            #     │       └── QTextBlock
            #     └── QTextBlock (普通段落)
            cursor.setPosition(table_start)
            cursor.setPosition(table_end + 1, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()

    def _restore_cursor_and_clear_table_selection(self, event):
        """恢复光标显示并清除表格选中状态"""
        if self.selected_table:
            self.selected_table = None
            self.selected_table_cursor = None
            self.viewport().update()
        # 恢复光标显示
        self._restore_cursor_visibility()
    
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
                note_id = self._get_current_note_id()
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
            logger.debug("[_handle_selected_table_deletion] 无选中表格，跳过")
            return False

        # 如果当前光标在表格内，说明用户正在编辑单元格内容
        if current_table == self.selected_table:
            logger.debug("[_handle_selected_table_deletion] 光标在表格内，转发给父类处理")
            super().keyPressEvent(event)
            return True

        # 删除整个表格（第二次按删除键）
        logger.debug(f"[_handle_selected_table_deletion] 准备删除表格: selected_table={self.selected_table}")
        self.delete_entire_table(self.selected_table)

        # 清除选中状态
        self.selected_table = None
        self.selected_table_cursor = None
        # 删除表格完成后恢复自定义光标闪烁
        self._start_cursor_blink()
        self.viewport().update()

        event.accept()
        return True

    def _collect_all_tables(self, frame):
        """递归收集指定 frame 下所有的表格（包括嵌套表格）

        Args:
            frame: 起始 QTextFrame

        Returns:
            list: 所有找到的表格列表
        """
        tables = []
        for child_frame in frame.childFrames():
            # 如果有cellAt方法，说明这个frame本身是个表格
            if hasattr(child_frame, 'cellAt'):
                # 是表格
                tables.append(child_frame)
                # 继续递归查找表格内的嵌套表格
                tables.extend(self._collect_all_tables(child_frame))
            else:
                tables.extend(self._collect_all_tables(child_frame))
        return tables

    def _handle_table_selection(self, event, cursor_pos):
        """处理表格选中（第一次按删除键）

        返回：True 表示已处理，False 表示未处理
        """
        # 递归收集文档中所有表格（包括嵌套在单元格内的表格）
        all_tables = self._collect_all_tables(self.document().rootFrame())

        for table in all_tables:
            table_start = table.firstPosition()
            table_end = table.lastPosition()

            logger.debug(f"[_handle_table_selection] cursor_pos={cursor_pos}, table_start={table_start}, table_end={table_end}")

            # 检查光标是否紧邻表格
            is_before_table = (event.key() == Qt.Key.Key_Delete and
                              cursor_pos == table_start - 1)
            is_after_table = (event.key() == Qt.Key.Key_Backspace and
                             cursor_pos == table_end + 1)

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

                # 隐藏自定义光标（表格选中状态下不显示光标）
                self._stop_cursor_blink()
                self.viewport().update()

                event.accept()
                return True

        return False

    def _handle_delete_key_press(self, event):
        """处理删除键按下事件

        Args:
            event: 键盘事件对象

        Returns:
            bool: 如果事件已被处理返回True，否则返回False
        """
        logger.debug(f"[_handle_delete_key_press] 检测到删除键: {'Delete' if event.key() == Qt.Key.Key_Delete else 'Backspace'}")

        current_cursor = self.textCursor()

        # 1. 处理附件删除
        logger.debug("[_handle_delete_key_press] 检查是否需要删除附件")
        if self._handle_attachment_deletion(event, current_cursor):
            logger.debug("[_handle_delete_key_press] 附件删除已处理，返回")
            return True

        # 2. 处理已选中表格的删除（第二次按删除键）
        logger.debug("[_handle_delete_key_press] 检查是否需要删除已选中的表格")
        if self._handle_selected_table_deletion(event, current_cursor.currentTable()):
            logger.debug("[_handle_delete_key_press] 已选中表格删除已处理，返回")
            return True

        # 3. 处理表格选中（第一次按删除键）
        cursor_pos = current_cursor.position()
        logger.debug(f"[_handle_delete_key_press] 检查是否需要选中表格 - cursor_pos: {cursor_pos}")
        if self._handle_table_selection(event, cursor_pos):
            logger.debug("[_handle_delete_key_press] 表格已选中，返回")
            return True

        # 4. 处理项目符号列表前缀的退格键
        if not current_cursor.hasSelection() and event.key() == Qt.Key.Key_Backspace:
            block = current_cursor.block()
            BULLET_PREFIX = "\u2022 "  # • 
            if block.text().startswith(BULLET_PREFIX):
                block_start = block.position()
                pos_in_block = current_cursor.position() - block_start
                prefix_len = len(BULLET_PREFIX)
                if pos_in_block <= prefix_len:
                    # 光标在 • 前缀范围内或紧跟其后，直接取消项目符号列表
                    logger.debug("[_handle_delete_key_press] 光标在项目符号前缀内，取消项目符号列表")
                    self.parent().toggle_bullet_list()
                    event.accept()
                    return True

        # 5. 处理检查清单前缀的退格键
        if not current_cursor.hasSelection() and event.key() == Qt.Key.Key_Backspace:
            block = current_cursor.block()
            UNCHECKED_PREFIX = "○ "  # 未选中
            CHECKED_PREFIX = "● "   # 已选中
            block_text = block.text()
            if block_text.startswith(UNCHECKED_PREFIX) or block_text.startswith(CHECKED_PREFIX):
                block_start = block.position()
                pos_in_block = current_cursor.position() - block_start
                prefix_len = len(UNCHECKED_PREFIX)  # 两者长度相同
                if pos_in_block <= prefix_len:
                    # 光标在检查清单前缀范围内或紧跟其后，直接取消检查清单
                    logger.debug("[_handle_delete_key_press] 光标在检查清单前缀内，取消检查清单")
                    self.parent().toggle_checklist()
                    event.accept()
                    return True

        return False

    def _reset_char_format_after_bullet_prefix(self):
        """删除键处理后，检查光标是否紧跟在 BULLET_PREFIX 之后。
        若是，则重置字符格式为正常前景色，避免后续输入的文字继承透明色而不可见。
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        block = cursor.block()
        BULLET_PREFIX = "\u2022 "  # • 
        block_text = block.text()
        if not block_text.startswith(BULLET_PREFIX):
            return
        block_start = block.position()
        pos_in_block = cursor.position() - block_start
        prefix_len = len(BULLET_PREFIX)
        if pos_in_block == prefix_len:
            # 光标紧跟在 • 前缀之后，重置字符格式为正常前景色
            fmt = QTextCharFormat(cursor.charFormat())
            fmt.setForeground(self.palette().color(self.foregroundRole()))
            self.setCurrentCharFormat(fmt)
            logger.debug("[_reset_char_format_after_bullet_prefix] 重置光标字符格式前景色")

    def _renumber_numbered_list_at(self, block):
        """对包含给定 block 的连续编号列表段重新从1开始顺序编号。

        从 block 向上找到编号列表的起始行，再向下遍历整个连续编号列表段，
        依次将前缀替换为 1. 2. 3. ...
        非编号列表行（包括空行）会中断连续段。
        """
        if not block.isValid():
            return

        # 向上找到编号列表段的起始块
        start_block = block
        prev = block.previous()
        while prev.isValid() and re.match(r'^\d+\.\s', prev.text()):
            start_block = prev
            prev = prev.previous()

        # 从起始块向下重新编号
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        number = 1
        cur = start_block
        while cur.isValid() and re.match(r'^\d+\.\s', cur.text()):
            text = cur.text()
            m = re.match(r'^(\d+\.\s)', text)
            if m:
                old_prefix = m.group(1)
                new_prefix = f"{number}. "
                if old_prefix != new_prefix:
                    blk_cursor = QTextCursor(cur)
                    blk_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    blk_cursor.movePosition(
                        QTextCursor.MoveOperation.NextCharacter,
                        QTextCursor.MoveMode.KeepAnchor,
                        len(old_prefix)
                    )
                    blk_cursor.insertText(new_prefix)
            number += 1
            cur = cur.next()
        cursor.endEditBlock()

    def _handle_return_key_press(self, event) -> bool:
        """处理回车键：在列表行尾按回车时，新行自动延续相同的列表格式。
        若当前行只有列表前缀而无正文内容，则退出列表格式（清除前缀）。

        Returns:
            bool: 已处理返回 True，否则返回 False
        """
        import re
        cursor = self.textCursor()
        # 有选区时不干预，交给默认处理
        if cursor.hasSelection():
            return False

        block = cursor.block()
        block_text = block.text()

        BULLET_PREFIX = "\u2022 "   # • （符号列表）
        DASH_PREFIX = "- "           # 短划线列表
        UNCHECKED = "○ "             # 检查清单（未选中）

        # 判断当前行的列表类型
        if block_text.startswith(BULLET_PREFIX):
            prefix_len = len(BULLET_PREFIX)
            list_type = "bullet"
        elif block_text.startswith(DASH_PREFIX):
            prefix_len = len(DASH_PREFIX)
            list_type = "dash"
        elif block_text.startswith("○ ") or block_text.startswith("● "):
            prefix_len = 2  # "○ " 和 "● " 均为 2 个字符
            list_type = "checklist"
        else:
            m = re.match(r'^(\d+)\.\s', block_text)
            if m:
                prefix_len = len(m.group(0))
                list_type = "numbered"
                current_number = int(m.group(1))
            else:
                # 检查当前行是否有标题格式（apply_heading 设置的格式）
                # 如果有，换行后将新行重置为正文格式
                heading_sizes = {FONT_SIZE_NOTE_TITLE, FONT_SIZE_HEADING1, FONT_SIZE_HEADING2, FONT_SIZE_HEADING3}  # 笔记标题、标题、小标题、副标题
                cur_fmt = cursor.charFormat()
                cur_size = cur_fmt.fontPointSize()
                cur_bold = cur_fmt.fontWeight() == QFont.Weight.Bold
                is_heading_line = cur_size in heading_sizes and cur_bold
                if not is_heading_line:
                    # 也检查整行是否有标题格式（光标可能在行首，charFormat 可能是正文格式）
                    doc = self.document()
                    block_start = block.position()
                    block_end = block_start + block.length() - 1
                    tmp_cursor = QTextCursor(doc)
                    for pos in range(block_start, block_end):
                        tmp_cursor.setPosition(pos)
                        fmt = tmp_cursor.charFormat()
                        size = fmt.fontPointSize()
                        bold = fmt.fontWeight() == QFont.Weight.Bold
                        if size in heading_sizes and bold:
                            is_heading_line = True
                            break
                if is_heading_line:
                    logger.debug(f"[_handle_return_key_press] 标题格式行换行，换行后重置为正文格式: "
                                 f"block_number={block.blockNumber()}, block_text={repr(block_text[:50])}")
                    super().keyPressEvent(event)
                    new_cursor = self.textCursor()
                    body_fmt = QTextCharFormat()
                    body_fmt.setFontPointSize(FONT_SIZE_BODY)
                    body_fmt.setFontWeight(QFont.Weight.Normal)
                    new_cursor.setBlockCharFormat(body_fmt)
                    self.setCurrentCharFormat(body_fmt)
                    self.setTextCursor(new_cursor)
                    return True
                logger.debug(f"[_handle_return_key_press] 非列表行，返回False交给默认处理: "
                             f"block_number={block.blockNumber()}, block_text={repr(block_text[:50])}, "
                             f"文档总行数={self.document().blockCount()}")
                return False  # 不是列表行，不处理

        content_after_prefix = block_text[prefix_len:]

        if not content_after_prefix.strip():
            # 当前行只有前缀，无正文内容 → 退出列表格式（删除前缀，不插入新行）
            block_cursor = QTextCursor(block)
            block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            block_cursor.movePosition(
                QTextCursor.MoveOperation.NextCharacter,
                QTextCursor.MoveMode.KeepAnchor,
                prefix_len
            )
            block_cursor.removeSelectedText()
            self.setTextCursor(block_cursor)
            return True

        # 当前行有正文内容 → 先执行默认换行，再在新行插入对应前缀
        super().keyPressEvent(event)

        new_cursor = self.textCursor()
        new_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)

        if list_type == "bullet":
            # 先清除新行可能继承的块字符格式，避免继承上一行（如 checklist）的格式
            normal_fmt = QTextCharFormat()
            normal_fmt.setForeground(self.palette().color(self.foregroundRole()))
            new_cursor.setBlockCharFormat(normal_fmt)
            # 插入 • 前缀，颜色设为透明（由自定义绘制覆盖）
            transparent_fmt = QTextCharFormat()
            transparent_fmt.setForeground(QColor(0, 0, 0, 0))
            new_cursor.insertText(BULLET_PREFIX, transparent_fmt)
            # 重置光标字符格式为默认前景色，避免后续输入的文字继承透明色
            new_cursor.setCharFormat(normal_fmt)
            self.setTextCursor(new_cursor)

        elif list_type == "dash":
            new_cursor.insertText(DASH_PREFIX)

        elif list_type == "checklist":
            new_cursor.insertText(UNCHECKED)

        elif list_type == "numbered":
            new_cursor.insertText(f"{current_number + 1}. ")

        return True

    # 英文输入法或功能键（Ctrl、Alt、Shift等+具体键）会触发此事件。
    # 使用功能键+其他键时，此事件触发时只能获取到功能键，+上的那个键值获取不到。
    # 其他输入法触发inputMethodEvent事件
    def keyPressEvent(self, event):
        """键盘事件 - 使用默认行为，允许删除选区中的所有内容（包括图片）"""
        key = event.key()
        key_text = event.text()
        modifiers = event.modifiers()
        logger.debug(f"[keyPressEvent] 按键事件触发 - key: {key}, text: '{key_text}', modifiers: {modifiers}")

        # 处理删除键
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._handle_delete_key_press(event):
                return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # 处理列表行回车：自动延续列表格式
            _pre_block_count = self.document().blockCount()
            _pre_cursor = self.textCursor()
            logger.debug(f"[keyPressEvent] 回车键按下: 回车前文档总行数={_pre_block_count}, "
                         f"cursor_pos={_pre_cursor.position()}, block_number={_pre_cursor.block().blockNumber()}")
            if self._handle_return_key_press(event):
                self._start_cursor_blink()
                return
            # 非列表行回车，走默认处理
        else:
            # 恢复光标显示并清除表格选中状态
            logger.debug("[keyPressEvent] 恢复光标显示并清除表格选中状态")
            self._restore_cursor_and_clear_table_selection(event)

        # QTextEditor 默认处理，如果光标位置发生了变化，会触发cursorPositionChanged事件，
        # 从而调用update_title_and_input_format进行格式化处理
        logger.debug("[keyPressEvent] 调用父类方法处理按键事件")
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            _post_block_count = self.document().blockCount()
            _post_cursor = self.textCursor()
            logger.debug(f"[keyPressEvent] 回车键处理完毕: 回车后文档总行数={_post_block_count}, "
                         f"cursor_pos={_post_cursor.position()}, block_number={_post_cursor.block().blockNumber()}, "
                         f"行数变化={_post_block_count - _pre_block_count}")
            # 如果回车后行数没有增加，说明 Qt 只清除了段落格式而没有新增段落（通常发生在有自定义
            # line-height 的空行上按回车时）。此时手动插入换行，确保回车操作正常生效。
            if _post_block_count == _pre_block_count:
                logger.debug("[keyPressEvent] 行数未增加，手动插入换行")
                cursor = self.textCursor()
                cursor.insertBlock()
                self.setTextCursor(cursor)
        # 删除键处理后，检查光标是否紧跟在 BULLET_PREFIX 之后（即删除内容后光标回到 • 后面）
        # 若是，则重置字符格式为正常前景色，避免后续输入的文字继承透明色而不可见
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._reset_char_format_after_bullet_prefix()
            # 删除行后，对当前行所在的编号列表段重新编号
            self._renumber_numbered_list_at(self.textCursor().block())
            # super().keyPressEvent 删除内容后，Qt 内部会重新设置 currentCharFormat，
            # 可能覆盖 cursorPositionChanged 里设置的标题格式。
            # 在此再次调用 update_title_and_input_format，确保标题行全选删除后光标格式正确。
            self.update_title_and_input_format()
        # 按键后重置光标闪烁定时器，确保光标从按键时刻重新开始完整的显示周期，
        # 避免因定时器相位不同步导致光标持续可见不闪烁的问题
        self._start_cursor_blink()
        logger.debug(f"[keyPressEvent] 按键事件处理完成，当前 _cursor_blink_visible={self._cursor_blink_visible}，定时器运行中={self._cursor_blink_timer.isActive()}")
    # 使用非英文输入法（中文等）时，会触发inputMethodEvent，每次输入一个字母都会触发此事件，
    # 通过event.preeditString()来获取所有输入的字母，最后确认后（空格或者手动选择）可以通过commitString来获取输入法输入的值
    # def inputMethodEvent(self, event):
    #     """处理输入法事件（如中文输入）
    #
    #     输入法输入完成后，会自动触发格式更新，确保标题格式正确。
    #     """
    #     commit_string = event.commitString()
    #     preedit_string = event.preeditString()
    #     logger.debug(f"[inputMethodEvent] 输入法事件触发 - commitString: '{commit_string}', preeditString: '{preedit_string}'")
    #
    #     # 在输入前预设置标题格式（如果需要）
    #     if commit_string and self._should_apply_title_format_before_input():
    #         logger.debug("[inputMethodEvent] 需要在输入前预设置标题格式")
    #         self._apply_title_format_to_cursor()
    #     elif commit_string:
    #         logger.debug("[inputMethodEvent] 有提交文本但不需要预设置格式")
    #
    #     # 调用父类方法处理输入法事件，会触发cursorPositionChanged事件
    #     super().inputMethodEvent(event)
    #
    #     # 输入完成后，触发格式检查和更新
    #     if commit_string:
    #         logger.debug("[inputMethodEvent] 输入完成，触发格式更新")
    #         self.update_title_and_input_format()
    #     else:
    #         logger.debug("[inputMethodEvent] 无提交文本（预编辑阶段），跳过格式更新")

    # def _should_apply_title_format_before_input(self) -> bool:
    #     """判断是否需要在输入前应用标题格式
    #
    #     Returns:
    #         bool: 如果光标在第一行且该行为空，返回 True
    #     """
    #     cursor = self.textCursor()
    #     block = cursor.block()
    #
    #     # 只在第一行且为空时才需要预设置格式
    #     if block.blockNumber() != 0:
    #         return False
    #
    #     block_text = block.text()
    #     return block_text == "" or block_text == "\u200B"
    #
    # def _apply_title_format_to_cursor(self):
    #     """为当前光标应用标题格式"""
    #     title_fmt = self.currentCharFormat()
    #     title_fmt.setFontPointSize(28)
    #     title_fmt.setFontWeight(QFont.Weight.Bold)
    #     self.setCurrentCharFormat(title_fmt)

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

        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()

        # 1. 查找真正的图片字符位置（U+FFFC）
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
            cursor.endEditBlock()
            return

        # 2. 只删除图片字符本身（1个字符），保持总行数不变
        _select_range(cursor, real_image_pos, real_image_pos + 1)
        cursor.removeSelectedText()

        # 3. 调整目标位置（删除操作在目标位置之前时，目标位置需要前移1）
        adjusted_target_pos = target_pos
        if real_image_pos < target_pos:
            adjusted_target_pos = target_pos - 1

        # 4. 在新位置插入图片字符
        cursor.setPosition(adjusted_target_pos)
        cursor.insertImage(image_format)

        cursor.endEditBlock()

        # 更新选中状态
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        self.selected_image = image_format
        self.selected_image_cursor = cursor
        self.selected_image_rect = self.get_image_rect_at_cursor(cursor)

        # 刷新显示
        self.viewport().update()

    def move_table_to_cursor(self, target_cursor):
        """移动表格到新的光标位置（目标光标所在行的前面）"""
        if not self.selected_table:
            return

        table = self.selected_table
        doc = self.document()

        table_start = table.firstPosition()
        table_end = table.lastPosition()

        # 目标位置（目标光标所在 block 的起始位置）
        target_block = target_cursor.block()
        target_block_start = target_block.position()

        # 如果目标位置在表格内部或紧邻表格，不移动
        if table_start - 1 <= target_block_start <= table_end + 1:
            return

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()

        # 1. 选中整个表格（包含 frame 边界字符），提取文档片段
        cursor.setPosition(table_start - 1)
        cursor.setPosition(table_end + 1, QTextCursor.MoveMode.KeepAnchor)
        fragment = cursor.selection()
        table_html = fragment.toHtml()

        # 2. 删除原表格（选中范围：frame前边界 到 frame后边界+1）
        cursor.setPosition(table_start - 1)
        cursor.setPosition(table_end + 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        # 3. 调整目标位置（如果表格在目标之前，目标位置需要前移）
        delete_count = (table_end + 1) - (table_start - 1)  # 删除的字符数
        adjusted_target_block_start = target_block_start
        if (table_start - 1) < target_block_start:
            adjusted_target_block_start = max(0, target_block_start - delete_count)

        # 4. 在目标位置插入表格
        cursor.setPosition(adjusted_target_block_start)
        cursor.insertHtml(table_html)

        cursor.endEditBlock()

        # 重新查找插入后的表格，保持选中状态
        cursor.setPosition(adjusted_target_block_start)
        new_table = cursor.currentTable()
        if not new_table:
            # insertHtml 后光标可能在表格之后，向前查找
            cursor.setPosition(adjusted_target_block_start + 1)
            new_table = cursor.currentTable()

        if new_table:
            self.selected_table = new_table
            self.selected_table_cursor = QTextCursor(doc)
            self.selected_table_cursor.setPosition(new_table.firstPosition())
        else:
            self.selected_table = None
            self.selected_table_cursor = None

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
        UNCHECKED = "○ "
        CHECKED = "● "
        BULLET_PREFIX = "\u2022 "  # • 项目符号

        def _is_list_line(line):
            """判断一行是否是列表行（核对清单/项目符号/短划线/编号）"""
            if (line.startswith(UNCHECKED) or line.startswith(CHECKED)
                    or line.startswith(BULLET_PREFIX) or line.startswith("- ")):
                return True
            if re.match(r'^\d+\.\s', line):
                return True
            return False

        # 检查粘贴内容是否包含列表行
        paste_has_list = False
        if source.hasText():
            for line in source.text().splitlines():
                if _is_list_line(line):
                    paste_has_list = True
                    break

        if paste_has_list:
            # 粘贴内容含列表时，先换行再粘贴，确保列表始终从新行开始
            cursor = self.textCursor()
            cursor_block_text = cursor.block().text()
            cursor_in_block_pos = cursor.position() - cursor.block().position()
            # 仅当当前行非空且光标不在行首时才换行（避免在空行或行首重复换行）
            if cursor_block_text.strip() != "" and cursor_in_block_pos > 0:
                cursor.insertBlock()
                self.setTextCursor(cursor)

        # 记录粘贴起始块位置
        paste_start_block_pos = self.textCursor().block().position()

        super().insertFromMimeData(source)

        # 粘贴后，检查粘贴位置附近是否有编号列表需要重新编号
        # （无论粘贴内容是否含列表，粘贴到编号列表中间都可能破坏编号顺序）
        doc = self.document()
        start_block_after = doc.findBlock(paste_start_block_pos)
        self._renumber_numbered_list_at(start_block_after)  # 粘贴起始位置所在段
        end_block_after = self.textCursor().block()
        if end_block_after != start_block_after:
            self._renumber_numbered_list_at(end_block_after)  # 粘贴结束位置所在段

        if not paste_has_list:
            return

        # 粘贴后将核对清单和项目符号前缀设为透明色，确保 paintEvent 绘制圆圈/圆点
        invis_fmt = QTextCharFormat()
        invis_fmt.setForeground(QColor(0, 0, 0, 0))
        invis_fmt.setBackground(Qt.GlobalColor.transparent)

        doc = self.document()
        paste_end_pos = self.textCursor().position()
        start_block = doc.findBlock(paste_start_block_pos)
        if not start_block.isValid():
            return

        block = start_block
        while block.isValid() and block.position() <= paste_end_pos:
            text = block.text()
            # 核对清单和项目符号前缀需设为透明色（由 paintEvent 绘制覆盖）
            for prefix in (UNCHECKED, CHECKED, BULLET_PREFIX):
                if text.startswith(prefix):
                    blk_cursor = QTextCursor(block)
                    blk_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    blk_cursor.movePosition(
                        QTextCursor.MoveOperation.NextCharacter,
                        QTextCursor.MoveMode.KeepAnchor, len(prefix))
                    blk_cursor.mergeCharFormat(invis_fmt)
                    break
            if block.position() + block.length() > paste_end_pos:
                break
            block = block.next()

    def is_image_file(self, file_path):
        """检查是否是图片文件"""
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']
        ext = os.path.splitext(file_path)[1].lower()
        return ext in image_extensions


class NoteEditor(QWidget):
    """笔记编辑器类 - 包含工具栏和编辑区"""
    def __init__(self, note_manager=None, main_window=None):
        super().__init__()
        self.bullet_action = None
        self.checklist_action = None
        self.math_renderer = MathRenderer()
        self.note_manager = note_manager
        self.main_window = main_window  # 保存 MainWindow 引用
        self.attachments = {}  # 存储附件 {filename: filepath}
        self.init_ui()

    def _get_current_note_id(self):
        """从main window获取当前笔记ID

        Returns:
            int or None: 当前笔记ID
        """
        if self.main_window and hasattr(self.main_window, '_get_current_note_id'):
            return self.main_window._get_current_note_id()
        return None

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

        # 创建空占位图标（16x16透明），确保所有菜单项图标列宽度一致
        _empty_pixmap = QPixmap(16, 16)
        _empty_pixmap.fill(Qt.GlobalColor.transparent)
        _empty_icon = QIcon(_empty_pixmap)

        # 标题样式：用普通 QAction + QProxyStyle 自定义字体绘制，文字位置完全由Qt菜单系统控制
        _heading_font_map = {}  # action -> (font_size, bold)

        class HeadingMenuStyle(QProxyStyle):
            def drawControl(self, element, option, painter, widget=None):
                if element == QStyle.ControlElement.CE_MenuItem and isinstance(option, QStyleOptionMenuItem):
                    action_font = _heading_font_map.get(option.text)
                    if action_font:
                        font_size, bold = action_font
                        new_option = QStyleOptionMenuItem(option)
                        f = QFont(option.font)
                        f.setPointSize(font_size)
                        f.setBold(bold)
                        new_option.font = f
                        super().drawControl(element, new_option, painter, widget)
                        return
                super().drawControl(element, option, painter, widget)

        _heading_style = HeadingMenuStyle(format_menu.style())
        format_menu.setStyle(_heading_style)

        def _make_heading_action(text, font_size, bold, callback):
            """创建以对应格式展示文字的菜单项（普通QAction，字体由HeadingMenuStyle控制）"""
            action = QAction(_empty_icon, text, self)
            _heading_font_map[text] = (font_size, bold)
            action.triggered.connect(callback)
            action._heading_text = text
            return action

        self.title_action = _make_heading_action("标题", FONT_SIZE_HEADING1, True, lambda: self.apply_heading(1))
        format_menu.addAction(self.title_action)

        self.heading_action = _make_heading_action("小标题", FONT_SIZE_HEADING2, True, lambda: self.apply_heading(2))
        format_menu.addAction(self.heading_action)

        self.subheading_action = _make_heading_action("副标题", FONT_SIZE_HEADING3, True, lambda: self.apply_heading(3))
        format_menu.addAction(self.subheading_action)

        # 正文
        body_action = _make_heading_action("正文", FONT_SIZE_BODY, False, self.apply_body_text)
        format_menu.addAction(body_action)

        format_menu.addSeparator()

        # 文本样式
        self.bold_action = QAction(_empty_icon, "粗体", self)
        self.bold_action.setShortcut("Ctrl+B")
        self.bold_action.triggered.connect(self.toggle_bold)
        format_menu.addAction(self.bold_action)

        self.italic_action = QAction(_empty_icon, "斜体", self)
        self.italic_action.setShortcut("Ctrl+I")
        self.italic_action.triggered.connect(self.toggle_italic)
        format_menu.addAction(self.italic_action)

        self.underline_action = QAction(_empty_icon, "下划线", self)
        self.underline_action.setShortcut("Ctrl+U")
        self.underline_action.triggered.connect(self.toggle_underline)
        format_menu.addAction(self.underline_action)

        self.strikethrough_action = QAction(_empty_icon, "删除线", self)
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

        self.bullet_action = QAction(_empty_icon, "• 项目符号列表", self)
        self.bullet_action.triggered.connect(self.toggle_bullet_list)
        format_menu.addAction(self.bullet_action)

        self.dash_action = QAction(_empty_icon, "- 短划线列表", self)
        self.dash_action.triggered.connect(self.toggle_dash_list)
        format_menu.addAction(self.dash_action)

        self.number_action = QAction(_empty_icon, "1. 编号列表", self)
        self.number_action.triggered.connect(self.toggle_numbered_list)
        format_menu.addAction(self.number_action)

        # 连接格式菜单的aboutToShow信号，在显示前更新状态
        format_menu.aboutToShow.connect(self.update_format_menu_state)

        # 格式按钮（使用 QToolButton，通过样式表去掉下拉箭头）
        format_button = QToolButton()
        format_button.setText("格式")
        format_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        format_button.setMenu(format_menu)
        # 去掉下拉箭头，保持与工具栏其他按钮一致的字体大小
        format_button.setStyleSheet("""
            QToolButton {
                font-size: 13px;
                padding: 2px 6px;
            }
            QToolButton::menu-indicator {
                image: none;
                width: 0;
            }
        """)
        # 格式按钮
        # format_button = QPushButton("格式")
        # format_button.setMenu(format_menu)
        toolbar.addWidget(format_button)

        # 核对清单按钮
        checklist_button = QPushButton()
        checklist_button.setToolTip("核对清单")
        checklist_button.clicked.connect(self.toggle_checklist)
        # 绘制核对清单图标
        from PyQt6.QtGui import QPainter
        _cl_pixmap = QPixmap(22, 22)
        _cl_pixmap.fill(Qt.GlobalColor.transparent)
        _cl_painter = QPainter(_cl_pixmap)
        _cl_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _cl_pen = _cl_painter.pen()
        _cl_pen.setColor(QColor("#555555"))
        _cl_pen.setWidth(1)
        _cl_painter.setPen(_cl_pen)
        # 第一行：实心圆（已选中）+ 横线
        _cl_painter.setBrush(QColor("#555555"))
        _cl_painter.drawEllipse(1, 2, 7, 7)
        _cl_painter.drawLine(11, 6, 21, 6)
        # 第二行：空心圆（未选中）+ 横线
        _cl_painter.setBrush(Qt.GlobalColor.transparent)
        _cl_painter.drawEllipse(1, 13, 7, 7)
        _cl_painter.drawLine(11, 17, 21, 17)
        _cl_painter.end()
        checklist_button.setIcon(QIcon(_cl_pixmap))
        checklist_button.setIconSize(QSize(22, 22))
        toolbar.addWidget(checklist_button)

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
                self._get_current_note_id() if hasattr(self, '_get_current_note_id') else None,
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

        # 修复旧数据中列表前缀颜色（确保前缀为透明色，避免在 paintEvent 中修改文档触发重绘循环）
        try:
            self.text_edit._fix_all_list_prefix_colors()
        except Exception as e:
            logger.exception("[fix-prefix-colors] failed: %s", e)

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
        # 清空编辑器会触发cursorPositionChanged事件，从而调用update_title_and_input_format方法，没有必要，所以屏蔽信息
        self.blockSignals(True)
        self.text_edit.clear()
        self.blockSignals(True)
        self.attachments.clear()

        # 获取光标
        cursor = self.text_edit.textCursor()

        # 创建标题字符格式
        title_char_fmt = QTextCharFormat()
        title_char_fmt.setFontPointSize(FONT_SIZE_NOTE_TITLE)
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

    # 格式化方法
    def apply_heading(self, level):
        """应用标题格式，如果已经是该格式则取消"""
        cursor = self.text_edit.textCursor()

        # 确定目标字号
        size_map = {1: FONT_SIZE_HEADING1, 2: FONT_SIZE_HEADING2, 3: FONT_SIZE_HEADING3}
        target_size = size_map.get(level, FONT_SIZE_BODY)

        # 判断当前是否已经是该标题格式（检查选区内所有字符）
        is_current_format = self._is_format_all_applied(
            cursor,
            lambda f: f.fontPointSize() == target_size and f.fontWeight() == QFont.Weight.Bold
        )

        cursor.beginEditBlock()

        if is_current_format:
            # 如果已经是该格式，则恢复为正文格式
            char_fmt = QTextCharFormat()
            char_fmt.setFontPointSize(FONT_SIZE_BODY)
            char_fmt.setFontWeight(QFont.Weight.Normal)
            if cursor.hasSelection():
                cursor.mergeCharFormat(char_fmt)
                # 重置 blockCharFormat，防止段落级别格式被污染
                body_block_fmt = QTextCharFormat()
                body_block_fmt.setFontPointSize(FONT_SIZE_BODY)
                body_block_fmt.setFontWeight(QFont.Weight.Normal)
                cursor.setBlockCharFormat(body_block_fmt)
                cursor.clearSelection()
                self.text_edit.setTextCursor(cursor)
            else:
                cursor.setBlockCharFormat(char_fmt)
                self.text_edit.setCurrentCharFormat(char_fmt)
                self.text_edit._manual_format_pt = int(char_fmt.fontPointSize())
        else:
            # 设置字符格式（仅作用于选中文字，不影响整行）
            char_fmt = QTextCharFormat()
            char_fmt.setFontWeight(QFont.Weight.Bold)
            char_fmt.setFontPointSize(target_size)

            if cursor.hasSelection():
                sel_start = cursor.selectionStart()
                sel_end = cursor.selectionEnd()

                # 第一步：固化整行所有字符的当前格式，防止 blockCharFormat 被污染后影响未选中字符
                doc = self.text_edit.document()
                block = cursor.block()
                block_start = block.position()
                block_end = block_start + block.length() - 1  # 不含换行符

                tmp_cursor = QTextCursor(doc)
                pos = block_start
                while pos < block_end:
                    tmp_cursor.setPosition(pos)
                    tmp_cursor.movePosition(QTextCursor.MoveOperation.Right,
                                            QTextCursor.MoveMode.KeepAnchor, 1)
                    existing_fmt = tmp_cursor.charFormat()
                    # 确保字体大小被显式设置（固化格式）
                    if existing_fmt.fontPointSize() <= 0:
                        existing_fmt.setFontPointSize(FONT_SIZE_BODY)
                    if existing_fmt.fontWeight() == QFont.Weight.Normal or existing_fmt.fontWeight() == 0:
                        existing_fmt.setFontWeight(QFont.Weight.Normal)
                    tmp_cursor.setCharFormat(existing_fmt)
                    pos += 1

                # 第二步：对选中部分应用标题格式
                cursor.setPosition(sel_start)
                cursor.setPosition(sel_end, QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(char_fmt)

                # 第三步：重置 blockCharFormat 为正文格式，防止段落级别格式被标题格式污染
                body_block_fmt = QTextCharFormat()
                body_block_fmt.setFontPointSize(FONT_SIZE_BODY)
                body_block_fmt.setFontWeight(QFont.Weight.Normal)
                cursor.setBlockCharFormat(body_block_fmt)

                cursor.clearSelection()
                self.text_edit.setTextCursor(cursor)
            else:
                cursor.setBlockCharFormat(char_fmt)
                self.text_edit.setCurrentCharFormat(char_fmt)
                self.text_edit._manual_format_pt = int(char_fmt.fontPointSize())

        cursor.endEditBlock()

    def apply_body_text(self):
        """应用正文格式"""
        cursor = self.text_edit.textCursor()

        char_fmt = QTextCharFormat()
        char_fmt.setFontPointSize(FONT_SIZE_BODY)
        char_fmt.setFontWeight(QFont.Weight.Normal)

        if cursor.hasSelection():
            cursor.mergeCharFormat(char_fmt)
        else:
            cursor.setBlockCharFormat(char_fmt)
            self.text_edit.setCurrentCharFormat(char_fmt)
            self.text_edit._manual_format_pt = int(char_fmt.fontPointSize())

    def _is_format_all_applied(self, cursor: QTextCursor, check_fn) -> bool:
        """检查选区内所有字符是否都已应用某种格式。
        如果没有选区，则检查当前光标位置的格式。
        
        Args:
            cursor: 文本光标
            check_fn: 接受 QTextCharFormat 返回 bool 的函数
        Returns:
            选区内所有字符都满足条件时返回 True
        """
        if not cursor.hasSelection():
            return check_fn(cursor.charFormat())
        
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        doc = self.text_edit.document()
        
        # 逐字符检查选区内的格式
        tmp = QTextCursor(doc)
        for pos in range(start, end):
            fmt = _selected_char_format(doc, pos)
            if fmt is None:
                continue
            # 跳过换行符等特殊字符
            tmp.setPosition(pos)
            tmp.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
            ch = tmp.selectedText()
            if ch in ('\n', '\r', '\u2029', '\u2028'):
                continue
            if not check_fn(fmt):
                return False
        return True

    def toggle_bold(self):
        """切换粗体"""
        cursor = self.text_edit.textCursor()
        all_bold = self._is_format_all_applied(
            cursor, lambda f: f.fontWeight() == QFont.Weight.Bold
        )
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if all_bold else QFont.Weight.Bold)
        cursor.mergeCharFormat(fmt)

    def toggle_italic(self):
        """切换斜体"""
        cursor = self.text_edit.textCursor()
        all_italic = self._is_format_all_applied(cursor, lambda f: f.fontItalic())
        fmt = QTextCharFormat()
        fmt.setFontItalic(not all_italic)
        cursor.mergeCharFormat(fmt)

    def toggle_underline(self):
        """切换下划线"""
        cursor = self.text_edit.textCursor()
        all_underline = self._is_format_all_applied(cursor, lambda f: f.fontUnderline())
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not all_underline)
        cursor.mergeCharFormat(fmt)

    def toggle_strikethrough(self):
        """切换删除线"""
        cursor = self.text_edit.textCursor()
        all_strike = self._is_format_all_applied(cursor, lambda f: f.fontStrikeOut())
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not all_strike)
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
                # Qt 选中高亮会遮盖字体颜色，取消选中让颜色立即显示
                cursor.clearSelection()
                self.text_edit.setTextCursor(cursor)
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
                # Qt 选中高亮会遮盖背景色，取消选中让背景色立即显示
                cursor.clearSelection()
                self.text_edit.setTextCursor(cursor)
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

    # ------------------------------------------------------------------ #
    #  列表格式公共辅助方法
    # ------------------------------------------------------------------ #

    def _get_list_selection_range(self):
        """返回 (cursor, start_block, end_block)，光标无选区时两块相同"""
        cursor = self.text_edit.textCursor()
        doc = self.text_edit.document()
        if cursor.hasSelection():
            start_pos = min(cursor.position(), cursor.anchor())
            end_pos = max(cursor.position(), cursor.anchor())
        else:
            start_pos = end_pos = cursor.position()
        return cursor, doc.findBlock(start_pos), doc.findBlock(end_pos)

    def _clear_block_qt_list_format(self, block, block_cursor):
        """取消块的 Qt 列表归属，并清除缩进/左边距"""
        existing_list = block.textList()
        if existing_list:
            existing_list.remove(block)
        blk_fmt = block.blockFormat()
        blk_fmt.setIndent(0)
        blk_fmt.setLeftMargin(0)
        block_cursor.setBlockFormat(blk_fmt)

    def _remove_block_list_prefix(self, block, block_cursor):
        """
        删除行首已有的任意列表前缀（• / - / N. / ○ / ●）。
        若删除了 checklist 前缀，同时清除整行背景色。
        返回被删除的前缀字符串，若无前缀则返回空字符串。
        """
        import re
        text = block.text()
        prefix = ""
        if text.startswith("\u2022 "):          # • 
            prefix = "\u2022 "
        elif text.startswith("- "):
            prefix = "- "
        elif text.startswith("○ "):
            prefix = "○ "
        elif text.startswith("● "):
            prefix = "● "
        else:
            m = re.match(r'^(\d+\.\s)', text)
            if m:
                prefix = m.group(1)

        if prefix:
            block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            block_cursor.movePosition(
                QTextCursor.MoveOperation.NextCharacter,
                QTextCursor.MoveMode.KeepAnchor,
                len(prefix)
            )
            block_cursor.removeSelectedText()
        return prefix

    def _reset_cursor_char_format(self, cursor):
        """将光标字符格式重置为编辑器默认前景色，防止后续输入继承透明色"""
        fmt = QTextCharFormat()
        fmt.setForeground(self.text_edit.palette().color(self.text_edit.foregroundRole()))
        cursor.setCharFormat(fmt)

    # ------------------------------------------------------------------ #

    def toggle_bullet_list(self):
        """切换项目符号列表，支持多行选择，行首显示 '• ' 前缀"""
        BULLET_PREFIX = "\u2022 "  # • 

        def _is_bullet_block(blk):
            return blk.text().startswith(BULLET_PREFIX)

        cursor, start_block, end_block = self._get_list_selection_range()

        # 判断选区内所有块是否都已经是项目符号列表
        all_bullet = True
        block = start_block
        while block.isValid():
            if not _is_bullet_block(block):
                all_bullet = False
                break
            if block == end_block:
                break
            block = block.next()

        cursor.beginEditBlock()
        block = start_block
        while block.isValid():
            block_cursor = QTextCursor(block)
            if all_bullet:
                # 取消：删除行首 '• ' 前缀，清除 Qt 列表格式
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                block_cursor.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                    len(BULLET_PREFIX)
                )
                block_cursor.removeSelectedText()
                self._clear_block_qt_list_format(block, block_cursor)
            else:
                # 清除 Qt 列表格式，删除其他列表前缀，再插入 • 前缀
                self._clear_block_qt_list_format(block, block_cursor)
                self._remove_block_list_prefix(block, block_cursor)
                # 插入透明色前缀，由 paintEvent 绘制可见圆点
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                transparent_fmt = QTextCharFormat()
                transparent_fmt.setForeground(QColor(0, 0, 0, 0))
                block_cursor.setCharFormat(transparent_fmt)
                block_cursor.insertText(BULLET_PREFIX)
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def toggle_dash_list(self):
        """切换短划线列表，支持多行选择，行首显示 '- ' 前缀"""
        DASH_PREFIX = "- "

        def _is_dash_block(blk):
            return blk.text().startswith(DASH_PREFIX)

        cursor, start_block, end_block = self._get_list_selection_range()

        # 判断选区内所有块是否都已经是短划线列表
        all_dash = True
        block = start_block
        while block.isValid():
            if not _is_dash_block(block):
                all_dash = False
                break
            if block == end_block:
                break
            block = block.next()

        cursor.beginEditBlock()
        block = start_block
        while block.isValid():
            block_cursor = QTextCursor(block)
            if all_dash:
                # 取消：删除行首 "- " 前缀，清除 Qt 列表格式
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                block_cursor.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                    len(DASH_PREFIX)
                )
                block_cursor.removeSelectedText()
                self._clear_block_qt_list_format(block, block_cursor)
            else:
                # 清除 Qt 列表格式，删除其他列表前缀，再插入 - 前缀
                self._clear_block_qt_list_format(block, block_cursor)
                self._remove_block_list_prefix(block, block_cursor)
                if not _is_dash_block(block):
                    block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    block_cursor.insertText(DASH_PREFIX)
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def toggle_numbered_list(self):
        """切换编号列表，支持多行选择，行首显示 '1. ' '2. ' 等自动编号前缀"""
        import re

        def _is_numbered_block(blk):
            return bool(re.match(r'^\d+\.\s', blk.text()))

        cursor, start_block, end_block = self._get_list_selection_range()

        # 判断选区内所有块是否都已经是编号列表
        all_numbered = True
        block = start_block
        while block.isValid():
            if not _is_numbered_block(block):
                all_numbered = False
                break
            if block == end_block:
                break
            block = block.next()

        cursor.beginEditBlock()
        block = start_block
        number = 1  # 编号从1开始
        while block.isValid():
            block_cursor = QTextCursor(block)
            if all_numbered:
                # 取消编号列表：删除行首的 'N. ' 前缀
                m = re.match(r'^(\d+\.\s)', block.text())
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                block_cursor.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                    len(m.group(1))
                )
                block_cursor.removeSelectedText()
                # 取消已有的 Qt 列表格式，并清除缩进
                existing_list = block.textList()
                if existing_list:
                    existing_list.remove(block)
                blk_fmt = block.blockFormat()
                blk_fmt.setIndent(0)
                blk_fmt.setLeftMargin(0)
                block_cursor.setBlockFormat(blk_fmt)
            else:
                # 清除 Qt 列表格式，删除其他列表前缀，再插入编号前缀
                self._clear_block_qt_list_format(block, block_cursor)
                self._remove_block_list_prefix(block, block_cursor)
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                block_cursor.insertText(f"{number}. ")
                number += 1
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def toggle_checklist(self):
        """切换核对清单，支持多行选择，行首显示 '○ '（未选中）或 '● '（已选中，黄色背景）"""
        UNCHECKED = "○ "   # U+25CB 空心圆（未选中）
        CHECKED_CHAR = "● "  # U+25CF 实心圆（已选中，黄色背景）

        def _is_checklist_block(blk):
            t = blk.text()
            return t.startswith(UNCHECKED) or t.startswith(CHECKED_CHAR)

        cursor, start_block, end_block = self._get_list_selection_range()

        # 判断选区内所有块是否都已经是核对清单
        all_checklist = True
        block = start_block
        while block.isValid():
            if not _is_checklist_block(block):
                all_checklist = False
                break
            if block == end_block:
                break
            block = block.next()

        cursor.beginEditBlock()
        block = start_block
        while block.isValid():
            block_cursor = QTextCursor(block)
            if all_checklist:
                # 取消：删除行首圆圈前缀
                prefix = UNCHECKED if block.text().startswith(UNCHECKED) else CHECKED_CHAR
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                block_cursor.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                    len(prefix)
                )
                block_cursor.removeSelectedText()
            else:
                self._clear_block_qt_list_format(block, block_cursor)
                self._remove_block_list_prefix(block, block_cursor)
                # 在行首插入未选中圆圈前缀（前景色透明，由 paintEvent 绘制圆圈图标）
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                _invis_fmt = QTextCharFormat()
                _invis_fmt.setForeground(QColor(0, 0, 0, 0))
                _invis_fmt.setBackground(Qt.GlobalColor.transparent)
                block_cursor.setCharFormat(_invis_fmt)
                block_cursor.insertText(UNCHECKED)
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def update_format_menu_state(self):
        """更新格式菜单的状态（显示当前格式）"""
        from PyQt6.QtGui import QIcon, QPainter
        cursor = self.text_edit.textCursor()
        # 从右向左选择时，cursor.position() 在选区左端（边界外），
        # 需要取选区内部位置的格式，否则会读到选区外的字符格式
        if cursor.hasSelection():
            # 取选区内靠近起始处的位置（min+1 确保在选区内部）
            inner_pos = min(cursor.position(), cursor.anchor()) + 1
            inner_cursor = self.text_edit.textCursor()
            inner_cursor.setPosition(inner_pos)
            fmt = inner_cursor.charFormat()
        else:
            fmt = cursor.charFormat()

        # 获取当前字体大小和粗细
        font_size = fmt.fontPointSize()
        font_weight = fmt.fontWeight()

        # 构建对号图标和空图标（大小固定，文字位置不变）
        icon_size = 16

        def _make_check_icon():
            """绘制一个对号图标"""
            pixmap = QPixmap(icon_size, icon_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = painter.pen()
            pen.setColor(QColor("#333333"))
            pen.setWidth(2)
            painter.setPen(pen)
            # 绘制对号：从左下到中间，再从中间到右上
            painter.drawLine(2, 9, 6, 13)
            painter.drawLine(6, 13, 14, 3)
            painter.end()
            return QIcon(pixmap)

        def _make_empty_icon():
            """绘制一个透明空图标，占位用"""
            pixmap = QPixmap(icon_size, icon_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            return QIcon(pixmap)

        check_icon = _make_check_icon()
        empty_icon = _make_empty_icon()

        def _set_check_icon(action, checked):
            """根据checked状态设置action图标"""
            action.setIcon(check_icon if checked else empty_icon)

        # 更新标题状态
        _set_check_icon(self.title_action, font_size == FONT_SIZE_HEADING1 and font_weight == QFont.Weight.Bold)
        _set_check_icon(self.heading_action, font_size == FONT_SIZE_HEADING2 and font_weight == QFont.Weight.Bold)
        _set_check_icon(self.subheading_action, font_size == FONT_SIZE_HEADING3 and font_weight == QFont.Weight.Bold)

        # 更新文本样式状态
        _set_check_icon(self.bold_action, font_weight == QFont.Weight.Bold)
        _set_check_icon(self.italic_action, fmt.fontItalic())
        _set_check_icon(self.underline_action, fmt.fontUnderline())
        _set_check_icon(self.strikethrough_action, fmt.fontStrikeOut())

        # 更新列表状态（同样需要用选区内部的光标检测）
        check_cursor = inner_cursor if cursor.hasSelection() else cursor
        import re
        current_block = check_cursor.block()
        block_text = current_block.text()
        is_bullet = block_text.startswith("\u2022 ")
        is_numbered = bool(re.match(r'^\d+\.\s', block_text))
        is_dash = block_text.startswith("- ")
        _set_check_icon(self.bullet_action, is_bullet)
        _set_check_icon(self.number_action, is_numbered)
        _set_check_icon(self.dash_action, is_dash)

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

        # 插入表格，insertTable 后光标已自动定位在第一个单元格
        cursor.insertTable(rows, cols, table_format)
        self.text_edit.setTextCursor(cursor)
        # 恢复焦点，触发 focusInEvent → _start_cursor_blink
        self.text_edit.setFocus(Qt.FocusReason.OtherFocusReason)

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
            file_path, self._get_current_note_id()
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
            if not self.note_manager or not self._get_current_note_id():
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

        # 恢复焦点到编辑器（对话框关闭后焦点会丢失，因为焦点原来在对话框上）
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

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