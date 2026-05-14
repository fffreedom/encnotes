# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QListWidget, QMenu
from PyQt6.QtGui import QAction, QPainter, QPen, QColor
from PyQt6.QtCore import Qt
import logging

if TYPE_CHECKING:
    from main_window import MainWindow

logger = logging.getLogger(__name__)


class NoteListWidget(QListWidget):
    """支持笔记拖拽到文件夹的自定义列表控件

    额外：自绘“笔记项分隔线”，让分隔线与标题起点对齐，且在选中黄色高亮的底部之外。
    """

    # 用 item.data 存储分隔线参数（避免改动太多结构）
    _SEP_ENABLED_ROLE = Qt.ItemDataRole.UserRole + 1
    _SEP_LEFT_ROLE = Qt.ItemDataRole.UserRole + 2
    _SEP_RIGHT_ROLE = Qt.ItemDataRole.UserRole + 3

    CLICK_THRESHOLD = 5  # 点击与拖动的移动距离阈值（像素）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None  # 将在MainWindow中设置
        self.last_selected_row = None  # 记录上次选中的行，用于Shift多选
        self.press_pos = None  # 记录鼠标按下的位置
        self.press_row = None  # 记录鼠标按下时的行号
        self.selected_rows: set[int] = set()  # 当前选中的笔记行号集合

        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        pen = QPen(QColor(0xE0, 0xE0, 0xE0), 1)
        painter.setPen(pen)

        # 默认只给“可选中的笔记项”画分隔线；
        # 但如果某个不可选项（比如分组标题）显式设置了 _SEP_ENABLED_ROLE，也允许绘制。
        for i in range(self.count()):
            item = self.item(i)
            if not item:
                continue

            enabled = bool(item.data(self._SEP_ENABLED_ROLE))
            if not enabled:
                continue

            rect = self.visualItemRect(item)
            if rect.isNull() or rect.height() <= 0:
                continue

            left = item.data(self._SEP_LEFT_ROLE)
            right = item.data(self._SEP_RIGHT_ROLE)
            try:
                left = int(left) if left is not None else 0
            except Exception:
                left = 0
            try:
                right = int(right) if right is not None else 0
            except Exception:
                right = 0

            # 画在 item 的顶部边缘：
            # 这样上一条的分隔线会紧贴下一条（即选中黄色背景）的上边缘，避免出现“线与黄色之间有一点空白”。
            # 同时由于绘制顺序是从上到下，使用 top 能减少 1px 的几何/抗锯齿误差。
            y = rect.top()
            x1 = rect.left() + max(0, left)
            x2 = rect.right() - max(0, right)
            painter.drawLine(x1, y, x2, y)

        painter.end()

    def _is_valid_selectable_item(self, item):
        """验证item是否有效且可选中

        Args:
            item: QListWidgetItem 列表项

        Returns:
            bool: 是否有效且可选中
        """
        if not item:
            return False
        return bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)

    def _is_command_or_ctrl_pressed(self, modifiers):
        """判断是否按下了 Command 或 Ctrl 键

        Args:
            modifiers: Qt.KeyboardModifier 键盘修饰符

        Returns:
            bool: 是否按下了 Command 或 Ctrl 键
        """
        return bool(modifiers & Qt.KeyboardModifier.ControlModifier or
                   modifiers & Qt.KeyboardModifier.MetaModifier)

    def _handle_command_press(self, clicked_row):
        """处理 Command/Ctrl 键点击（跳选：添加/移除单个项）

        Args:
            clicked_row: int 点击的行号
        """
        if self.main_window:
            self.toggle_note_selection(clicked_row)
        self.last_selected_row = clicked_row

    def _handle_shift_press(self, clicked_row):
        """处理 Shift 键点击（范围选择）

        Args:
            clicked_row: int 点击的行号
        """
        if self.main_window and self.last_selected_row is not None:
            self.select_note_range(self.last_selected_row, clicked_row)

    def _is_item_in_multi_select(self, clicked_row):
        """判断点击的item是否在多选集合中

        Args:
            clicked_row: int 点击的行号

        Returns:
            bool: 是否在多选集合中
        """
        return clicked_row in self.selected_rows

    def _keep_multi_select_for_drag(self, clicked_row, event_pos):
        """保持多选状态用于拖动

        Args:
            clicked_row: int 点击的行号
            event_pos: QPoint 点击位置
        """
        # 记录点击信息，用于在mouseReleaseEvent中判断是否发生了拖动
        self.press_pos = event_pos
        self.press_row = clicked_row

        # 保持多选状态，但需要设置currentItem以支持拖动
        self.blockSignals(True)
        self.setCurrentRow(clicked_row)
        self.blockSignals(False)

        # 强制刷新视觉选中状态，确保所有选中项都正确显示
        self.update_visual_selection()

    # mousePressEvent，正常鼠标按下事件处理函数
    def _handle_normal_press(self, clicked_row, event_pos):
        """处理普通点击（单选或保持多选用于拖动）

        Args:
            clicked_row: int 点击的行号
            event_pos: QPoint 点击位置
        """
        logger.debug(f"🔵 [DEBUG] _handle_normal_press called - clicked_row: {clicked_row}, event_pos: ({event_pos.x()}, {event_pos.y()})")

        if not self.main_window:
            logger.debug(f"🔵 [DEBUG] _handle_normal_press - main_window is None, returning")
            return

        # 如果点击的笔记已经在多选集合中，保持多选状态（用于拖动）
        is_in_multi_select = self._is_item_in_multi_select(clicked_row)
        logger.debug(f"🔵 [DEBUG] _handle_normal_press - is_in_multi_select: {is_in_multi_select}")

        if is_in_multi_select:
            logger.debug(f"🔵 [DEBUG] _handle_normal_press - Item already in multi-select, keeping multi-select for drag")
            self._keep_multi_select_for_drag(clicked_row, event_pos)
        else:
            # 点击的是未选中的笔记，执行单选
            logger.debug(f"🔵 [DEBUG] _handle_normal_press - Item not in multi-select, selecting single note at row: {clicked_row}")
            self.select_single_note(clicked_row)

        self.last_selected_row = clicked_row
        logger.debug(f"🔵 [DEBUG] _handle_normal_press completed - last_selected_row set to: {clicked_row}")

    def mousePressEvent(self, event):
        """处理鼠标按下事件，支持多选

        Args:
            event: QMouseEvent 鼠标事件
        """
        logger.debug("🟡 [DEBUG] NoteListWidget mousePressEvent triggered")
        # 1. 获取并验证点击的item
        item = self.itemAt(event.pos())
        if not self._is_valid_selectable_item(item):
            super().mousePressEvent(event)
            return

        # 2. 只处理左键点击，右键用于显示菜单
        if event.button() != Qt.MouseButton.LeftButton:
            # 不调用super()，直接返回，让Qt的事件系统继续传递到contextMenuEvent
            return

        # 3. 获取点击信息
        clicked_row = self.row(item)
        modifiers = event.modifiers()

        # 4. 根据修饰键处理不同的点击逻辑
        if self._is_command_or_ctrl_pressed(modifiers):
            # Command/Ctrl键：跳选（添加/移除单个项）
            self._handle_command_press(clicked_row)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Shift键：范围选择
            self._handle_shift_press(clicked_row)
        else:
            # 普通点击：单选或保持多选（用于拖动）
            self._handle_normal_press(clicked_row, event.pos())

        # 5. 调用父类方法以支持拖动功能
        super().mousePressEvent(event)

    def _log_mouse_release(self, event):
        """记录鼠标释放事件的调试日志

        Args:
            event: QMouseEvent 鼠标事件
        """
        button_name = "Left" if event.button() == Qt.MouseButton.LeftButton else \
                     "Right" if event.button() == Qt.MouseButton.RightButton else "Other"
        logger.debug(f"[mouseReleaseEvent] Button: {button_name}, "
              f"press_pos: {self.press_pos}, "
              f"selected_rows count: {len(self.selected_rows)}")

    def _is_within_click_threshold(self, release_pos):
        """判断释放位置是否在按下位置的点击阈值内（即未发生拖动）

        Args:
            release_pos: QPoint 鼠标释放位置

        Returns:
            bool: True 表示未发生拖动，False 表示发生了拖动
        """
        move_distance = (release_pos - self.press_pos).manhattanLength()
        logger.debug(f"[mouseReleaseEvent] Move distance: {move_distance}")
        return move_distance < self.CLICK_THRESHOLD

    def _handle_click_in_multi_select(self):
        """处理多选状态下的点击事件（取消多选，只选中当前笔记）"""
        if self.main_window and self.press_row is not None:
            logger.debug(f"[mouseReleaseEvent] Canceling multi-select, "
                  f"selecting single note: {self.press_row}")
            self.select_single_note(self.press_row)

    def _clear_press_info(self):
        """清除记录的按下信息"""
        self.press_pos = None
        self.press_row = None

    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件，如果是点击而非拖动，则取消多选状态

        Args:
            event: QMouseEvent 鼠标事件
        """
        logger.debug("🟢 [DEBUG] mouseReleaseEvent triggered")
        # 1. 记录调试日志
        self._log_mouse_release(event)

        # 2. 只处理左键释放事件，右键用于显示菜单，不应该影响选中状态
        if event.button() == Qt.MouseButton.LeftButton:
            # 3. 检查是否在多选状态下点击
            if self.press_pos is not None and len(self.selected_rows) > 1:
                # 4. 判断是点击还是拖动
                if self._is_within_click_threshold(event.pos()):
                    # 5. 如果是点击，取消多选状态，只选中当前点击的笔记
                    self._handle_click_in_multi_select()

            # 6. 清除记录的点击信息
            self._clear_press_info()

        # 7. 调用父类方法
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """处理右键菜单事件（融合单选和多选功能）"""
        if not self.main_window:
            return

        item = self.itemAt(event.pos())

        # 点击空白区域：只显示"新建笔记"
        if not item:
            self._show_blank_area_menu(event.globalPos())
            return

        # 处理笔记选择
        selected_note_ids = self._handle_note_selection(item)
        if not selected_note_ids:
            return

        # 创建并显示完整菜单
        menu = self._create_note_context_menu(selected_note_ids)
        menu.exec(event.globalPos())

    def select_single_note(self, row):
        """单选笔记"""
        logger.debug(f"[select_single_note] ENTER: row={row}, current_note_id={self.main_window._get_current_note_id()}")
        # 清除之前的多选状态
        self.clear_selection()

        # 选中指定行
        self.selected_rows = {row}
        self.update_visual_selection()

        # 加载笔记到编辑器
        item = self.item(row)
        if item:
            # 保存之前的笔记（包括光标位置）
            if self.main_window._get_current_note_id():
                self.main_window.save_current_note()

            # 阻止信号，避免触发on_note_selected
            self.blockSignals(True)
            self.setCurrentItem(item)
            self.blockSignals(False)

            # 加载新笔记
            note_id = item.data(Qt.ItemDataRole.UserRole)
            logger.debug(f"[select_single_note] loading note_id={note_id}")
            self.main_window._set_current_note_id(note_id)
            self.main_window._load_and_display_note(note_id)
        logger.debug(f"[select_single_note] EXIT: row={row}, current_note_id={self.main_window._get_current_note_id()}")

    def toggle_note_selection(self, row):
        """切换笔记的选中状态（Command键跳选）"""
        if row in self.selected_rows:
            # 如果已选中，则取消选中
            self.selected_rows.discard(row)
            if not self.selected_rows:
                # 如果没有选中项了，保存当前笔记，然后清空编辑器
                if self.main_window._get_current_note_id():
                    self.main_window.save_current_note()
                self.main_window._set_current_note_id(None)
                self.main_window.editor.clear()
        else:
            # 如果未选中，则添加到选中集合
            # 先保存当前笔记
            if self.main_window._get_current_note_id():
                self.main_window.save_current_note()

            self.selected_rows.add(row)
            # 将最后选中的项设为当前项
            item = self.item(row)
            if item:
                self.blockSignals(True)
                self.setCurrentItem(item)
                self.blockSignals(False)
                # 加载这个笔记到编辑器
                note_id = item.data(Qt.ItemDataRole.UserRole)
                self.main_window._set_current_note_id(note_id)
                self.main_window._load_and_display_note(note_id)

        self.update_visual_selection()

    def select_note_range(self, start_row, end_row):
        """范围选择笔记（Shift键）"""
        # 清除之前的选择
        self.clear_selection()

        # 确定范围
        min_row = min(start_row, end_row)
        max_row = max(start_row, end_row)

        # 选中范围内所有可选中的笔记项
        for row in range(min_row, max_row + 1):
            item = self.item(row)
            if item and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                self.selected_rows.add(row)

        # 设置最后点击的项为当前项
        if self.selected_rows:
            item = self.item(end_row)
            if item:
                self.blockSignals(True)
                self.setCurrentItem(item)
                self.blockSignals(False)
                # 加载这个笔记到编辑器
                note_id = item.data(Qt.ItemDataRole.UserRole)
                self.main_window._set_current_note_id(note_id)
                note = self.main_window.note_manager.get_note(note_id)
                if note:
                    self.main_window.editor.blockSignals(True)
                    self.main_window.editor.setHtml(note['content'])
                    self.main_window.editor.blockSignals(False)

        self.update_visual_selection()

    def _show_blank_area_menu(self, global_pos):
        """显示空白区域的右键菜单（仅包含新建笔记）"""
        menu = QMenu(self)
        new_note_action = QAction("新建笔记", self)
        new_note_action.triggered.connect(lambda: self.main_window.create_note_in_current_folder())

        # 在"所有笔记"和"最近删除"视图中禁用
        if self.main_window.current_folder_id is None or self.main_window.current_system_key == "deleted":
            new_note_action.setEnabled(False)

        menu.addAction(new_note_action)
        menu.exec(global_pos)

    def _handle_note_selection(self, clicked_item):
        """处理笔记选择逻辑，返回选中的笔记ID列表"""
        clicked_row = self.row(clicked_item)

        # 如果点击的笔记不在选中集合中，则只选中当前笔记
        if clicked_row not in self.selected_rows:
            self.select_single_note(clicked_row)

        # 获取所有选中的笔记ID
        selected_note_ids = []
        for row in sorted(self.selected_rows):
            item = self.item(row)
            if item:
                selected_note_ids.append(item.data(Qt.ItemDataRole.UserRole))

        logger.debug(f"[contextMenuEvent] Final selected note IDs: {selected_note_ids}, count: {len(selected_note_ids)}")
        return selected_note_ids

    def _create_note_context_menu(self, selected_note_ids):
        """创建笔记的完整右键菜单"""
        menu = QMenu(self)

        # 1. 新建笔记
        self._add_new_note_action(menu)
        menu.addSeparator()

        # 2. 移到文件夹
        self._add_move_to_menu(menu, selected_note_ids)
        menu.addSeparator()

        # 3. 置顶/取消置顶
        self._add_pin_action(menu, selected_note_ids)
        menu.addSeparator()

        # 4. 标签
        self._add_tag_menu(menu, selected_note_ids)
        menu.addSeparator()

        # 5. 删除笔记
        self._add_delete_action(menu, selected_note_ids)

        return menu

    def _add_new_note_action(self, menu):
        """添加"新建笔记"菜单项"""
        new_note_action = QAction("新建笔记", self)
        new_note_action.triggered.connect(lambda: self.main_window.create_new_note())

        # 在"所有笔记"和"最近删除"视图中禁用
        if self.main_window.current_folder_id is None or self.main_window.current_system_key == "deleted":
            new_note_action.setEnabled(False)

        menu.addAction(new_note_action)

    def _add_move_to_menu(self, menu, selected_note_ids):
        """添加"移到"子菜单"""
        move_menu = menu.addMenu("移到")
        self._populate_move_to_menu(move_menu, selected_note_ids)

    def _add_pin_action(self, menu, selected_note_ids):
        """添加"置顶/取消置顶"菜单项"""
        all_pinned = all(self.main_window.note_manager.is_note_pinned(nid) for nid in selected_note_ids)
        pin_text = "取消置顶" if all_pinned else "置顶"

        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(lambda: self.main_window.batch_toggle_pin_notes(selected_note_ids))
        menu.addAction(pin_action)

    def _add_tag_menu(self, menu, selected_note_ids):
        """添加"标签"子菜单"""
        tag_menu = menu.addMenu("标签")
        all_tags = self.main_window.note_manager.get_all_tags()

        if all_tags:
            self._populate_tag_menu(tag_menu, all_tags, selected_note_ids)
        else:
            self._add_no_tags_placeholder(tag_menu)

    def _populate_tag_menu(self, tag_menu, all_tags, selected_note_ids):
        """填充标签子菜单的内容"""
        # 获取第一个笔记的标签（用于显示对勾）
        first_note_tags = self.main_window.note_manager.get_note_tags(selected_note_ids[0])
        first_note_tag_ids = {t['id'] for t in first_note_tags}

        for tag in all_tags:
            tag_id = tag['id']
            tag_name = tag['name']
            has_tag = tag_id in first_note_tag_ids

            # 显示对勾表示已添加
            display_name = f"✓ {tag_name}" if has_tag else tag_name

            action = QAction(display_name, self)
            action.triggered.connect(
                lambda checked, tid=tag_id, tname=tag_name, has=has_tag:
                    self.main_window.toggle_tag_for_notes(selected_note_ids, tid, tname, has)
            )
            tag_menu.addAction(action)

    def _add_no_tags_placeholder(self, tag_menu):
        """添加"无标签"占位符"""
        no_tags_action = QAction("(无标签)", self)
        no_tags_action.setEnabled(False)
        tag_menu.addAction(no_tags_action)

    def _add_delete_action(self, menu, selected_note_ids):
        """添加"删除笔记"菜单项"""
        count = len(selected_note_ids)
        delete_text = f"删除笔记 ({count}个)" if count > 1 else "删除笔记"

        delete_action = QAction(delete_text, self)
        delete_action.triggered.connect(lambda: self.main_window.batch_delete_notes(selected_note_ids))
        menu.addAction(delete_action)

    def _populate_move_to_menu(self, menu: QMenu, note_ids: list):
        """填充"移到"子菜单：展示所有文件夹（含层级），支持批量移动"""

        # 构建文件夹树
        try:
            all_folders = self.main_window.note_manager.get_all_folders()
        except Exception:
            all_folders = []

        children_map = {}
        for f in all_folders:
            pid = f.get('parent_folder_id')
            children_map.setdefault(pid, []).append(f)

        def _sort_key(folder: dict):
            return (int(folder.get('order_index', 0) or 0), str(folder.get('name', '')))

        for pid in list(children_map.keys()):
            try:
                children_map[pid].sort(key=_sort_key)
            except Exception:
                pass

        def _add_folder_branch(parent_menu: QMenu, parent_id):
            folders = children_map.get(parent_id, [])
            for folder in folders:
                fid = folder.get('id')
                name = folder.get('name') or '未命名文件夹'

                has_children = bool(children_map.get(fid))

                if has_children:
                    sub = parent_menu.addMenu(f"📁 {name}")
                    _add_folder_branch(sub, fid)

                    # 允许移动到这个父文件夹
                    sub.addSeparator()
                    act_here = QAction(f"移动到 \"{name}\"", self)
                    act_here.triggered.connect(lambda checked=False, _fid=fid:
                                             self.main_window.batch_move_notes(note_ids, _fid))
                    sub.addAction(act_here)
                else:
                    act = QAction(f"📁 {name}", self)
                    act.triggered.connect(lambda checked=False, _fid=fid:
                                        self.main_window.batch_move_notes(note_ids, _fid))
                    parent_menu.addAction(act)

        _add_folder_branch(menu, None)

        # 如果没有任何文件夹，给一个禁用提示
        if not children_map.get(None):
            empty = QAction("（暂无文件夹）", self)
            empty.setEnabled(False)
            menu.addAction(empty)

    def clear_selection(self):
        """清除所有选中项的视觉高亮，并清空 selected_rows 集合。"""
        for row in self.selected_rows:
            item = self.item(row)
            if item:
                widget = self.itemWidget(item)
                if widget and widget.objectName() == "note_item_widget":
                    widget.setProperty("selected", False)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()
        self.selected_rows.clear()

    def update_visual_selection(self):
        """更新所有笔记项的视觉选中状态"""
        for i in range(self.count()):
            item = self.item(i)
            if item and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                widget = self.itemWidget(item)
                if widget and widget.objectName() == "note_item_widget":
                    is_selected = i in self.selected_rows
                    widget.setProperty("selected", is_selected)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()
