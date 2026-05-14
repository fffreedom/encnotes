# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QListWidget, QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
import logging

if TYPE_CHECKING:
    from main_window import MainWindow

logger = logging.getLogger(__name__)
class FolderListWidget(QListWidget):
    """支持文件夹层级拖拽的自定义列表控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None  # 将在MainWindow中设置
        
        # 拖放指示器状态
        self._drop_indicator_position = None  # 'above', 'below', 'on' 或 None
        self._drop_indicator_rect = None  # 指示器的矩形区域
        self._drop_target_item = None  # 目标item
        # 标记鼠标是否真实按下在本 widget 内，防止外部拖拽（如笔记拖拽松手）误触发文件夹拖拽
        self._mouse_pressed_inside = False

    def mousePressEvent(self, event):
        self._mouse_pressed_inside = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._mouse_pressed_inside = False
        super().mouseReleaseEvent(event)

    # _mouse_pressed_inside在mousePressEvent置True，mouseReleaseEvent置False
    # 来确保只有鼠标真实按下在文件夹列表内部时才允许启动拖拽。这样笔记拖拽经过文件夹列表时，由于
    # mousePressEvent从未在FolderListWidget上触发，_mouse_pressed_inside为False，
    # startDrag直接返回，不会误触发文件夹拖拽
    def startDrag(self, supported_actions):
        """只允许从本 widget 内部真实 mousePress 发起的拖拽"""
        if not self._mouse_pressed_inside:
            return
        super().startDrag(supported_actions)

    def dragMoveEvent(self, event):
        """拖动过程中实时更新拖放指示器（支持拖到任意位置，自动检测父文件夹）"""
        # 验证拖动源并确定拖动类型
        drag_type = self._validate_drag_source(event)
        if drag_type is None:
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 获取鼠标位置和目标项
        pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
        target_item = self.itemAt(pos)
        target_folder_id = self._get_folder_id_from_item(target_item)
        # 根据拖动类型分发处理
        if drag_type == 'note':
            self._handle_note_drag_move(event, pos, target_item)
        elif drag_type == 'folder':
            self._handle_folder_drag_move(event, pos, target_item)
    
    def _validate_drag_source(self, event):
        """
        验证拖动源并返回拖动类型
        
        Returns:
            'note': 拖动笔记
            'folder': 拖动文件夹
            None: 无效的拖动源
        """
        drag_source = event.source()
        note_list = self.main_window.note_list
        
        if drag_source == note_list:
            # 验证笔记拖动源
            note_item = note_list.currentItem()
            if not note_item or not note_item.data(Qt.ItemDataRole.UserRole):
                return None
            return 'note'
        
        elif drag_source == self:
            # 验证文件夹拖动源
            folder_item = self.currentItem()
            if not folder_item:
                return None
            folder_data = folder_item.data(Qt.ItemDataRole.UserRole)
            if not self._is_folder_data(folder_data):
                return None
            return 'folder'
        
        return None
    
    def _handle_note_drag_move(self, event, pos, target_item):
        """处理笔记拖动的移动事件"""
        # 笔记必须拖到文件夹上
        if not target_item:
            # 拖到空白处，笔记不能拖到空白处
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 检查目标是否是文件夹
        target_data = target_item.data(Qt.ItemDataRole.UserRole)
        if not self._is_folder_data(target_data):
            # 目标不是文件夹
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 笔记只能拖到文件夹上，显示淡黄色背景
        self._set_drop_indicator('on', target_item)
        event.accept()

    # event.ignore()指当前组件对象忽略这个事件，该事件会将事件传递给父组件对象继续处理
    # event.accept()指当前组件对象接受这个事件，阻止事件继续向上传递给父组件对象
    def _handle_folder_drag_move(self, event, pos, target_item):
        """处理文件夹拖动的移动事件（支持智能位置检测）"""
        # 获取源文件夹ID
        src_folder_id = self._get_current_folder_id()
        if src_folder_id is None:
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 如果拖到空白处，忽略拖动信号，不可拖动到空白处（正常情况下只要在文件夹列表下拖动targe_item都有值，
        # 只有拖动标签下方空白处targe_item才会为None）
        if not target_item:
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 验证目标文件夹，如果无效，忽略拖动信号，不会触发dropEvent
        target_folder_id = self._get_folder_id_from_item(target_item)
        if target_folder_id is None:
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 验证拖动的有效性
        if not self._validate_folder_drop(src_folder_id, target_folder_id):
            self._clear_drop_indicator()
            event.ignore()
            return
        
        # 计算拖放位置（上方/中间/下方）
        position = self._calculate_drop_position(pos, target_item)
        self._set_drop_indicator(position, target_item)
        event.accept()
    
    def _is_folder_data(self, data):
        """检查数据是否是有效的文件夹数据"""
        return isinstance(data, tuple) and len(data) == 2 and data[0] == "folder"
    
    def _get_current_folder_id(self):
        """获取当前选中的文件夹ID"""
        src_item = self.currentItem()
        if not src_item:
            return None
        return self._get_folder_id_from_item(src_item)
    
    def _get_folder_id_from_item(self, item):
        """从item中提取文件夹ID"""
        if not item:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        if not self._is_folder_data(data):
            return None
        return data[1]
    
    def _validate_folder_drop(self, src_folder_id, target_folder_id):
        """
        验证文件夹拖放是否有效
        
        Returns:
            True: 有效
            False: 无效（拖到自己或子孙文件夹）
        """
        # 不能拖到自己身上
        if src_folder_id == target_folder_id:
            return False
        
        # 不能拖到自己的子孙文件夹下（避免循环）
        if self.main_window.note_manager.is_ancestor_folder(src_folder_id, target_folder_id):
            return False
        
        return True
    
    def _calculate_drop_position(self, pos, target_item):
        """
        计算拖放位置（三区域判断）
        
        Returns:
            'above': 插入到目标之前（同级）
            'below': 插入到目标之后（同级）
            'on': 作为目标的子文件夹
        """
        item_rect = self.visualItemRect(target_item)
        relative_y = pos.y() - item_rect.top()
        item_height = item_rect.height()
        
        # 三区域判断逻辑：
        # 上方25%区域 -> 插入到目标之前（同级）
        # 中间50%区域 -> 作为目标的子文件夹
        # 下方25%区域 -> 插入到目标之后（同级）
        
        if relative_y < item_height * 0.25:
            return 'above'
        elif relative_y > item_height * 0.75:
            return 'below'
        else:
            return 'on'
    
    def _set_drop_indicator(self, position, target_item):
        """设置拖放指示器"""
        item_rect = self.visualItemRect(target_item)
        self._drop_indicator_position = position
        self._drop_indicator_rect = item_rect
        self._drop_target_item = target_item
        self.viewport().update()
    
    def _clear_drop_indicator(self):
        """清除拖放指示器"""
        self._drop_indicator_position = None
        self._drop_indicator_rect = None
        self._drop_target_item = None
        self.viewport().update()
    
    def _find_nearest_folder_item(self, y_pos):
        """找到最近的文件夹item（用于拖到空白处时）"""
        nearest_item = None
        min_distance = float('inf')
        
        for i in range(self.count()):
            item = self.item(i)
            if not item:
                continue
            
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if not (isinstance(item_data, tuple) and len(item_data) == 2 and item_data[0] == "folder"):
                continue
            
            item_rect = self.visualItemRect(item)
            item_center_y = item_rect.center().y()
            distance = abs(y_pos - item_center_y)
            
            if distance < min_distance:
                min_distance = distance
                nearest_item = item
        
        return nearest_item
    
    def _folder_has_children(self, folder_id):
        """判断文件夹是否有子文件夹"""
        # 遍历所有item，查找是否有子文件夹
        for i in range(self.count()):
            item = self.item(i)
            if not item:
                continue
            
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if not (isinstance(item_data, tuple) and len(item_data) == 2 and item_data[0] == "folder"):
                continue
            
            child_folder_id = item_data[1]
            # 从数据库查询父文件夹ID
            try:
                cursor = self.main_window.note_manager.conn.cursor()
                cursor.execute("SELECT enc_parent_folder_id FROM enc_folder WHERE enc_pk = ?", (child_folder_id,))
                row = cursor.fetchone()
                if row and row[0] == folder_id:
                    return True
            except Exception:
                pass
        
        return False
    
    def _get_first_child_item(self, parent_item):
        """获取父文件夹的第一个子文件夹item"""
        parent_data = parent_item.data(Qt.ItemDataRole.UserRole)
        if not (isinstance(parent_data, tuple) and len(parent_data) == 2 and parent_data[0] == "folder"):
            return None
        
        parent_folder_id = parent_data[1]
        parent_row = self.row(parent_item)
        
        # 查找下一个item，如果它是子文件夹，则返回
        if parent_row + 1 < self.count():
            next_item = self.item(parent_row + 1)
            if next_item:
                next_data = next_item.data(Qt.ItemDataRole.UserRole)
                if isinstance(next_data, tuple) and len(next_data) == 2 and next_data[0] == "folder":
                    # 检查是否是子文件夹（通过缩进判断）
                    next_widget = self.itemWidget(next_item)
                    parent_widget = self.itemWidget(parent_item)
                    if next_widget and parent_widget:
                        # 简单判断：如果下一个item的缩进大于当前item，则认为是子文件夹
                        # 这里可以通过检查数据库来确认
                        try:
                            cursor = self.main_window.note_manager.conn.cursor()
                            next_folder_id = next_data[1]
                            cursor.execute("SELECT enc_parent_folder_id FROM enc_folder WHERE enc_pk = ?", (next_folder_id,))
                            row = cursor.fetchone()
                            if row and row[0] == parent_folder_id:
                                return next_item
                        except Exception:
                            pass
        
        return None

    def paintEvent(self, event):
        """绘制拖放指示器"""
        super().paintEvent(event)
        
        if not self._drop_indicator_position or not self._drop_indicator_rect:
            return
        
        from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath
        from PyQt6.QtCore import Qt, QRectF

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._drop_indicator_position == 'on':
            # 拖到文件夹上：绘制淡黄色圆角背景
            # 使用 row_widget.geometry()（而非 visualItemRect）作为基础矩形，
            # 因为 QListWidget::item 有 padding: 6px 10px，导致 itemWidget 的实际
            # viewport 坐标（x=10, w=192）与 visualItemRect（x=0, w=212）不同。
            # 再在 left/right 各缩进 8px（对应 FolderRowWidget 样式 margin-left/right: 8px）
            # 并使用 border-radius: 6px，使拖放高亮与真实选中/悬浮高亮形状完全对齐。
            row_widget = self.itemWidget(self._drop_target_item)
            if row_widget:
                base_rect = row_widget.geometry()
            else:
                base_rect = self._drop_indicator_rect
            adjusted_rect = base_rect.adjusted(8, 0, -8, 0)
            path = QPainterPath()
            path.addRoundedRect(QRectF(adjusted_rect), 6, 6)
            painter.fillPath(path, QColor(255, 252, 220, 180))
        else:
            # 拖到文件夹之间：绘制蓝色插入线
            pen = QPen(QColor(0, 122, 255), 2)  # macOS蓝色
            painter.setPen(pen)
            
            if self._drop_indicator_position == 'above':
                # 在item上方绘制线
                y = self._drop_indicator_rect.top()
                x1 = self._drop_indicator_rect.left()
                x2 = self._drop_indicator_rect.right()
                painter.drawLine(x1, y, x2, y)
            elif self._drop_indicator_position == 'below':
                # 在item下方绘制线
                y = self._drop_indicator_rect.bottom()
                x1 = self._drop_indicator_rect.left()
                x2 = self._drop_indicator_rect.right()
                painter.drawLine(x1, y, x2, y)
    
    def _get_drag_source_data(self, event):
        """获取拖拽源数据
        
        Returns:
            tuple: (is_note_drag, src_note_ids, src_folder_id)
                - is_note_drag: 是否是笔记拖拽
                - src_note_ids: 源笔记ID列表（笔记拖拽时）
                - src_folder_id: 源文件夹ID（文件夹拖拽时）
            None: 无效的拖拽源
        """
        note_list = self.main_window.note_list
        folder_list = self
        drag_source = event.source()
        
        # 笔记拖拽
        if drag_source == note_list:
            src_note_ids = []

            # 检查多选笔记
            if hasattr(self.main_window, 'note_list') and self.main_window.note_list.selected_rows:
                for row in sorted(self.main_window.note_list.selected_rows):
                    item = note_list.item(row)
                    if item:
                        note_id = item.data(Qt.ItemDataRole.UserRole)
                        if note_id:
                            src_note_ids.append(note_id)
                    else:
                        logger.debug(f"[笔记拖拽] 行号 {row} 无对应列表项（超出范围）")
            else:
                # 单选笔记
                note_current_item = note_list.currentItem()
                if note_current_item:
                    note_data = note_current_item.data(Qt.ItemDataRole.UserRole)
                    if note_data:
                        src_note_ids = [note_data]

            return (True, src_note_ids, None) if src_note_ids else None
        
        # 文件夹拖拽
        elif drag_source == folder_list:
            folder_current_item = folder_list.currentItem()
            if folder_current_item:
                src_data = folder_current_item.data(Qt.ItemDataRole.UserRole)
                if isinstance(src_data, tuple) and len(src_data) == 2 and src_data[0] == "folder":
                    return (False, None, src_data[1])
        
        return None
    
    def _get_drop_target_folder(self, event):
        """获取拖放目标文件夹ID
        
        Returns:
            int or None: 目标文件夹ID，None表示拖到空白处或顶级
            False: 拖到了非文件夹项（无效目标）
        """
        drop_pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
        target_item = self.itemAt(drop_pos)
        # 拖到了空白处，如是将文件夹拖到顶层，有效，如果是笔记拖动到顶层，无效
        if not target_item:
            return None
        target_data = target_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(target_data, tuple) and len(target_data) == 2 and target_data[0] == "folder":
            return target_data[1]
        # 拖到的元素data不是folder说明拖到了非文件夹项，拖动无效
        return None
    
    def _expand_folder_ancestors(self, folder_id):
        """展开指定文件夹及其所有祖先文件夹"""
        import time
        t_start = time.time()
        
        self.main_window._folder_expanded[folder_id] = True
        
        current_folder_id = folder_id
        ancestor_count = 0
        while current_folder_id:
            folder_info = self.main_window.note_manager.get_folder(current_folder_id)
            if folder_info and folder_info.get('parent_folder_id'):
                parent_id = folder_info['parent_folder_id']
                self.main_window._folder_expanded[parent_id] = True
                current_folder_id = parent_id
                ancestor_count += 1
            else:
                break
        
        t_end = time.time()
        logger.debug(f"[性能] 展开{ancestor_count}个祖先文件夹耗时: {(t_end - t_start)*1000:.2f}ms")
    
    def _delayed_refresh_note_ui(self, note_list, folder_list):
        """延迟刷新笔记拖拽后的UI"""
        import time
        from PyQt6.QtWidgets import QApplication
        
        t_refresh_start = time.time()
        
        try:
            self.main_window.note_manager.conn.commit()
            t_after_commit = time.time()
            logger.debug(f"[性能-笔记拖拽] 数据库commit耗时: {(t_after_commit - t_refresh_start)*1000:.2f}ms")
        except Exception:
            pass
        
        t_before_load_folders = time.time()
        self.main_window.load_folders()
        # load_folders() 重建了所有 row_widget，新 widget 的 selected 属性默认为 False。
        # on_folder_changed 因 current_folder_id 未变而跳过高亮恢复，需手动补调。
        self.main_window._restore_current_item_highlight()
        # 拖拽结束后鼠标仍停在目标文件夹位置，新建的 FolderRowWidget 的 enterEvent 会
        # 立即触发，将 hovered 属性设为 True。调用 clear_hover() 手动清除 hover 高亮。
        fl = self.main_window.folder_list
        for i in range(fl.count()):
            item = fl.item(i)
            if item:
                w = fl.itemWidget(item)
                if isinstance(w, FolderRowWidget):
                    w.clear_hover()
        t_after_load_folders = time.time()
        logger.debug(f"[性能-笔记拖拽] load_folders()耗时: {(t_after_load_folders - t_before_load_folders)*1000:.2f}ms")
        
        t_before_ui_refresh = time.time()
        note_list.viewport().update()
        folder_list.viewport().update()
        note_list.repaint()
        folder_list.repaint()
        QApplication.processEvents()
        t_after_ui_refresh = time.time()
        logger.debug(f"[性能-笔记拖拽] UI刷新耗时: {(t_after_ui_refresh - t_before_ui_refresh)*1000:.2f}ms")
        
        t_refresh_end = time.time()
        logger.debug(f"[性能-笔记拖拽] delayed_refresh总耗时: {(t_refresh_end - t_refresh_start)*1000:.2f}ms")
    
    def _delayed_refresh_folder_ui(self, src_folder_id):
        """延迟刷新文件夹拖拽后的UI"""
        import time
        from PyQt6.QtWidgets import QApplication
        
        t_refresh_start = time.time()
        
        try:
            self.main_window.note_manager.conn.commit()
            t_after_commit = time.time()
            logger.debug(f"[性能] 数据库commit耗时: {(t_after_commit - t_refresh_start)*1000:.2f}ms")
        except Exception:
            pass
        
        t_before_load = time.time()
        self.main_window.load_folders()
        t_after_load = time.time()
        logger.debug(f"[性能] load_folders()耗时: {(t_after_load - t_before_load)*1000:.2f}ms")
        
        t_before_ui_refresh = time.time()
        self.viewport().update()
        self.repaint()
        QApplication.processEvents()
        t_after_ui_refresh = time.time()
        logger.debug(f"[性能] UI刷新耗时: {(t_after_ui_refresh - t_before_ui_refresh)*1000:.2f}ms")
        
        # 重新选中被拖动的文件夹
        self._reselect_folder(src_folder_id)
        
        t_refresh_end = time.time()
        logger.debug(f"[性能] delayed_refresh总耗时: {(t_refresh_end - t_refresh_start)*1000:.2f}ms")
    
    def _handle_note_drop(self, src_note_ids, target_folder_id, t_start):
        """处理笔记拖拽"""
        if not target_folder_id:
            logger.debug("[笔记拖拽] 拖到空白处，不处理")
            return
        import time
        
        t_before_db = time.time()
        logger.debug(f"[性能-笔记拖拽] 准备阶段耗时: {(t_before_db - t_start)*1000:.2f}ms")
        logger.debug(f"[笔记拖拽] 移动 {len(src_note_ids)} 个笔记到文件夹: {target_folder_id}")
        
        # 批量更新笔记所属文件夹
        # 倒序迭代：视觉上排第一的笔记最后移动，获得最新的 enc_modified_at 时间戳，
        # 从而在 ORDER BY enc_modified_at DESC 中排在最前面，保持原始视觉顺序。
        for note_id in reversed(src_note_ids):
            self.main_window.note_manager.move_note_to_folder(note_id, target_folder_id)
        
        t_after_db = time.time()
        logger.debug(f"[性能-笔记拖拽] 数据库更新耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
        
        # 展开目标文件夹及其祖先
        self._expand_folder_ancestors(target_folder_id)

        # 清除拖放指示器，防止目标文件夹残留淡黄色高亮背景
        self._clear_drop_indicator()

        # 延迟刷新UI
        note_list = self.main_window.note_list
        folder_list = self
        QTimer.singleShot(50, lambda: self._delayed_refresh_note_ui(note_list, folder_list))
        
        t_end = time.time()
        logger.debug(f"[性能-笔记拖拽] dropEvent总耗时(不含延迟): {(t_end - t_start)*1000:.2f}ms")
    
    def _handle_folder_drop_on(self, src_folder_id, target_folder_id, t_before_db):
        """处理文件夹拖到另一个文件夹上（改变父文件夹）"""
        import time
        
        self.main_window.note_manager.update_folder_parent(src_folder_id, target_folder_id)
        t_after_db = time.time()
        logger.debug(f"[性能] 数据库更新(改变父文件夹)耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
        
        # 展开目标父文件夹及其祖先
        if target_folder_id:
            self._expand_folder_ancestors(target_folder_id)
    
    def _handle_folder_drop_between(self, src_folder_id, target_folder_id, insert_before, t_before_db):
        """处理文件夹拖到两个文件夹之间（调整顺序）"""
        import time
        
        # 获取目标文件夹的父文件夹ID
        target_folder_info = self.main_window.note_manager.get_folder(target_folder_id)
        if not target_folder_info:
            logger.error(f"[错误] 无法获取目标文件夹信息: {target_folder_id}")
            return
        
        new_parent_id = target_folder_info.get('parent_folder_id')
        
        # 获取源文件夹的当前父文件夹ID
        src_folder_info = self.main_window.note_manager.get_folder(src_folder_id)
        current_parent_id = src_folder_info.get('parent_folder_id') if src_folder_info else None
        
        # 如果父文件夹不同，先改变父文件夹
        if new_parent_id != current_parent_id:
            self.main_window.note_manager.update_folder_parent(src_folder_id, new_parent_id)
            logger.debug(f"[调试] 改变父文件夹: {current_parent_id} -> {new_parent_id}")
        
        # 调整顺序
        success = self.main_window.note_manager.reorder_folder(src_folder_id, target_folder_id, insert_before)
        t_after_db = time.time()
        if success:
            logger.debug(f"[性能] 数据库更新(调整位置)耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
        else:
            logger.debug(f"[性能] 调整位置失败: {(t_after_db - t_before_db)*1000:.2f}ms")
        
        # 展开新父文件夹及其祖先
        if new_parent_id:
            self._expand_folder_ancestors(new_parent_id)
    
    def _handle_folder_drop_blank(self, src_folder_id, t_before_db):
        """处理文件夹拖到空白处（移到顶级）"""
        import time
        
        self.main_window.note_manager.update_folder_parent(src_folder_id, None)
        t_after_db = time.time()
        logger.debug(f"[性能] 数据库更新(移到顶级)耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
    
    def _handle_folder_drop(self, src_folder_id, target_folder_id, t_start):
        """处理文件夹拖拽"""
        import time
        
        t_before_db = time.time()
        logger.debug(f"[性能] 准备阶段耗时: {(t_before_db - t_start)*1000:.2f}ms")
        
        # 检查是否拖到自己上
        if target_folder_id == src_folder_id:
            self._clear_drop_indicator()
            return False
        
        # 根据拖放指示器位置决定操作类型
        if self._drop_indicator_position == 'on':
            self._handle_folder_drop_on(src_folder_id, target_folder_id, t_before_db)
        elif self._drop_indicator_position in ('above', 'below'):
            insert_before = (self._drop_indicator_position == 'above')
            self._handle_folder_drop_between(src_folder_id, target_folder_id, insert_before, t_before_db)
        else:
            self._handle_folder_drop_blank(src_folder_id, t_before_db)
        
        # 清除拖放指示器
        self._clear_drop_indicator()
        
        # 延迟刷新UI
        QTimer.singleShot(50, lambda: self._delayed_refresh_folder_ui(src_folder_id))
        
        t_end = time.time()
        logger.debug(f"[性能] dropEvent总耗时(不含延迟): {(t_end - t_start)*1000:.2f}ms")
        return True

    def _reselect_folder(self, folder_id):
        """重新选中指定的文件夹"""
        import time
        t_start = time.time()
        
        for i in range(self.count()):
            item = self.item(i)
            if item:
                item_data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(item_data, tuple) and len(item_data) == 2 and item_data[0] == "folder":
                    if item_data[1] == folder_id:
                        self.setCurrentItem(item)
                        self.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)
                        t_end = time.time()
                        logger.debug(f"[性能] 重新选中文件夹耗时: {(t_end - t_start)*1000:.2f}ms")
                        return
        
        logger.warning(f"[警告] 未找到被拖动的文件夹 {folder_id}")
    
    # 鼠标拖拽事件触发顺序：mousePressEvent->mouseMoveEvent->dragEnterEvent->dragMoveEvent->dropEvent
    # 鼠标拖拽事件触发顺序：mousePressEvent->mouseReleaseEvent，注意dropEvent和mouseReleaseEvent只会触发一个，不会同时都触发
    # 拖动到空白（标签下面的空白区域或非文件夹列表）处不会触发dropEvent事件，所以这儿的target_folder_id不可能为None
    def dropEvent(self, event):
        """处理拖拽放下事件：支持文件夹拖拽和笔记拖拽"""
        try:
            import time
            t_start = time.time()
            
            # 1. 验证拖拽数据格式
            mime_data = event.mimeData()
            if not mime_data.hasFormat("application/x-qabstractitemmodeldatalist"):
                super().dropEvent(event)
                return
            
            # 2. 获取拖拽源数据
            drag_data = self._get_drag_source_data(event)
            if not drag_data:
                super().dropEvent(event)
                return
            
            is_note_drag, src_note_ids, src_folder_id = drag_data
            
            # 3. 获取目标文件夹
            target_folder_id = self._get_drop_target_folder(event)
            pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
            target_item = self.itemAt(pos)
            logger.debug(f"🔵 [DEBUG] dropEvent triggered, source={event.source()}, source_type={type(event.source()).__name__}, target_item={target_item}, target_folder_id={target_folder_id}")
            if not target_folder_id:
                # 拖到了非文件夹项
                event.ignore()
                return
            
            # 4. 根据拖拽类型执行操作
            if is_note_drag:
                self._handle_note_drop(src_note_ids, target_folder_id, t_start)
                event.accept()
                return
            if not self._handle_folder_drop(src_folder_id, target_folder_id, t_start):
                event.ignore()
                return
            event.accept()
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            super().dropEvent(event)


class FolderRowWidget(QWidget):
    """文件夹列表行 widget，用自定义 hovered 属性替代 CSS :hover，
    使拖拽结束后可通过 clear_hover() 手动清除 hover 高亮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("folder_row_widget")
        # WA_StyledBackground 让 Qt 知道此 widget 有独立的背景样式，
        # 使父控件 QListWidget 的 QSS 属性选择器（[selected="true"]）能正确触发重绘。
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("selected", False)
        self.setProperty("hovered", False)

    def enterEvent(self, event):
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        super().leaveEvent(event)

    def clear_hover(self):
        """拖拽结束后手动清除 hover 状态"""
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()



class FolderTwisty(QLabel):
    """文件夹展开/折叠小箭头（可点击）"""

    toggled = pyqtSignal(str)

    def __init__(self, folder_id: str, expanded: bool, parent=None):
        super().__init__(parent)
        self._folder_id = folder_id
        self.setExpanded(expanded)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(14)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            color: #666666;
            font-size: 12px;
            background: transparent;
        """)

    def setExpanded(self, expanded: bool):
        # ▶ (折叠) / ▼ (展开)
        self.setText("▼" if expanded else "▶")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggled.emit(self._folder_id)
            event.accept()
            return
        super().mousePressEvent(event)

