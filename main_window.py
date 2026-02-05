#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口 - Mac风格三栏布局
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QListWidget, QToolBar, QPushButton,
    QListWidgetItem, QMessageBox, QFileDialog, QDialog,
    QLabel, QCheckBox, QProgressDialog, QInputDialog, QMenu,
    QSizePolicy
)

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QDesktopServices
from PyQt6.QtCore import QUrl

from note_editor import NoteEditor
from note_manager import NoteManager
from export_manager import ExportManager
from icloud_sync import CloudKitSyncManager
from password_dialog import UnlockDialog, SetupPasswordDialog, ChangePasswordDialog
import datetime
import logging

logger = logging.getLogger(__name__)


class ElidedLabel(QLabel):
    """宽度不足时自动显示省略号的Label（用于setItemWidget场景）"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text or ""
        super().setText(self._full_text)

    def setFullText(self, text: str):
        self._full_text = text or ""
        self._update_elide()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self):
        fm = self.fontMetrics()
        # 预留1px避免某些平台紧贴边缘导致最后一个字符被截断
        available = max(0, self.width() - 1)
        elided = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available)
        super().setText(elided)


class FolderListWidget(QListWidget):
    """支持文件夹层级拖拽的自定义列表控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None  # 将在MainWindow中设置
        
        # 拖放指示器状态
        self._drop_indicator_position = None  # 'above', 'below', 'on' 或 None
        self._drop_indicator_rect = None  # 指示器的矩形区域
        self._drop_target_item = None  # 目标item
    
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
        logger.debug(f"DragMove: pos={pos}, target_item={target_item}, target_folder_id={target_folder_id}")
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
                cursor.execute("SELECT ZPARENTFOLDERID FROM ZFOLDER WHERE Z_PK = ?", (child_folder_id,))
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
                            cursor.execute("SELECT ZPARENTFOLDERID FROM ZFOLDER WHERE Z_PK = ?", (next_folder_id,))
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
        
        from PyQt6.QtGui import QPainter, QPen, QColor
        from PyQt6.QtCore import Qt
        
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self._drop_indicator_position == 'on':
            # 拖到文件夹上：绘制淡黄色背景
            painter.fillRect(self._drop_indicator_rect, QColor(255, 252, 220, 180))
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
            if hasattr(self.main_window, 'selected_note_rows') and self.main_window.selected_note_rows:
                for row in self.main_window.selected_note_rows:
                    item = note_list.item(row)
                    if item:
                        note_id = item.data(Qt.ItemDataRole.UserRole)
                        if note_id:
                            src_note_ids.append(note_id)
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
        t_after_load_folders = time.time()
        logger.debug(f"[性能-笔记拖拽] load_folders()耗时: {(t_after_load_folders - t_before_load_folders)*1000:.2f}ms")
        
        t_before_load_notes = time.time()
        self.main_window.load_notes()
        t_after_load_notes = time.time()
        logger.debug(f"[性能-笔记拖拽] load_notes()耗时: {(t_after_load_notes - t_before_load_notes)*1000:.2f}ms")
        
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
        for note_id in src_note_ids:
            self.main_window.note_manager.move_note_to_folder(note_id, target_folder_id)
        
        t_after_db = time.time()
        logger.debug(f"[性能-笔记拖拽] 数据库更新耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
        
        # 展开目标文件夹及其祖先
        self._expand_folder_ancestors(target_folder_id)
        
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
        logger.debug("🔵 [DEBUG] dropEvent triggered")
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

class NoteListWidget(QListWidget):
    """支持笔记拖拽到文件夹的自定义列表控件

    额外：自绘“笔记项分隔线”，让分隔线与标题起点对齐，且在选中黄色高亮的底部之外。
    """

    # 用 item.data 存储分隔线参数（避免改动太多结构）
    _SEP_ENABLED_ROLE = Qt.ItemDataRole.UserRole + 1
    _SEP_LEFT_ROLE = Qt.ItemDataRole.UserRole + 2
    _SEP_RIGHT_ROLE = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None  # 将在MainWindow中设置
        self.last_selected_row = None  # 记录上次选中的行，用于Shift多选
        self.press_pos = None  # 记录鼠标按下的位置
        self.press_row = None  # 记录鼠标按下时的行号
        self.was_in_multi_select = False  # 记录按下时是否处于多选状态
        
        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def paintEvent(self, event):
        super().paintEvent(event)

        from PyQt6.QtGui import QPainter, QPen, QColor

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
    
    def _handle_command_click(self, clicked_row):
        """处理 Command/Ctrl 键点击（跳选：添加/移除单个项）
        
        Args:
            clicked_row: int 点击的行号
        """
        if self.main_window:
            self.main_window.toggle_note_selection(clicked_row)
        self.last_selected_row = clicked_row
    
    def _handle_shift_click(self, clicked_row):
        """处理 Shift 键点击（范围选择）
        
        Args:
            clicked_row: int 点击的行号
        """
        if self.main_window and self.last_selected_row is not None:
            self.main_window.select_note_range(self.last_selected_row, clicked_row)
    
    def _is_item_in_multi_select(self, clicked_row):
        """判断点击的item是否在多选集合中
        
        Args:
            clicked_row: int 点击的行号
            
        Returns:
            bool: 是否在多选集合中
        """
        if not self.main_window:
            return False
        return clicked_row in self.main_window.selected_note_rows
    
    def _keep_multi_select_for_drag(self, clicked_row, event_pos):
        """保持多选状态用于拖动
        
        Args:
            clicked_row: int 点击的行号
            event_pos: QPoint 点击位置
        """
        # 记录点击信息，用于在mouseReleaseEvent中判断是否发生了拖动
        self.press_pos = event_pos
        self.press_row = clicked_row
        self.was_in_multi_select = len(self.main_window.selected_note_rows) > 1
        
        # 保持多选状态，但需要设置currentItem以支持拖动
        self.blockSignals(True)
        self.setCurrentRow(clicked_row)
        self.blockSignals(False)
        
        # 强制刷新视觉选中状态，确保所有选中项都正确显示
        self.main_window._update_visual_selection()
    
    def _handle_normal_click(self, clicked_row, event_pos):
        """处理普通点击（单选或保持多选用于拖动）
        
        Args:
            clicked_row: int 点击的行号
            event_pos: QPoint 点击位置
        """
        if not self.main_window:
            return
        
        # 如果点击的笔记已经在多选集合中，保持多选状态（用于拖动）
        if self._is_item_in_multi_select(clicked_row):
            self._keep_multi_select_for_drag(clicked_row, event_pos)
        else:
            # 点击的是未选中的笔记，执行单选
            self.main_window.select_single_note(clicked_row)
        
        self.last_selected_row = clicked_row
    
    def mousePressEvent(self, event):
        """处理鼠标按下事件，支持多选
        
        Args:
            event: QMouseEvent 鼠标事件
        """
        logger.debug("🟡 [DEBUG] mousePressEvent triggered")
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
            self._handle_command_click(clicked_row)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Shift键：范围选择
            self._handle_shift_click(clicked_row)
        else:
            # 普通点击：单选或保持多选（用于拖动）
            self._handle_normal_click(clicked_row, event.pos())
        
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
              f"was_in_multi_select: {self.was_in_multi_select}")
    
    def _is_click_not_drag(self, release_pos, threshold=5):
        """判断是点击还是拖动
        
        Args:
            release_pos: QPoint 鼠标释放位置
            threshold: int 判断阈值（像素），默认5像素
            
        Returns:
            bool: True表示是点击，False表示是拖动
        """
        if self.press_pos is None:
            return False
        
        move_distance = (release_pos - self.press_pos).manhattanLength()
        logger.debug(f"[mouseReleaseEvent] Move distance: {move_distance}")
        return move_distance < threshold
    
    def _handle_click_in_multi_select(self):
        """处理多选状态下的点击事件（取消多选，只选中当前笔记）"""
        if self.main_window and self.press_row is not None:
            logger.debug(f"[mouseReleaseEvent] Canceling multi-select, "
                  f"selecting single note: {self.press_row}")
            self.main_window.select_single_note(self.press_row)
    
    def _clear_press_info(self):
        """清除记录的按下信息"""
        self.press_pos = None
        self.press_row = None
        self.was_in_multi_select = False
    
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
            if self.press_pos is not None and self.was_in_multi_select:
                # 4. 判断是点击还是拖动
                if self._is_click_not_drag(event.pos()):
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
    
    def _show_blank_area_menu(self, global_pos):
        """显示空白区域的右键菜单（仅包含新建笔记）"""
        menu = QMenu(self)
        new_note_action = QAction("新建笔记", self)
        new_note_action.triggered.connect(lambda: self.main_window.create_note_in_current_folder())
        
        # 在"所有笔记"和"最近删除"视图中禁用
        if self.main_window.current_folder_id is None or self.main_window.is_viewing_deleted:
            new_note_action.setEnabled(False)
        
        menu.addAction(new_note_action)
        menu.exec(global_pos)
    
    def _handle_note_selection(self, clicked_item):
        """处理笔记选择逻辑，返回选中的笔记ID列表"""
        clicked_row = self.row(clicked_item)
        
        # 如果点击的笔记不在选中集合中，则只选中当前笔记
        if clicked_row not in self.main_window.selected_note_rows:
            self.main_window.select_single_note(clicked_row)
        
        # 获取所有选中的笔记ID
        selected_note_ids = []
        for row in sorted(self.main_window.selected_note_rows):
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
        if self.main_window.current_folder_id is None or self.main_window.is_viewing_deleted:
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


class MainWindow(QMainWindow):
    """主窗口类"""

    def _is_empty_new_note(self, note: dict) -> bool:

        """判断某条笔记是否为"空的新笔记草稿"。

        约束：一个文件夹下只允许存在一个这样的草稿，用于避免用户连续创建多个空白笔记。

        判定规则（与"保存标题规则"保持一致）：
        - 只要整条笔记（纯文本）为空（没有任何非空白字符），就认为是"空草稿"
        - 不再强依赖数据库里当下的 title 值（因为 title 会随着输入变化而变为"无标题"等）
        """
        try:
            if not note:
                return False

            # content 是HTML字符串（NoteManager._row_to_dict 已解密），用 toPlainText 语义的方式提取
            from bs4 import BeautifulSoup
            html = note.get('content') or ''
            plain = BeautifulSoup(html, 'html.parser').get_text(separator='\n')
            # 移除零宽度空格（U+200B）后再判断是否为空
            plain_without_zwsp = (plain or '').replace('\u200B', '')
            return plain_without_zwsp.strip() == ""
        except Exception:
            return False

    def _current_folder_has_empty_new_note(self) -> bool:
        """当前选中文件夹下是否已存在一个“空的新笔记草稿”。"""
        if not self.current_folder_id:
            return False
        try:
            notes = self.note_manager.get_notes_by_folder(self.current_folder_id)
        except Exception:
            notes = []
        for n in notes:
            if self._is_empty_new_note(n):
                return True
        return False

    def _update_new_note_action_enabled(self):
        """根据当前上下文启用/禁用"新建笔记"动作。
        
        规则：
        - "最近删除"和"所有笔记"视图：不允许新建笔记
        - 自定义文件夹：允许新建笔记（即使存在空笔记也允许，会自动跳转）
        """
        # 必须选中了自定义文件夹（current_folder_id 有值）
        if not self.current_folder_id:
            enabled = False
        else:
            # 自定义文件夹：始终允许新建（即使有空笔记）
            enabled = True

        for attr in ("new_note_action_toolbar", "new_note_action_menu"):
            act = getattr(self, attr, None)
            if act is not None:
                act.setEnabled(enabled)

    def _handle_folder_rename_escape(self, obj, event):
        """处理文件夹重命名时的 ESC 取消操作。
        
        Args:
            obj: 事件对象
            event: 事件
            
        Returns:
            bool: 如果处理了事件返回 True，否则返回 False
        """
        try:
            if event.type() == event.Type.KeyPress:
                from PyQt6.QtCore import Qt
                if event.key() == Qt.Key.Key_Escape:
                    # 标记取消，让 editingFinished 走取消分支
                    if hasattr(obj, "setProperty"):
                        obj.setProperty("_rename_cancelled", True)
                    obj.clearFocus()
                    event.accept()
                    return True
        except Exception:
            pass
        return False

    def _handle_empty_folder_editor_click(self, obj, event):
        """处理空文件夹时点击编辑器自动新建笔记。
        
        Args:
            obj: 事件对象
            event: 事件
            
        Returns:
            bool: 如果处理了事件返回 True，否则返回 False
        """
        try:
            from PyQt6.QtCore import QEvent, Qt
            
            # 检查是否启用了点击创建功能，且是编辑器的左键点击
            if not (
                getattr(self, "_editor_click_to_create_note_enabled", False)
                and obj is getattr(getattr(self.editor, "text_edit", None), "viewport", lambda: None)()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                return False
            
            # 只有"选中了某个自定义文件夹 + 当前没有选中笔记 + 当前不在标签视图"才自动创建
            if self.current_folder_id and self._get_current_note_id() is None and self.current_tag_id is None:
                self.create_note_in_folder(self.current_folder_id, default_title="新笔记")
                event.accept()
                return True
        except Exception:
            pass
        return False

    def _is_editor_click(self, obj):
        """检查是否点击了编辑器（viewport 或 text_edit 本身）。
        
        Args:
            obj: 事件对象
            
        Returns:
            bool: 如果是编辑器点击返回 True，否则返回 False
        """
        return (
            obj is getattr(getattr(self.editor, "text_edit", None), "viewport", lambda: None)()
            or obj is getattr(self.editor, "text_edit", None)
        )

    def _handle_empty_tag_editor_click(self, obj, event):
        """处理空标签时点击编辑器，阻止进入可编辑状态。
        
        Args:
            obj: 事件对象
            event: 事件
            
        Returns:
            bool: 如果处理了事件返回 True，否则返回 False
        """
        try:
            from PyQt6.QtCore import QEvent
            
            # 检查是否是编辑器的鼠标点击，且当前在空标签视图
            if not (
                self._is_editor_click(obj)
                and event.type() == QEvent.Type.MouseButtonPress
                and self.current_tag_id is not None
                and self._get_current_note_id() is None
            ):
                return False
            
            # 检查当前标签是否为空标签
            tag = self.note_manager.get_tag(self.current_tag_id)
            if tag:
                tag_name = str(tag.get('name', '') or '').strip()
                if not tag_name:
                    # 空标签：阻止点击事件，不让编辑器获得焦点
                    event.accept()
                    return True
        except Exception:
            pass
        return False

    def eventFilter(self, obj, event):
        """事件过滤器，处理各种特殊的用户交互事件。
        
        处理以下场景：
        1. 文件夹重命名时的 ESC 取消
        2. 空文件夹时点击编辑器自动新建笔记
        3. 空标签时阻止编辑器进入可编辑状态
        
        Args:
            obj: 事件对象
            event: 事件
            
        Returns:
            bool: 如果处理了事件返回 True，否则调用父类方法
        """
        # 处理文件夹重命名的 ESC 取消
        if self._handle_folder_rename_escape(obj, event):
            return True
        
        # 处理空文件夹时点击编辑器自动新建笔记
        if self._handle_empty_folder_editor_click(obj, event):
            return True
        
        # 处理空标签时阻止编辑器进入可编辑状态
        if self._handle_empty_tag_editor_click(obj, event):
            return True
        
        return super().eventFilter(obj, event)


    def __init__(self):
        super().__init__()
        self.note_manager = NoteManager()

        self.export_manager = ExportManager()
        self.sync_manager = CloudKitSyncManager(self.note_manager)
        
        # 视图状态
        self.current_folder_id = None  # 当前选中的文件夹ID
        self.current_tag_id = None  # 当前选中的标签ID
        self.is_viewing_deleted = False  # 是否正在查看最近删除
        self.custom_folders = []  # 自定义文件夹列表
        self.tags = []  # 标签列表
        
        # 每个视图记录上次编辑的笔记：{view_key: note_id}
        # view_key 格式：
        #   - "system:all_notes" - 所有笔记
        #   - "system:deleted" - 最近删除
        #   - "folder:{folder_id}" - 自定义文件夹
        #   - "tag:{tag_id}" - 标签
        self._last_note_per_view = {}

        # 编辑器初始化标志：防止启动时保存空笔记覆盖数据库内容
        self._editor_initialized = False

        # 多选状态
        self.selected_note_rows = set()  # 当前选中的笔记行号集合

        # 文件夹展开/折叠状态（folder_id -> bool），默认展开
        self._folder_expanded = {}

        # 加密管理器
        self.encryption_manager = self.note_manager.encryption_manager

        # 检查是否需要设置密码或解锁
        if not self._handle_encryption_setup():
            # 用户取消了密码设置或解锁，退出应用
            import sys
            sys.exit(0)

        self.init_ui()
        self.load_folders(True)  # 加载文件夹并恢复状态

        # 设置自动同步定时器（每5分钟）
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.auto_sync)
        self.sync_timer.start(300000)  # 5分钟

    def _restore_window_geometry(self):
        """恢复窗口大小和位置。
        
        若用户曾调整过窗口大小，则按上次值恢复。
        若没有历史记录（首次启动），默认最大化。
        """
        restored = False
        try:
            import base64
            geo_str = self.note_manager.get_app_state("main_window/geometry")
            if geo_str:
                geo = base64.b64decode(geo_str.encode())
                restored = self.restoreGeometry(geo)
        except Exception:
            restored = False

        # 首次启动：默认最大化（占满当前显示器的可用工作区，不覆盖菜单栏/任务栏）
        if not restored:
            try:
                self.showMaximized()
            except Exception:
                self.setGeometry(100, 100, 1200, 800)

        # 可选：恢复窗口状态（例如工具栏停靠等）；失败不影响启动
        try:
            import base64
            st_str = self.note_manager.get_app_state("main_window/state")
            if st_str:
                st = base64.b64decode(st_str.encode())
                self.restoreState(st)
        except Exception:
            pass

    def _create_main_splitter(self):
        """创建主分割器。
        
        Returns:
            QSplitter: 配置好的水平分割器
        """
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e6e6e6;
            }
        """)
        return splitter

    def _setup_folder_list_basic(self):
        """设置文件夹列表的基本属性。"""
        self.folder_list = FolderListWidget()
        self.folder_list.main_window = self
        self.folder_list.setMaximumWidth(500)
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_list.setTextElideMode(Qt.TextElideMode.ElideRight)

    def _setup_folder_list_drag_drop(self):
        """配置文件夹列表的拖拽功能。"""
        self.folder_list.setDragEnabled(True)
        self.folder_list.setAcceptDrops(True)
        self.folder_list.setDropIndicatorShown(True)
        try:
            from PyQt6.QtWidgets import QAbstractItemView
            # 注意：不要用 InternalMove。InternalMove 会执行"列表内重排"，看起来只改变位置不改变层级。
            # 我们把 Drop 交给 eventFilter 处理：写入 ZPARENTFOLDERID 后再 load_folders() 重新渲染层级树。
            self.folder_list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        except Exception:
            pass
        self.folder_list.setDefaultDropAction(Qt.DropAction.MoveAction)

    def _setup_folder_list_style(self):
        """设置文件夹列表的样式。"""
        self.folder_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #f5f5f5;
                font-size: 13px;
                outline: none;
            }

            QWidget#folder_row_widget {
                background: transparent;
            }
            QWidget#folder_row_widget[selected="true"] {
                background-color: #FFE066;
                border-radius: 6px;
                margin-left: 8px;
                margin-right: 8px;
            }

            QListWidget::item {
                padding: 6px 10px;
                border: none;
                outline: none;
            }
            QListWidget::item:selected,
            QListWidget::item:selected:active,
            QListWidget::item:selected:!active {
                background-color: transparent;
                color: #000000;
                border: none;
                outline: none;
            }

            QListWidget::item:hover {
                background-color: #FFF4CC;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                border: none;
                outline: none;
            }

            /* 让滚动条更轻：避免出现边框/箭头等 */
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #c8c8c8;
                min-height: 24px;
                border: none;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
            }
        """)

    def _setup_folder_list_signals(self):
        """连接文件夹列表的信号。"""
        self.folder_list.setCurrentRow(0)
        self.folder_list.currentRowChanged.connect(self.on_folder_changed)
        self.folder_list.itemDoubleClicked.connect(self.on_folder_item_double_clicked)
        self.folder_list.itemClicked.connect(self.on_folder_item_clicked)

        # 让 MainWindow.eventFilter 能收到 folder_list 的 Drop 事件
        try:
            self.folder_list.installEventFilter(self)
        except Exception:
            pass

        # 允许"选中后再次单击"进入重命名（仿Finder）
        self.folder_list.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)
        self._last_folder_click_folder_id = None
        self._last_folder_click_ms = 0

    def _setup_folder_list_context_menu(self):
        """设置文件夹列表的右键菜单。"""
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self.show_folder_context_menu)

    def _setup_folder_list_scrollbar(self):
        """配置文件夹列表的滚动条（默认隐藏，交互时显示）。"""
        self.folder_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._folder_scrollbar_hide_timer = QTimer(self)
        self._folder_scrollbar_hide_timer.setSingleShot(True)
        self._folder_scrollbar_hide_timer.timeout.connect(self._hide_folder_scrollbar)

        self._folder_scrollbar_dragging = False
        folder_sb = self.folder_list.verticalScrollBar()
        folder_sb.valueChanged.connect(self._show_folder_scrollbar_temporarily)
        folder_sb.sliderPressed.connect(self._on_folder_scrollbar_pressed)
        folder_sb.sliderReleased.connect(self._on_folder_scrollbar_released)

    def _init_folder_list(self):
        """初始化文件夹列表（包含所有配置）。"""
        self._setup_folder_list_basic()
        self._setup_folder_list_drag_drop()
        self._setup_folder_list_style()
        self._setup_folder_list_signals()
        self._setup_folder_list_context_menu()
        self._setup_folder_list_scrollbar()

    def _setup_note_list_basic(self):
        """设置笔记列表的基本属性。"""
        self.note_list = NoteListWidget()
        self.note_list.main_window = self
        self.note_list.setMaximumWidth(500)
        self.note_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # 配置笔记列表的滚动条（默认隐藏，交互时显示）。
        self.note_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.note_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _setup_note_list_drag_drop(self):
        """配置笔记列表的拖拽功能（只允许拖出）。"""
        self.note_list.setDragEnabled(True)
        # 笔记列表不接受拖入
        self.note_list.setAcceptDrops(False)
        self.note_list.setDropIndicatorShown(False)
        # 只允许拖出
        self.note_list.setDragDropMode(QListWidget.DragDropMode.DragOnly)

    def _setup_note_list_style(self):
        """设置笔记列表的样式。"""
        self.note_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #ffffff;
                font-size: 15px;
                outline: none;
            }
            QListWidget::viewport {
                background: transparent;
            }

            QListWidget::item {
                padding: 0px;
                border: none;
                outline: none;
            }
            QListWidget::item:selected {
                background: transparent;
                color: #000000;
                padding: 0px;
                border: none;
                outline: none;
            }
            QListWidget::item:hover {
                background: transparent;
                padding: 0px;
                border: none;
                outline: none;
            }

            QListWidget::item:focus {
                border: none;
                outline: none;
            }

            /* 浮动滚动条：只显示一条粗线（滑块），不显示边框/箭头/轨道灰底 */
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #bdbdbd;
                min-height: 24px;
                border: none;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
            }
        """)

    def _setup_note_list_scrollbar(self):
        self._note_scrollbar_hide_timer = QTimer(self)
        self._note_scrollbar_hide_timer.setSingleShot(True)
        self._note_scrollbar_hide_timer.timeout.connect(self._hide_note_scrollbar)

        self._note_scrollbar_dragging = False
        sb = self.note_list.verticalScrollBar()
        sb.valueChanged.connect(self._show_note_scrollbar_temporarily)
        sb.sliderPressed.connect(self._on_note_scrollbar_pressed)
        sb.sliderReleased.connect(self._on_note_scrollbar_released)

    def _setup_note_list_signals(self):
        """连接笔记列表的信号。"""
        self.note_list.currentItemChanged.connect(self.on_note_selected)

    def _init_note_list(self):
        """初始化笔记列表（包含所有配置）。"""
        self._setup_note_list_basic()
        self._setup_note_list_drag_drop()
        self._setup_note_list_style()
        self._setup_note_list_scrollbar()
        self._setup_note_list_signals()

    def _init_editor(self):
        """初始化编辑器。"""
        self.editor = NoteEditor(self.note_manager, main_window=self)
        self.editor.textChanged.connect(self.on_text_changed)

        # 空文件夹点击编辑器：自动新建笔记（仿备忘录行为）
        self._editor_click_to_create_note_enabled = True
        try:
            # QTextEdit 的鼠标事件通常由 viewport() 接收；
            # 如果只装在 QTextEdit 本体上，可能收不到 MouseButtonPress。
            self.editor.text_edit.viewport().installEventFilter(self)
        except Exception:
            try:
                self.editor.text_edit.installEventFilter(self)
            except Exception:
                pass

    def _setup_splitter_widgets(self, splitter):
        """将所有部件添加到分割器并设置比例。
        
        Args:
            splitter: QSplitter 对象
        """
        splitter.addWidget(self.folder_list)
        splitter.addWidget(self.note_list)
        splitter.addWidget(self.editor)
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 5)

        # 设置分割器启动时初始宽度，文件夹列表和笔记列表最大宽度由各自的setMaximumWidth设置，最小宽度不设置
        # 这里把左侧文件夹栏稍微加宽，避免"新建文件夹"等默认名称显示不全
        splitter.setSizes([200, 200, 900])

    def init_ui(self):
        """初始化用户界面。
        
        主要步骤：
        1. 恢复窗口大小和位置
        2. 创建中心部件和主布局
        3. 创建分割器
        4. 初始化文件夹列表
        5. 初始化笔记列表
        6. 初始化编辑器
        7. 设置分割器比例
        8. 创建工具栏和菜单栏
        """
        self.setWindowTitle("加密笔记")

        # 恢复窗口大小和位置
        self._restore_window_geometry()

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建分割器
        splitter = self._create_main_splitter()
        
        # 初始化三个主要部件
        self._init_folder_list()
        self._init_note_list()
        self._init_editor()
        
        # 将部件添加到分割器
        self._setup_splitter_widgets(splitter)
        
        # 添加到主布局
        main_layout.addWidget(splitter)
        
        # 创建工具栏和菜单栏
        self.create_toolbar()
        self.create_menubar()

    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # 新建笔记按钮
        new_note_action = QAction("➕ 新建笔记", self)
        new_note_action.setShortcut(QKeySequence("Ctrl+N"))
        new_note_action.triggered.connect(self.create_new_note)
        toolbar.addAction(new_note_action)

        # 保存引用：用于根据“是否已存在空的新笔记”动态禁用
        self.new_note_action_toolbar = new_note_action

        
        # 新建文件夹按钮
        new_folder_action = QAction("📁 新建文件夹", self)
        new_folder_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_folder_action.triggered.connect(self.create_new_folder)
        toolbar.addAction(new_folder_action)
        
        # 新建标签按钮
        new_tag_action = QAction("🏷️ 新建标签", self)
        new_tag_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tag_action.triggered.connect(self.create_new_tag)
        toolbar.addAction(new_tag_action)
        
        toolbar.addSeparator()
        
    def create_menubar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        new_action = QAction("新建笔记", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.create_new_note)
        file_menu.addAction(new_action)

        # 保存引用：用于根据“是否已存在空的新笔记”动态禁用
        self.new_note_action_menu = new_action

        
        new_folder_action = QAction("新建文件夹", self)
        new_folder_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_folder_action.triggered.connect(self.create_new_folder)
        file_menu.addAction(new_folder_action)
        
        file_menu.addSeparator()
        
        # 导出子菜单
        export_menu = file_menu.addMenu("导出")
        
        export_pdf_action = QAction("导出为PDF", self)
        export_pdf_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        export_pdf_action.triggered.connect(self.export_to_pdf)
        export_menu.addAction(export_pdf_action)
        
        export_word_action = QAction("导出为Word", self)
        export_word_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
        export_word_action.triggered.connect(self.export_to_word)
        export_menu.addAction(export_word_action)
        
        export_md_action = QAction("导出为Markdown", self)
        export_md_action.setShortcut(QKeySequence("Ctrl+Shift+M"))
        export_md_action.triggered.connect(self.export_to_markdown)
        export_menu.addAction(export_md_action)
        
        export_html_action = QAction("导出为HTML", self)
        export_html_action.triggered.connect(self.export_to_html)
        export_menu.addAction(export_html_action)
        
        export_menu.addSeparator()
        
        open_export_folder_action = QAction("打开导出文件夹", self)
        open_export_folder_action.triggered.connect(self.open_export_folder)
        export_menu.addAction(open_export_folder_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu("编辑")
        
        # 插入菜单
        insert_menu = menubar.addMenu("插入")
        
        # 插入图片
        image_action = QAction("插入图片", self)
        image_action.setShortcut(QKeySequence("Ctrl+I"))
        image_action.triggered.connect(self.insert_image)
        insert_menu.addAction(image_action)
        
        # 插入附件
        attachment_action = QAction("插入附件", self)
        attachment_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        attachment_action.triggered.connect(self.insert_attachment)
        insert_menu.addAction(attachment_action)
        
        insert_menu.addSeparator()
        
        latex_action = QAction("插入 LaTeX 公式", self)
        latex_action.setShortcut(QKeySequence("Ctrl+L"))
        latex_action.triggered.connect(self.editor.insert_latex)
        insert_menu.addAction(latex_action)
        
        mathml_action = QAction("插入 MathML 公式", self)
        mathml_action.setShortcut(QKeySequence("Ctrl+M"))
        mathml_action.triggered.connect(self.editor.insert_mathml)
        insert_menu.addAction(mathml_action)
        
        # 同步菜单
        sync_menu = menubar.addMenu("同步")
        
        enable_sync_action = QAction("启用iCloud同步", self)
        enable_sync_action.setCheckable(True)
        enable_sync_action.setChecked(self.sync_manager.sync_enabled)
        enable_sync_action.triggered.connect(self.toggle_sync)
        sync_menu.addAction(enable_sync_action)
        self.enable_sync_action = enable_sync_action
        
        sync_menu.addSeparator()
        
        sync_now_action = QAction("立即同步", self)
        sync_now_action.setShortcut(QKeySequence("Ctrl+S"))
        sync_now_action.triggered.connect(self.sync_now)
        sync_menu.addAction(sync_now_action)
        
        pull_sync_action = QAction("从iCloud拉取", self)
        pull_sync_action.triggered.connect(self.pull_from_icloud)
        sync_menu.addAction(pull_sync_action)
        
        sync_menu.addSeparator()
        
        sync_status_action = QAction("同步状态", self)
        sync_status_action.triggered.connect(self.show_sync_status)
        sync_menu.addAction(sync_status_action)
        
        # 安全菜单
        security_menu = menubar.addMenu("安全")
        
        change_password_action = QAction("修改密码", self)
        change_password_action.triggered.connect(self.change_password)
        security_menu.addAction(change_password_action)
        
        security_menu.addSeparator()
        
        lock_action = QAction("锁定笔记", self)
        lock_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        lock_action.triggered.connect(self.lock_notes)
        security_menu.addAction(lock_action)
        
    def _get_time_group(self, note_date):
        """根据笔记创建时间获取时间分组名称"""
        from datetime import datetime, timedelta
        
        try:
            # 解析笔记的创建时间
            if isinstance(note_date, str):
                note_dt = datetime.fromisoformat(note_date)
            else:
                note_dt = note_date
            
            # 获取当前时间（去掉时分秒，只保留日期）
            now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            note_date_only = note_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 计算时间差
            delta = now - note_date_only
            days = delta.days
            
            # 根据时间差返回分组名称
            if days == 0:
                return "今天"
            elif days == 1:
                return "昨天"
            elif days <= 7:
                return "过去一周"
            elif days <= 30:
                return "过去30天"
            else:
                # 按年份分组
                return f"{note_dt.year}年"
        except Exception as e:
            logger.error(f"解析时间失败: {e}")
            return "其他"
    
    def _add_group_header(self, group_name):
        """添加分组标题"""
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中
        
        # 创建分组标题widget
        widget = QWidget()
        widget_layout = QVBoxLayout(widget)
        widget_layout.setContentsMargins(16, 12, 8, 8)  # 分组标识缩进16px（比笔记更靠左）
        widget_layout.setSpacing(0)
        
        # 分组标题（加粗）
        header_label = QLabel(group_name)
        header_label.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            color: #666666;
            border: none;
            background: transparent;
            padding: 0px;
            margin: 0px;
        """)
        widget_layout.addWidget(header_label)

        # 分组标题与下方列表的分隔线：左侧对齐分组文字(16px)，右侧对齐笔记分隔线(8px)
        widget_layout.addSpacing(6)
        group_separator = QWidget()
        group_separator.setFixedHeight(1)
        group_separator.setStyleSheet("""
            background-color: #e0e0e0;
            margin-left: 0px;
            margin-right: 8px;
        """)
        widget_layout.addWidget(group_separator)

        widget.setFixedHeight(47)  # 标题 + 间距 + 1px分隔线
        
        # 让分组标题也参与“自绘分隔线”：
        # - 分组标题本身不可选中，但我们希望它也能画一条“顶部线”，让视觉上分组之间更连贯。
        # - left/right 与分组 separator 保持一致（左 16 / 右 8）。
        try:
            item.setData(Qt.ItemDataRole.UserRole + 1, True)
            item.setData(Qt.ItemDataRole.UserRole + 2, 16)
            item.setData(Qt.ItemDataRole.UserRole + 3, 8)
        except Exception:
            pass

        self.note_list.addItem(item)
        self.note_list.setItemWidget(item, widget)
        # 注意这里Group的宽度同样会影响笔记的宽度，所以需要设置成和笔记item相同的宽度
        item.setSizeHint(QSize(200, 47))

    
    def _clear_note_list_widgets(self):
        """清除笔记列表中的所有自定义widget。
        
        必须在clear()之前删除所有widget，避免重叠。
        """
        # 清除多选状态
        self.selected_note_rows.clear()
        if hasattr(self, 'note_list') and self.note_list:
            self.note_list.last_selected_row = None
        
        # 手动删除所有自定义widget
        widgets_to_delete = []
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            widget = self.note_list.itemWidget(item)
            if widget:
                # 先解除widget与item的关联
                self.note_list.setItemWidget(item, None)
                # 收集需要删除的widget
                widgets_to_delete.append(widget)
        
        # 删除所有widget
        for widget in widgets_to_delete:
            widget.setParent(None)
            widget.deleteLater()
        
        # 强制处理待删除的事件，确保widget立即删除
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # 清空列表
        self.note_list.clear()
    
    def _calculate_folder_indices(self):
        """计算文件夹列表中各个区域的行索引。
        
        Returns:
            tuple: (deleted_row, tag_header_row, first_tag_row)
                - deleted_row: "最近删除"的行索引
                - tag_header_row: "标签"标题的行索引
                - first_tag_row: 第一个标签的行索引
        """
        folder_count = len(self.custom_folders)
        deleted_row = 2 + folder_count
        tag_header_row = deleted_row + 1
        first_tag_row = tag_header_row + 1
        return deleted_row, tag_header_row, first_tag_row
    
    def _load_notes_by_current_selection(self, current_row, deleted_row, first_tag_row):
        """根据当前选中的文件夹/标签加载笔记。
        
        Args:
            current_row: 当前选中的行索引
            deleted_row: "最近删除"的行索引
            first_tag_row: 第一个标签的行索引
            
        Returns:
            list: 笔记列表
        """
        if current_row == 1:  # 所有笔记
            notes = self.note_manager.get_all_notes()
            self.current_folder_id = None
            self.current_tag_id = None
            self.is_viewing_deleted = False
        elif current_row == deleted_row:  # 最近删除
            notes = self.note_manager.get_deleted_notes()
            self.current_folder_id = None
            self.current_tag_id = None
            self.is_viewing_deleted = True
        elif 2 <= current_row < deleted_row:  # 自定义文件夹
            notes = self._load_notes_from_folder(current_row)
        elif current_row >= first_tag_row:  # 标签
            notes = self._load_notes_from_tag(current_row, first_tag_row)
        else:
            notes = []
        
        return notes
    
    def _load_notes_from_folder(self, current_row):
        """从自定义文件夹加载笔记。
        
        Args:
            current_row: 当前选中的行索引
            
        Returns:
            list: 笔记列表
        """
        folder_index = current_row - 2
        if 0 <= folder_index < len(self.custom_folders):
            folder_id = self.custom_folders[folder_index]['id']
            notes = self.note_manager.get_notes_by_folder(folder_id)
            self.current_folder_id = folder_id
            self.current_tag_id = None
            self.is_viewing_deleted = False
        else:
            notes = []
        return notes
    
    def _load_notes_from_tag(self, current_row, first_tag_row):
        """从标签加载笔记。
        
        Args:
            current_row: 当前选中的行索引
            first_tag_row: 第一个标签的行索引
            
        Returns:
            list: 笔记列表
        """
        tag_index = current_row - first_tag_row
        if 0 <= tag_index < len(self.tags):
            tag = self.tags[tag_index]
            tag_id = tag['id']

            # 空标签名：允许选中/重命名，但不让右侧编辑器进入可编辑态（不显示光标）
            tag_name = str(tag.get('name', '') or '').strip()
            if not tag_name:
                notes = []
                # 不清空current_folder_id，保持之前选中的文件夹ID，以便在标签视图下新建笔记
                self.current_tag_id = tag_id
                self.is_viewing_deleted = False

                self._set_current_note_id(None)
                self.editor.clear()
                try:
                    self.editor.text_edit.clearFocus()
                except Exception:
                    pass
            else:
                notes = self.note_manager.get_notes_by_tag(tag_id)
                # 不清空current_folder_id，保持之前选中的文件夹ID，以便在标签视图下新建笔记
                self.current_tag_id = tag_id
                self.is_viewing_deleted = False
        else:
            notes = []
        return notes
    
    def _categorize_notes(self, notes):
        """将笔记分为置顶和普通笔记。
        
        Args:
            notes: 笔记列表
            
        Returns:
            tuple: (pinned_notes, normal_notes)
        """
        pinned_notes = []
        normal_notes = []
        
        for note in notes:
            if self.note_manager.is_note_pinned(note['id']):
                pinned_notes.append(note)
            else:
                normal_notes.append(note)
        
        return pinned_notes, normal_notes
    
    def _group_notes_by_time(self, normal_notes):
        """按时间分组普通笔记。
        
        Args:
            normal_notes: 普通笔记列表
            
        Returns:
            dict: 时间分组字典，key为分组名称，value为笔记列表
        """
        time_groups = {}
        for note in normal_notes:
            group_name = self._get_time_group(note['created_at'])
            if group_name not in time_groups:
                time_groups[group_name] = []
            time_groups[group_name].append(note)
        
        return time_groups
    
    def _get_group_order(self, time_groups):
        """获取时间分组的显示顺序。
        
        Args:
            time_groups: 时间分组字典
            
        Returns:
            list: 分组名称的有序列表
        """
        group_order = ["今天", "昨天", "过去一周", "过去30天"]
        
        # 添加年份分组（按年份降序）
        year_groups = sorted([g for g in time_groups.keys() if g.endswith("年")], reverse=True)
        group_order.extend(year_groups)
        
        # 添加"其他"分组
        if "其他" in time_groups:
            group_order.append("其他")
        
        return group_order
    
    def _display_pinned_notes(self, pinned_notes):
        """显示置顶笔记。
        
        Args:
            pinned_notes: 置顶笔记列表
        """
        if not pinned_notes:
            return
        
        self._add_group_header("置顶")
        for idx, note in enumerate(pinned_notes):
            self._add_note_item(note)

            # 分组的第一条笔记：关闭其"顶部线"，避免与分组标题下面的分隔线重复
            if idx == 0:
                try:
                    it = self.note_list.item(self.note_list.count() - 1)
                    if it and (it.flags() & Qt.ItemFlag.ItemIsSelectable):
                        it.setData(Qt.ItemDataRole.UserRole + 1, False)
                except Exception:
                    pass
    
    def _display_grouped_notes(self, time_groups, group_order):
        """显示按时间分组的普通笔记。
        
        Args:
            time_groups: 时间分组字典
            group_order: 分组名称的有序列表
        """
        for group_name in group_order:
            if group_name in time_groups and time_groups[group_name]:
                group_notes = time_groups[group_name]
                self._add_group_header(group_name)
                for idx, note in enumerate(group_notes):
                    self._add_note_item(note)

                    # 分组的第一条笔记：关闭其"顶部线"，避免与分组标题下面的分隔线重复
                    if idx == 0:
                        try:
                            it = self.note_list.item(self.note_list.count() - 1)
                            if it and (it.flags() & Qt.ItemFlag.ItemIsSelectable):
                                it.setData(Qt.ItemDataRole.UserRole + 1, False)
                        except Exception:
                            pass
    
    def _select_or_default_note_in_list(self, select_note_id):
        """在笔记列表中选中指定的笔记或第一个笔记。
        
        Args:
            select_note_id: 要选中的笔记ID，如果为None则选中第一个笔记
        """
        logger.info(f"[_select_or_default_note_in_list] 开始选中笔记: select_note_id={select_note_id}")
        
        # 现在分隔线画在 item 的顶部边缘，因此"最后一条笔记"也应该保留顶部线（无需关闭）。
        # 触发重绘（应用分隔线状态变化）
        self.note_list.viewport().update()
        
        # 如果指定了要选中的笔记ID，尝试选中它
        note_selected = False
        if select_note_id:
            for i in range(self.note_list.count()):
                item = self.note_list.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    if item.data(Qt.ItemDataRole.UserRole) == select_note_id:
                        logger.info(f"[_select_or_default_note_in_list] 找到并选中指定笔记: note_id={select_note_id}, row={i}")
                        # 这儿会触发on_note_selected事件，从而调用_load_and_display_note加载笔记
                        self.note_list.setCurrentRow(i)
                        self.note_list.last_selected_row = i  # 设置last_selected_row以支持Shift多选
                        self.selected_note_rows.add(i)  # 添加到多选集合，支持Command键多选
                        note_selected = True
                        break
        
        # 如果没有指定笔记ID或指定的笔记不存在，选中第一个可选中的笔记项
        if not note_selected:
            logger.info(f"[_select_or_default_note_in_list] 未找到指定笔记或未指定，选中第一个笔记")
            for i in range(self.note_list.count()):
                item = self.note_list.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    first_note_id = item.data(Qt.ItemDataRole.UserRole)
                    logger.info(f"[_select_or_default_note_in_list] 选中第一个笔记: note_id={first_note_id}, row={i}")
                    # 这儿会触发on_note_selected事件，从而调用_load_and_display_note加载笔记
                    self.note_list.setCurrentRow(i)
                    self.note_list.last_selected_row = i  # 设置last_selected_row以支持Shift多选
                    self.selected_note_rows.add(i)  # 添加到多选集合，支持Command键多选
                    break
    
    def _clear_editor_for_empty_list(self):
        """当笔记列表为空时，清空编辑器并设置为不可编辑状态。"""
        self._set_current_note_id(None)
        self.editor.clear()
        try:
            self.editor.text_edit.clearFocus()
        except Exception:
            pass
    
    def load_notes(self, select_note_id=None):
        """加载笔记列表。
        
        主函数协调整个加载流程：
        1. 清除widget和多选状态
        2. 根据选中的文件夹/标签加载笔记
        3. 分类和分组笔记
        4. 显示笔记
        5. 选中指定笔记
        6. 更新菜单状态
        
        Args:
            select_note_id: 要选中的笔记ID，如果为None则选中第一个笔记
        """
        # 1. 清除widget和多选状态
        self._clear_note_list_widgets()
        
        # 2. 根据当前选中的文件夹/标签加载笔记
        current_row = self.folder_list.currentRow()
        deleted_row, tag_header_row, first_tag_row = self._calculate_folder_indices()
        notes = self._load_notes_by_current_selection(current_row, deleted_row, first_tag_row)
        
        # 3. 将笔记分为置顶和普通笔记
        pinned_notes, normal_notes = self._categorize_notes(notes)
        
        # 4. 按时间分组普通笔记
        time_groups = self._group_notes_by_time(normal_notes)
        group_order = self._get_group_order(time_groups)
        
        # 5. 显示置顶笔记和分组的普通笔记
        self._display_pinned_notes(pinned_notes)
        self._display_grouped_notes(time_groups, group_order)
        
        # 6. 选中指定的笔记或第一个笔记
        if notes:
            self._select_or_default_note_in_list(select_note_id)
        else:
            self._clear_editor_for_empty_list()
        
        # 7. 更新新建笔记菜单的可用状态
        self._update_new_note_action_enabled()

    
    def _show_folder_scrollbar_temporarily(self):
        """用户滚动文件夹列表时临时显示滚动条，停止滚动一段时间后隐藏"""
        self.folder_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._folder_scrollbar_hide_timer.start(2000)

    def _on_folder_scrollbar_pressed(self):
        """用户按下文件夹列表滚动条开始拖动时：保持显示，不触发隐藏"""
        self._folder_scrollbar_dragging = True
        self.folder_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._folder_scrollbar_hide_timer.stop()

    def _on_folder_scrollbar_released(self):
        """用户结束拖动文件夹列表滚动条：延迟隐藏"""
        self._folder_scrollbar_dragging = False
        self._folder_scrollbar_hide_timer.start(2000)

    def _hide_folder_scrollbar(self):
        """隐藏文件夹列表滚动条（停止滚动后触发）"""
        if getattr(self, "_folder_scrollbar_dragging", False):
            return
        self.folder_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _show_note_scrollbar_temporarily(self):

        """用户滚动笔记列表时临时显示滚动条，停止滚动一段时间后隐藏"""
        self.note_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # 只要在滚动，就不断延后隐藏时间
        self._note_scrollbar_hide_timer.start(2000)

    def _on_note_scrollbar_pressed(self):
        """用户按下滚动条开始拖动时：保持显示，不触发隐藏"""
        self._note_scrollbar_dragging = True
        self.note_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._note_scrollbar_hide_timer.stop()

    def _on_note_scrollbar_released(self):
        """用户结束拖动滚动条：延迟隐藏"""
        self._note_scrollbar_dragging = False
        self._note_scrollbar_hide_timer.start(2000)

    def _hide_note_scrollbar(self):
        """隐藏笔记列表滚动条（停止滚动后触发）"""
        if getattr(self, "_note_scrollbar_dragging", False):
            return
        self.note_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _add_note_item(self, note):
        """添加笔记项到列表"""
        # 获取笔记的纯文本内容
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(note['content'], 'html.parser')
        plain_text = soup.get_text(separator='\n')

        # 提取正文第一行作为预览（排除标题）
        # 注意：HTML转纯文本时可能不会产生换行，这里用separator强制换行；并做多种分隔兜底。
        title_text = (note.get('title') or '').strip()

        candidates = []
        lines = [l.strip() for l in plain_text.split('\n') if l.strip()]
        if len(lines) >= 2:
            candidates = lines[1:]
        else:
            # 兜底：有些内容可能只有空白分隔
            candidates = [l.strip() for l in plain_text.splitlines() if l.strip()]

        preview_text = ''
        for c in candidates:
            if not c:
                continue
            # 避免预览再次显示标题（旧逻辑问题）
            if title_text and c == title_text:
                continue
            preview_text = c
            break

        # 限制预览长度
        if len(preview_text) > 35:
            preview_text = preview_text[:35] + '...'

        
        # 格式化修改时间
        from datetime import datetime
        try:
            updated_at = datetime.fromisoformat(note['updated_at'])
            time_str = updated_at.strftime('%Y/%m/%d')
        except:
            time_str = ''
        
        # 创建列表项
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, note['id'])
        
        # 使用自定义widget显示两行内容
        widget = QWidget()
        widget.setObjectName("note_item_widget")
        widget.setProperty("selected", False)
        widget.setStyleSheet("""
            QWidget#note_item_widget {
                background: transparent;
                border-radius: 8px;
                margin-left: 8px;
                margin-right: 8px;
            }
            QWidget#note_item_widget[selected="true"] {
                background-color: #FFE066;
            }
        """)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        widget_layout = QVBoxLayout(widget)
        widget_layout.setContentsMargins(32, 6, 8, 6)

        widget_layout.setSpacing(2)  # 减小间距，从4改为2

        # 分隔线：用 item 的“下边框”来画，避免分隔线落在黄色选中背景内部。
        # 同时让分隔线左侧与内容起点对齐，右侧也留出与黄色背景一致的空白。
        item.setData(Qt.ItemDataRole.UserRole + 1, True)  # 标记：默认显示分隔线（最后一条会关闭）
        item.setData(Qt.ItemDataRole.UserRole + 2, 32)    # 标记：分隔线缩进（保持与标题起点一致）
        item.setData(Qt.ItemDataRole.UserRole + 3, 8)     # 标记：右侧边距（与左侧留白对称）

        
        # 第一行：标题
        title_label = ElidedLabel(note['title'])
        title_label.setFullText(note['title'])
        title_label.setStyleSheet("""
            font-size: 15px; 
            font-weight: normal; 
            color: #000000;
            border: none;
            background: transparent;
            padding: 0px;
            margin: 0px;
        """)
        title_label.setWordWrap(False)
        title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setMinimumWidth(0)
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        title_label.setToolTip(note['title'])
        widget_layout.addWidget(title_label)
        
        # 第二行：时间 + 预览
        info_text = f"{time_str}    {preview_text}"
        info_label = ElidedLabel(info_text)
        info_label.setFullText(info_text)
        info_label.setStyleSheet("""
            font-size: 12px; 
            color: #888888;
            border: none;
            background: transparent;
            padding: 0px;
            margin: 0px;
        """)
        info_label.setWordWrap(False)
        info_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        info_label.setTextFormat(Qt.TextFormat.PlainText)
        info_label.setMinimumWidth(0)
        info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        info_label.setToolTip(info_text)
        widget_layout.addWidget(info_label)
        
        # 第三行：文件夹信息和标签信息
        # 获取笔记的标签
        note_tags = self.note_manager.get_note_tags(note['id'])
        tags_text = ""
        if note_tags:
            tag_names = [tag['name'] for tag in note_tags]
            tags_text = f"  🏷️ {', '.join(tag_names)}"
        
        if self.current_folder_id is None and not self.is_viewing_deleted:
            # 在"所有笔记"视图中显示：文件夹 + 标签
            folder_id = note.get('folder_id')
            folder_name = "所有笔记"  # 默认值
            
            if folder_id:
                # 获取文件夹名称
                folder_info = self.note_manager.get_folder(folder_id)
                if folder_info:
                    folder_name = folder_info.get('name', '未知文件夹')
            
            # 显示文件夹图标和名称 + 标签
            folder_text = f"📁 {folder_name}{tags_text}"
            folder_label = ElidedLabel(folder_text)
            folder_label.setFullText(folder_text)
            folder_label.setStyleSheet("""
                font-size: 11px; 
                color: #999999;
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            """)
            folder_label.setWordWrap(False)
            folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            folder_label.setTextFormat(Qt.TextFormat.PlainText)
            folder_label.setMinimumWidth(0)
            folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            folder_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            folder_label.setToolTip(folder_text)
            widget_layout.addWidget(folder_label)
        elif tags_text:
            # 在其他文件夹视图中，如果有标签则单独显示一行
            tags_label = ElidedLabel(tags_text.strip())
            tags_label.setFullText(tags_text.strip())
            tags_label.setStyleSheet("""
                font-size: 11px; 
                color: #999999;
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            """)
            tags_label.setWordWrap(False)
            tags_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            tags_label.setTextFormat(Qt.TextFormat.PlainText)
            tags_label.setMinimumWidth(0)
            tags_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            tags_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            tags_label.setToolTip(tags_text.strip())
            widget_layout.addWidget(tags_label)
        
        # 分隔线已改为 item 下边框绘制（最后一条会关闭）。

        
        # 设置widget固定高度
        # 如果显示文件夹信息或标签信息，高度增加约16px（文字12px + 间距4px）
        if self.current_folder_id is None and not self.is_viewing_deleted:
            widget.setFixedHeight(77)  # 原61 + 16（文件夹+标签行）
        elif note_tags:
            widget.setFixedHeight(77)  # 原61 + 16（标签行）
        else:
            widget.setFixedHeight(61)
        
        self.note_list.addItem(item)
        self.note_list.setItemWidget(item, widget)

        
        # 设置 item 的 sizeHint，注意这里的宽度同时受group设置的宽度影响
        if self.current_folder_id is None and not self.is_viewing_deleted:
            item.setSizeHint(QSize(200, 77))
        elif note_tags:
            item.setSizeHint(QSize(200, 77))
        else:
            item.setSizeHint(QSize(200, 61))

            
    def load_folders(self, restore_last_state: bool = False):
        """加载文件夹列表（新布局：iCloud分组，支持多级文件夹）
        
        Args:
            restore_last_state: 是否从数据库恢夏状态（仅初始化时使用）
        """
        # 保存当前选中的行
        current_row = self.folder_list.currentRow()
        
        # 清空列表
        self.folder_list.clear()
        
        # 预加载笔记计数数据
        self._preload_note_counts()
        
        # 添加iCloud分组
        self._add_icloud_section()
        
        # 添加标签分组
        self._add_tags_section()
        
        # 恢复选中状态
        self._restore_selection(current_row, restore_last_state)
        
        # 强制刷新UI
        self.folder_list.viewport().update()
        self.folder_list.update()

    def _preload_note_counts(self):
        """预加载笔记计数数据，避免逐个查询造成卡顿"""
        self._folder_note_counts = {}
        self._system_note_counts = {"all_notes": 0, "deleted": 0}
        
        try:
            cur = self.note_manager.conn.cursor()

            # 所有笔记（未删除）
            cur.execute('''
                SELECT COUNT(*) as cnt
                FROM ZNOTE
                WHERE ZISDELETED = 0
            ''')
            row = cur.fetchone()
            try:
                self._system_note_counts["all_notes"] = int(row['cnt'])
            except Exception:
                self._system_note_counts["all_notes"] = int(row[0]) if row else 0

            # 最近删除
            cur.execute('''
                SELECT COUNT(*) as cnt
                FROM ZNOTE
                WHERE ZISDELETED = 1
            ''')
            row = cur.fetchone()
            try:
                self._system_note_counts["deleted"] = int(row['cnt'])
            except Exception:
                self._system_note_counts["deleted"] = int(row[0]) if row else 0

            # 自定义文件夹：folder_id -> 笔记数量（未删除，且属于某文件夹）
            cur.execute('''
                SELECT ZFOLDERID as folder_id, COUNT(*) as cnt
                FROM ZNOTE
                WHERE ZISDELETED = 0 AND ZFOLDERID IS NOT NULL
                GROUP BY ZFOLDERID
            ''')
            for row in cur.fetchall():
                try:
                    fid = row['folder_id']
                    cnt = row['cnt']
                except Exception:
                    fid = row[0]
                    cnt = row[1]
                if fid:
                    self._folder_note_counts[str(fid)] = int(cnt)

        except Exception:
            self._folder_note_counts = {}
            self._system_note_counts = {"all_notes": 0, "deleted": 0}

    def _add_icloud_section(self):
        """添加iCloud分组（包括标题、系统文件夹和自定义文件夹）"""
        # 添加iCloud标题
        self._add_section_header("☁️ iCloud")
        
        # 添加系统文件夹
        self._add_system_folder_item("all_notes", "📝 所有笔记")
        
        # 加载自定义文件夹（支持层级显示）
        all_folders = self.note_manager.get_all_folders()
        self.custom_folders = []
        self._add_folders_recursive(all_folders, None, 1, self.custom_folders)
        
        # 添加最近删除
        self._add_system_folder_item("deleted", "🗑️ 最近删除")

    def _add_tags_section(self):
        """添加标签分组（包括标题和所有标签）"""
        # 添加标签标题
        tag_header = self._add_section_header("🏷️ 标签")
        tag_header.setData(Qt.ItemDataRole.UserRole, ("tag_header", None))
        
        # 加载标签
        self.tags = self.note_manager.get_all_tags()
        for tag in self.tags:
            self._add_tag_item(tag)

    def _add_section_header(self, title: str) -> QListWidgetItem:
        """添加分组标题（不可选中）
        
        Args:
            title: 标题文本
            
        Returns:
            创建的QListWidgetItem
        """
        header_item = QListWidgetItem()
        header_item.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 10, 0)
        header_layout.setSpacing(6)

        header_label = ElidedLabel(title)
        header_label.setFullText(title)
        header_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #000000;
            background: transparent;
        """)
        header_layout.addWidget(header_label, 1)

        header_widget.setFixedHeight(28)
        header_item.setSizeHint(QSize(200, 28))

        self.folder_list.addItem(header_item)
        self.folder_list.setItemWidget(header_item, header_widget)
        
        return header_item

    def _add_tag_item(self, tag: dict):
        """添加单个标签项
        
        Args:
            tag: 标签数据字典，包含id和name
        """
        raw_name = str(tag.get('name', '') or '')
        tag_name = raw_name.strip()
        count = self.note_manager.get_tag_count(tag['id'])

        is_empty_tag = (tag_name == "")
        display_name = tag_name if not is_empty_tag else "（未命名标签）"
        item_text = f"    🏷️ {display_name} ({count})"

        tag_item = QListWidgetItem()
        tag_item.setData(Qt.ItemDataRole.UserRole, ("tag", tag['id']))

        # 创建自定义widget以支持高亮显示
        tag_widget = QWidget()
        tag_widget.setObjectName("folder_row_widget")
        tag_layout = QHBoxLayout(tag_widget)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(0)

        tag_label = QLabel(item_text)
        if is_empty_tag:
            tag_label.setStyleSheet("background: transparent; padding: 8px 10px; font-size: 13px; color: #8e8e93;")
        else:
            tag_label.setStyleSheet("background: transparent; padding: 8px 10px; font-size: 13px;")
        tag_layout.addWidget(tag_label)

        # 设置选中状态
        is_selected = (self.current_tag_id == tag['id'])
        tag_widget.setProperty("selected", is_selected)
        tag_item.setSelected(is_selected)

        self.folder_list.addItem(tag_item)
        self.folder_list.setItemWidget(tag_item, tag_widget)
        tag_item.setSizeHint(QSize(200, 40))

    def _restore_selection(self, current_row: int, restore_last_state: bool = False):
        """恢复选中状态
        
        Args:
            current_row: 之前选中的行号（非初始化场景使用）
            restore_last_state: 是否从数据库恢复完整状态（初始化场景使用）
        """
        if restore_last_state:
            # 初始化场景：从数据库恢复完整状态
            self._restore_last_state()
        else:
            # 非初始化场景：保持当前选中行
            if current_row >= 0 and current_row < self.folder_list.count():
                item = self.folder_list.item(current_row)
                if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    self.folder_list.setCurrentRow(current_row)
                else:
                    self.folder_list.setCurrentRow(1)  # 默认选中"所有笔记"
            else:
                self.folder_list.setCurrentRow(1)  # 默认选中"所有笔记"
    
    def _restore_last_note_per_view(self):
        """从数据库恢复所有视图的笔记映射"""
        try:
            import json
            last_note_per_view_str = self.note_manager.get_app_state("last_note_per_view")
            logger.info(f"[_restore_last_note_per_view] 开始恢复视图笔记映射: {last_note_per_view_str}")
            if last_note_per_view_str:
                try:
                    last_note_per_view = json.loads(last_note_per_view_str)
                    if isinstance(last_note_per_view, dict):
                        self._last_note_per_view = last_note_per_view
                        logger.info(f"[_restore_last_note_per_view] 视图笔记映射恢复成功: {last_note_per_view}")
                except Exception as e:
                    logger.error(f"[_restore_last_note_per_view] 解析 last_note_per_view 失败: {e}")
                    print(f"解析 last_note_per_view 失败: {e}")
        except Exception as e:
            logger.error(f"[_restore_last_note_per_view] 恢复 last_note_per_view 失败: {e}")
            print(f"恢复 last_note_per_view 失败: {e}")
    
    def _restore_last_state(self):
        """从数据库恢复完整状态（文件夹/标签、笔记、光标位置）"""
        logger.info("[_restore_last_state] 开始恢复应用状态")
        try:
            # 0. 首先恢复所有视图的笔记映射
            self._restore_last_note_per_view()
            
            # 1. 恢复文件夹/标签选中状态
            last_folder_type = self.note_manager.get_app_state("last_folder_type")
            last_folder_value = self.note_manager.get_app_state("last_folder_value")
            logger.info(f"[_restore_last_state] 恢复文件夹状态: type={last_folder_type}, value={last_folder_value}")
            
            # 尝试恢复上次选中的文件夹/标签
            folder_restored = self._find_and_select_folder(last_folder_type, last_folder_value)
            
            # 2. 如果没有恢复成功，使用默认值（"所有笔记"）
            if not folder_restored:
                logger.info("[_restore_last_state] 文件夹恢复失败，使用默认文件夹")
                self._select_default_folder()
            else:
                logger.info("[_restore_last_state] 文件夹恢复成功")
            
        except Exception as e:
            logger.error(f"[_restore_last_state] 恢复状态失败: {e}")
            import traceback
            traceback.print_exc()
            # 失败时使用默认值
            self._select_default_folder()
    
    def _find_and_select_folder(self, folder_type, folder_value):
        """查找并选中指定的文件夹/标签
        
        Args:
            folder_type: 文件夹类型（如 "system", "custom", "tag"）
            folder_value: 文件夹值（如 "all_notes", 文件夹ID, 标签ID）
            
        Returns:
            bool: 是否成功找到并选中
        """
        if not folder_type or not folder_value:
            return False
        
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if not item:
                continue
                
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, tuple) and len(payload) == 2:
                if payload[0] == folder_type and payload[1] == folder_value:
                    # 这儿会触发on_folder_changed事件
                    self.folder_list.setCurrentRow(i)
                    return True
        
        return False
    
    def _select_default_folder(self):
        """选中默认文件夹（"所有笔记"）"""
        # 尝试选中"所有笔记"
        if self._find_and_select_folder("system", "all_notes"):
            return
        
        # 如果找不到"所有笔记"，选中第一个可用项
        if self.folder_list.count() > 0:
            self.folder_list.setCurrentRow(0)
    
    def _find_note_by_id(self, note_id):
        """根据笔记ID查找笔记在列表中的索引
        
        Args:
            note_id: 笔记ID
            
        Returns:
            int or None: 笔记索引，如果未找到返回 None
        """
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if not item or not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                continue
            
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                return i
        
        return None
    


    def _add_folders_recursive(self, all_folders, parent_id, level, flat_list):
        """递归添加文件夹，支持多级层级显示（带展开/折叠箭头）
        
        Args:
            all_folders: 所有文件夹列表
            parent_id: 父文件夹ID，None表示顶级文件夹
            level: 当前层级（1为顶级，2为二级，以此类推）
            flat_list: 扁平化的文件夹列表（用于保持与原有逻辑兼容）
        """
        # 找出当前层级的文件夹
        current_level_folders = [
            f for f in all_folders
            if f.get('parent_folder_id') == parent_id
        ]

        # 按order_index排序
        current_level_folders.sort(key=lambda x: x.get('order_index', 0))

        # 为了判断是否有子文件夹，预先构建 parent -> children_count
        children_count = {}
        for f in all_folders:
            pid = f.get('parent_folder_id')
            if pid is None:
                continue
            children_count[pid] = children_count.get(pid, 0) + 1

        # 添加到列表
        for folder in current_level_folders:
            folder_id = folder['id']
            has_children = children_count.get(folder_id, 0) > 0
            expanded = self._folder_expanded.get(folder_id, True)

            # 创建item + 自定义widget
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, ("folder", folder_id))

            row_widget = QWidget()
            row_widget.setObjectName("folder_row_widget")
            row_widget.setProperty("selected", False)
            row_layout = QHBoxLayout(row_widget)
            # 左移：让折叠箭头列的最左侧与“🏷️ 标签”等普通文本项的图标最左侧对齐
            row_layout.setContentsMargins(0, 0, 10, 0)

            row_layout.setSpacing(6)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            # 缩进：顶级(folder level=1)不额外缩进；子级每级增加16px
            indent_px = max(0, (level - 1) * 16)
            indent_widget = QWidget()
            indent_widget.setFixedWidth(indent_px)
            row_layout.addWidget(indent_widget)

            # 展开/折叠箭头（仅在有子文件夹时显示，否则占位保证对齐）
            if has_children:
                twisty = FolderTwisty(folder_id, expanded)
                twisty.toggled.connect(self._toggle_folder_expanded)
                row_layout.addWidget(twisty)
            else:
                spacer = QWidget()
                spacer.setFixedWidth(14)
                row_layout.addWidget(spacer)

            # 文件夹图标（单独一列，确保重命名时图标仍显示）
            icon_label = QLabel("📁")
            icon_label.setFixedWidth(16)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet("""
                font-size: 13px;
                color: #000000;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            """)
            row_layout.addWidget(icon_label)

            # 文件夹名称（仅名称部分可编辑）
            name_label = ElidedLabel(folder['name'])
            name_label.setFullText(folder['name'])
            name_label.setToolTip(folder['name'])
            name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_label.setStyleSheet("""
                font-size: 13px;
                color: #000000;
                background: transparent;
            """)
            row_layout.addWidget(name_label, 1)

            # 右侧：笔记数量（灰色、右对齐；无笔记则不显示）
            try:
                count = int(getattr(self, "_folder_note_counts", {}).get(folder_id, 0))
            except Exception:
                count = 0

            count_label = QLabel(str(max(0, count)))
            count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            count_label.setMinimumWidth(28)  # 预留 1~3 位数字对齐
            count_label.setStyleSheet("""
                font-size: 12px;
                color: #9a9a9a;
                background: transparent;
            """)
            row_layout.addWidget(count_label)

            row_widget.setFixedHeight(28)
            item.setSizeHint(QSize(200, 28))

            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, row_widget)

            # 添加到扁平列表（保持与原有逻辑兼容：用于 folder_index -> folder_id 映射）
            flat_list.append(folder)

            # 如果有子文件夹且已展开，则递归添加子文件夹
            if has_children and expanded:
                self._add_folders_recursive(all_folders, folder_id, level + 1, flat_list)

    def _toggle_folder_expanded(self, folder_id: str):
        """切换文件夹展开/折叠状态并刷新左侧列表"""
        # 记录当前选中的folder_id（尽量保持选中不跳）
        selected_folder_id = None
        current_row = self.folder_list.currentRow()
        if current_row is not None and current_row >= 0:
            cur_item = self.folder_list.item(current_row)
            if cur_item:
                payload = cur_item.data(Qt.ItemDataRole.UserRole)
                if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder":
                    selected_folder_id = payload[1]

        self._folder_expanded[folder_id] = not self._folder_expanded.get(folder_id, True)
        self.load_folders()

        # 恢复选中
        if selected_folder_id:
            for i in range(self.folder_list.count()):
                it = self.folder_list.item(i)
                if not it:
                    continue
                payload = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder" and payload[1] == selected_folder_id:
                    self.folder_list.setCurrentRow(i)
                    break

    def _add_system_folder_item(self, key: str, text: str):
        """添加系统文件夹项（与自定义文件夹统一缩进/对齐）"""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, ("system", key))

        # 系统项（所有笔记/最近删除）不允许拖动：它们不是“真实文件夹节点”，
        # 也不参与父子层级调整，避免用户误操作。
        try:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        except Exception:
            pass

        row_widget = QWidget()
        row_widget.setObjectName("folder_row_widget")
        row_widget.setProperty("selected", False)
        row_layout = QHBoxLayout(row_widget)
        # 左移：与“🏷️ 标签”等普通文本项的图标最左侧对齐
        row_layout.setContentsMargins(0, 0, 10, 0)

        row_layout.setSpacing(6)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 系统项顶级不再额外缩进（level=0）
        level = 0
        indent_px = level * 16
        indent_widget = QWidget()
        indent_widget.setFixedWidth(indent_px)
        row_layout.addWidget(indent_widget)

        # 系统项没有展开/折叠，但需要占位保持对齐
        spacer = QWidget()
        spacer.setFixedWidth(14)
        row_layout.addWidget(spacer)

        name_label = ElidedLabel(text)
        name_label.setFullText(text)
        name_label.setToolTip(text.replace("📝 ", "").replace("🗑️ ", ""))
        name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        name_label.setStyleSheet("""
            font-size: 13px;
            color: #000000;
            background: transparent;
        """)
        row_layout.addWidget(name_label, 1)

        # 右侧：系统项笔记数量（灰色、右对齐）
        try:
            count = int(getattr(self, "_system_note_counts", {}).get(key, 0))
        except Exception:
            count = 0

        count_label = QLabel(str(max(0, count)))
        count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        count_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        count_label.setMinimumWidth(28)
        count_label.setStyleSheet("""
            font-size: 12px;
            color: #9a9a9a;
            background: transparent;
        """)
        row_layout.addWidget(count_label)

        row_widget.setFixedHeight(28)
        item.setSizeHint(QSize(200, 28))

        self.folder_list.addItem(item)
        self.folder_list.setItemWidget(item, row_widget)

    def create_new_folder(self):

        """创建新文件夹（不弹窗）。

        规则：
        - 如果当前选中的是“自定义文件夹”，则在该文件夹下创建子文件夹（行为与右键菜单一致）
        - 否则（未选中自定义文件夹/选中系统项/标签等），在根目录下创建
        """
        parent_folder_id = None

        # 判断当前选中行是否为自定义文件夹
        try:
            current_row = self.folder_list.currentRow()
            folder_count = len(self.custom_folders)
            deleted_row = 2 + folder_count
            if 2 <= current_row < deleted_row:
                folder_index = current_row - 2
                if 0 <= folder_index < len(self.custom_folders):
                    parent_folder_id = self.custom_folders[folder_index]['id']
        except Exception:
            parent_folder_id = None

        if parent_folder_id:
            self.create_subfolder(parent_folder_id)
            return

        base_name = "新建文件夹"

        # 顶级文件夹：parent_folder_id 为 None
        try:
            all_folders = self.note_manager.get_all_folders()
            existing = {
                str(f.get("name", "")).strip().casefold()
                for f in all_folders
                if f.get("parent_folder_id") is None
            }
        except Exception:
            existing = set()

        # 生成不重名的默认名：新建文件夹 / 新建文件夹1 / 新建文件夹2 ...
        if base_name.casefold() not in existing:
            name = base_name
        else:
            i = 1
            while True:
                candidate = f"{base_name}{i}"
                if candidate.casefold() not in existing:
                    name = candidate
                    break
                i += 1

        folder_id = self.note_manager.create_folder(name)
        self.load_folders()

        # 选中新创建的文件夹（索引从2开始）
        created_row = None
        for i, folder in enumerate(self.custom_folders):
            if folder['id'] == folder_id:
                created_row = 2 + i
                self.folder_list.setCurrentRow(created_row)
                break

        # 进入就地重命名：让用户可直接覆盖默认名
        if created_row is not None:
            QTimer.singleShot(0, lambda: self.rename_folder(folder_id))

                    
    def rename_folder(self, folder_id: str):
        """重命名文件夹（就地编辑，不弹窗）。

        交互：将该文件夹行的名称区域替换为可编辑输入框；用户回车或失去焦点即提交；
        ESC 取消。
        """
        folder = self.note_manager.get_folder(folder_id)
        if not folder:
            return

        # 找到对应的 QListWidgetItem
        target_item = None
        for i in range(self.folder_list.count()):
            it = self.folder_list.item(i)
            if not it:
                continue
            payload = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder" and payload[1] == folder_id:
                target_item = it
                break

        if not target_item:
            return

        row_widget = self.folder_list.itemWidget(target_item)
        if not row_widget:
            return

        layout = row_widget.layout()
        if not layout:
            return

        # 防止重复进入编辑态
        if row_widget.property("renaming") is True:
            return
        row_widget.setProperty("renaming", True)

        from PyQt6.QtWidgets import QLineEdit

        # 定位名称控件（我们构建行时，最后一个 stretch=1 的 widget 是名称 ElidedLabel）
        name_widget = None
        name_index = -1
        for idx in range(layout.count() - 1, -1, -1):
            w = layout.itemAt(idx).widget()
            if isinstance(w, ElidedLabel):
                name_widget = w
                name_index = idx
                break

        if name_widget is None or name_index < 0:
            row_widget.setProperty("renaming", False)
            return

        # 编辑框只编辑纯名称（不包含 📁 ）
        old_name = folder.get("name", "")

        editor = QLineEdit()
        # 右侧留出一块可点击的空白区域（仿 macOS 备忘录/Finder）：
        # 不通过给文本追加空格来实现，而是通过输入框的右侧 padding 留白。
        editor.setText(old_name)
        editor.setTextMargins(0, 0, 24, 0)

        editor.setProperty("_rename_old_name", old_name)
        editor.setProperty("_rename_cancelled", False)
        editor.setFrame(False)
        editor.setStyleSheet("""
            QLineEdit {
                font-size: 13px;
                color: #000000;
                background-color: #ffffff;
                border: 1px solid #bdbdbd;
                border-radius: 4px;
                padding: 2px 24px 2px 6px;
                margin: 0px;
            }
        """)

        def _cleanup(cancelled: bool, new_name: str | None = None):
            # 恢复 label
            try:
                layout.removeWidget(editor)
                editor.deleteLater()
            except Exception:
                pass

            # 把 label 加回原位
            layout.insertWidget(name_index, name_widget, 1)
            name_widget.show()

            row_widget.setProperty("renaming", False)

            # 如果取消，直接恢复原显示
            if cancelled:
                name_widget.setFullText(old_name)
                name_widget.setToolTip(old_name)
                return

            # 提交更新
            if new_name is None:
                return
            new_name = (new_name or "").strip()

            if not new_name or new_name == old_name:
                name_widget.setFullText(old_name)
                name_widget.setToolTip(old_name)
                return

            # 校验：同一父文件夹下不允许重名（忽略大小写和首尾空白）
            try:
                all_folders = self.note_manager.get_all_folders()
                parent_id = folder.get("parent_folder_id")
                normalized = new_name.strip().casefold()
                conflict = any(
                    (f.get("id") != folder_id)
                    and (f.get("parent_folder_id") == parent_id)
                    and (str(f.get("name", "")).strip().casefold() == normalized)
                    for f in all_folders
                )
            except Exception:
                conflict = False

            if conflict:
                QMessageBox.warning(self, "名称已存在", "已存在同名文件夹，请换一个名称。")
                # 回到就地编辑状态，让用户继续编辑
                QTimer.singleShot(0, lambda: self.rename_folder(folder_id))
                return

            self.note_manager.update_folder(folder_id, new_name)
            # 直接全量刷新，确保名称、排序、扁平映射一致
            self.load_folders()

        # 提交：回车
        editor.returnPressed.connect(lambda: _cleanup(False, editor.text()))

        def _on_editing_finished():
            # ESC 取消
            if bool(editor.property("_rename_cancelled")):
                _cleanup(True)
                return

            # editingFinished 会在回车和失焦都触发；如果 returnPressed 已经触发，
            # 此时 row_widget.renaming 可能已被置回 False，避免重复提交。
            if row_widget.property("renaming") is True:
                _cleanup(False, editor.text())

        editor.editingFinished.connect(_on_editing_finished)

        # 取消：ESC
        editor.installEventFilter(self)

        # 临时替换控件
        name_widget.hide()
        layout.removeWidget(name_widget)
        layout.insertWidget(name_index, editor, 1)

        editor.setFocus()
        # 默认全选（Finder 风格）：用户可以直接输入覆盖；
        # 如果想在末尾追加，点击右侧留白处即可把光标放到末尾再输入。
        editor.selectAll()

            
    def delete_folder_confirm(self, folder_id: str):
        """删除文件夹（确认）"""
        folder = self.note_manager.get_folder(folder_id)
        if not folder:
            return
            
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除文件夹 '{folder['name']}' 吗？\n\n文件夹中的笔记将移动到'所有笔记'。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 删除文件夹时：将该文件夹（含子文件夹）下的笔记全部移入“最近删除”
            try:
                self.note_manager.delete_folder_to_trash(folder_id)
            except Exception:
                # 兜底：保持原有行为（至少不让UI崩溃）
                self.note_manager.delete_folder(folder_id)
            self.load_folders()
            self.load_notes()

            
    # ========== 标签管理方法 ==========
    
    def create_new_tag(self):
        """创建新标签（不弹窗）"""
        base_name = "新建标签"
        
        # 获取所有现有标签名称
        try:
            all_tags = self.note_manager.get_all_tags()
            existing = {
                str(t.get("name", "")).strip().casefold()
                for t in all_tags
            }
        except Exception:
            existing = set()
        
        # 生成不重名的默认名：新建标签 / 新建标签1 / 新建标签2 ...
        if base_name.casefold() not in existing:
            name = base_name
        else:
            i = 1
            while True:
                candidate = f"{base_name}{i}"
                if candidate.casefold() not in existing:
                    name = candidate
                    break
                i += 1
        
        tag_id = self.note_manager.create_tag(name)
        self.load_folders()
        
        # 选中新创建的标签并进入重命名状态
        created_row = None
        for i, tag in enumerate(self.tags):
            if tag['id'] == tag_id:
                # 标签在 folder_list 中的位置需要计算
                # 位置 = 系统项(2) + 自定义文件夹数量 + 已删除(1) + 标签头(1) + 标签索引
                created_row = 2 + len(self.custom_folders) + 1 + 1 + i
                self.folder_list.setCurrentRow(created_row)
                break
        
        # 进入就地重命名
        if created_row is not None:
            QTimer.singleShot(0, lambda: self.rename_tag_inline(tag_id))
            
    def rename_tag(self, tag_id: str):
        """重命名标签（兼容旧接口，调用就地编辑版本）"""
        self.rename_tag_inline(tag_id)
    
    def rename_tag_dialog(self, tag_id: str):
        """重命名标签（对话框版本，保留用于特殊场景）"""
        tag = self.note_manager.get_tag(tag_id)
        if not tag:
            return
            
        name, ok = QInputDialog.getText(
            self, "重命名标签", 
            "请输入新名称:",
            text=tag['name']
        )
        
        if ok and name.strip():
            self.note_manager.update_tag(tag_id, name.strip())
            self.load_folders()
    
    def rename_tag_inline(self, tag_id: str):
        """重命名标签（就地编辑，不弹窗）"""
        tag = self.note_manager.get_tag(tag_id)
        if not tag:
            return
        
        # 找到对应的 QListWidgetItem
        target_item = None
        for i in range(self.folder_list.count()):
            it = self.folder_list.item(i)
            if not it:
                continue
            payload = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "tag" and payload[1] == tag_id:
                target_item = it
                break
        
        if not target_item:
            return
        
        row_widget = self.folder_list.itemWidget(target_item)
        if not row_widget:
            return
        
        layout = row_widget.layout()
        if not layout:
            return
        
        # 防止重复进入编辑态
        if row_widget.property("renaming") is True:
            return
        row_widget.setProperty("renaming", True)
        
        from PyQt6.QtWidgets import QLineEdit
        
        # 找到标签名称的 QLabel
        name_widget = None
        name_index = -1
        for idx in range(layout.count()):
            w = layout.itemAt(idx).widget()
            if isinstance(w, QLabel):
                name_widget = w
                name_index = idx
                break
        
        if name_widget is None or name_index < 0:
            row_widget.setProperty("renaming", False)
            return
        
        # 提取纯名称（去掉前缀和计数）
        old_name = tag.get("name", "")
        
        editor = QLineEdit()
        editor.setText(old_name)
        editor.setTextMargins(0, 0, 24, 0)
        editor.setProperty("_rename_old_name", old_name)
        editor.setProperty("_rename_cancelled", False)
        editor.setFrame(False)
        editor.setStyleSheet("""
            QLineEdit {
                font-size: 13px;
                color: #000000;
                background-color: #ffffff;
                border: 1px solid #bdbdbd;
                border-radius: 4px;
                padding: 2px 24px 2px 6px;
                margin: 0px 10px;
            }
        """)
        
        def _cleanup(cancelled: bool, new_name: str | None = None):
            # 恢复 label
            try:
                layout.removeWidget(editor)
                editor.deleteLater()
            except Exception:
                pass
            
            # 把 label 加回原位
            layout.insertWidget(name_index, name_widget)
            name_widget.show()
            
            row_widget.setProperty("renaming", False)
            
            # 如果取消，直接恢复原显示
            if cancelled:
                return
            
            # 提交更新
            if new_name is None:
                return
            new_name = (new_name or "").strip()
            
            if not new_name or new_name == old_name:
                return
            
            # 校验：不允许重名（忽略大小写和首尾空白）
            try:
                all_tags = self.note_manager.get_all_tags()
                normalized = new_name.strip().casefold()
                conflict = any(
                    (t.get("id") != tag_id)
                    and (str(t.get("name", "")).strip().casefold() == normalized)
                    for t in all_tags
                )
            except Exception:
                conflict = False
            
            if conflict:
                QMessageBox.warning(self, "名称已存在", "已存在同名标签，请换一个名称。")
                # 回到就地编辑状态，让用户继续编辑
                QTimer.singleShot(0, lambda: self.rename_tag_inline(tag_id))
                return
            
            self.note_manager.update_tag(tag_id, new_name)
            # 全量刷新
            self.load_folders()
        
        # 提交：回车
        editor.returnPressed.connect(lambda: _cleanup(False, editor.text()))
        
        def _on_editing_finished():
            # ESC 取消
            if bool(editor.property("_rename_cancelled")):
                _cleanup(True)
                return
            
            if row_widget.property("renaming") is True:
                _cleanup(False, editor.text())
        
        editor.editingFinished.connect(_on_editing_finished)
        
        # 取消：ESC
        editor.installEventFilter(self)
        
        def _event_filter(obj, event):
            if obj == editor and event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    editor.setProperty("_rename_cancelled", True)
                    editor.clearFocus()
                    return True
            return False
        
        self.eventFilter = _event_filter
        
        # 隐藏原 label，插入编辑框
        name_widget.hide()
        layout.insertWidget(name_index, editor)
        
        editor.setFocus()
        editor.selectAll()
            
    def delete_tag_confirm(self, tag_id: str):
        """删除标签（确认）"""
        tag = self.note_manager.get_tag(tag_id)
        if not tag:
            return
            
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除标签 '{tag['name']}' 吗？\n\n标签将从所有笔记中移除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.note_manager.delete_tag(tag_id)
            self.load_folders()
            self.load_notes()
            
    def _find_and_select_empty_note(self, folder_id):
        """查找并选中空草稿笔记
        
        Args:
            folder_id: 文件夹ID
            
        Returns:
            bool: 是否找到并选中了空草稿笔记
        """
        try:
            notes = self.note_manager.get_notes_by_folder(folder_id)
            for note in notes:
                if self._is_empty_new_note(note):
                    empty_note_id = note.get('id')
                    # 在笔记列表中选中这个笔记
                    for i in range(self.note_list.count()):
                        item = self.note_list.item(i)
                        if item.data(Qt.ItemDataRole.UserRole) == empty_note_id:
                            self.note_list.setCurrentItem(item)
                            break
                    # 设置焦点到编辑器
                    self.editor.text_edit.setFocus()
                    return True
        except Exception as e:
            pass
        return False

    def _select_note_in_list(self, note_id):
        """在笔记列表中选中指定笔记
        
        Args:
            note_id: 笔记ID
        """
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentItem(item)
                break

    def _refresh_folders_and_restore_selection(self):
        """刷新文件夹列表并恢复选中状态"""
        selected_row = self.folder_list.currentRow()
        self.load_folders()
        try:
            if selected_row is not None and 0 <= selected_row < self.folder_list.count():
                self.folder_list.setCurrentRow(selected_row)
        except Exception as e:
            pass

    def _create_and_save_new_note(self, folder_id):
        """创建并保存新笔记
        
        Args:
            folder_id: 文件夹ID
            
        Returns:
            int: 新创建的笔记ID
        """
        note_id = self.note_manager.create_note(title="新笔记", folder_id=folder_id)
        
        try:
            # 确保标题落库（兼容未来 create_note 默认值变化）
            self.note_manager.update_note(note_id, title="新笔记")
        except Exception as e:
            pass
        
        return note_id

    def create_new_note(self):
        """创建新笔记（菜单/工具栏）。

        规则：
        - 默认在当前选中的"自定义文件夹"下创建
        - 标题默认为"新笔记"
        - 同一文件夹下只允许存在一个"空的新笔记草稿"；若已存在，则该菜单应不可用（这里也做一次保护）
        """
        # 必须在自定义文件夹下创建；未选中文件夹时直接忽略
        folder_id = self.current_folder_id
        
        if not folder_id:
            logging.warning("create_new_note: folder_id为空，不应该进入到create_new_note的函数逻辑中")
            return

        # 防御：如果已存在空草稿，直接打开那个草稿
        if self._current_folder_has_empty_new_note():
            if self._find_and_select_empty_note(folder_id):
                return
            # 发现有空笔记但选中失败
            logging.warning(f"create_new_note: 文件夹 {folder_id} 下存在空笔记，但选中笔记失败")
            return

        # 创建新笔记
        note_id = self._create_and_save_new_note(folder_id)

        # 刷新笔记列表
        self.load_notes()

        # 同步刷新左侧文件夹计数（load_notes 不会重建 folder_list）
        self._refresh_folders_and_restore_selection()

        # 选中新创建的笔记
        self._select_note_in_list(note_id)

        # 设置焦点到编辑器，让光标闪烁
        self.editor.text_edit.setFocus()

    def create_new_note_from_tag(self):
        """从标签右键菜单创建新笔记。
        
        规则：
        - 如果当前有选中的有效文件夹，使用该文件夹
        - 如果没有选中文件夹或选中的是系统文件夹，使用第一个自定义文件夹
        - 如果没有任何自定义文件夹，提示用户先创建文件夹
        """
        folder_id = self.current_folder_id
        
        # 如果当前文件夹无效（None或系统文件夹），尝试使用第一个自定义文件夹
        if not folder_id or folder_id in (None, -1):
            if self.custom_folders:
                folder_id = self.custom_folders[0]['id']
                # 更新current_folder_id以便后续操作
                self.current_folder_id = folder_id
            else:
                # 没有任何自定义文件夹，提示用户
                QMessageBox.information(self, "提示", "请先创建或选择一个文件夹")
                return
        
        # 在文件夹列表中选中对应的文件夹
        self._select_folder_in_list(self.current_folder_id)
        
        # 调用标准的创建笔记方法
        self.create_new_note()

    def _select_folder_in_list(self, folder_id):
        """在文件夹列表中选中指定的文件夹
        
        Args:
            folder_id: 要选中的文件夹ID
        """
        if not folder_id:
            return
        
        # 遍历文件夹列表，找到对应的项
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if not item:
                continue
                
            payload = item.data(Qt.ItemDataRole.UserRole)
            if not payload:
                continue
                
            # 检查是否是文件夹项，且ID匹配
            if isinstance(payload, tuple) and len(payload) == 2:
                item_type, item_id = payload
                if item_type == "folder" and item_id == folder_id:
                    # 选中该项
                    self.folder_list.setCurrentRow(i)
                    # 确保该项可见（滚动到视图中）
                    self.folder_list.scrollToItem(item)
                    return

                
    def show_folder_context_menu(self, position):
        """显示文件夹列表的右键菜单"""
        item = self.folder_list.itemAt(position)
        menu = QMenu(self)
        
        if not item:
            # 点击在空白区域，显示统一的三项菜单
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(self.create_new_note)
            # 如果当前选中的是系统文件夹（所有笔记或最近删除），禁用新建笔记
            if self.current_folder_id is None or self.current_folder_id == -1:
                new_note_action.setEnabled(False)
            menu.addAction(new_note_action)
            
            new_folder_action = QAction("新建文件夹", self)
            new_folder_action.triggered.connect(self.create_new_folder)
            menu.addAction(new_folder_action)
            
            new_tag_action = QAction("新建标签", self)
            new_tag_action.triggered.connect(self.create_new_tag)
            menu.addAction(new_tag_action)
            
            menu.exec(self.folder_list.mapToGlobal(position))
            return
        
        # 获取item的数据标识
        payload = item.data(Qt.ItemDataRole.UserRole)
        
        # 判断是否是系统文件夹（所有笔记、最近删除）
        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "system":
            # 系统文件夹显示禁用的"新建笔记"和"新建文件夹"
            new_note_action = QAction("新建笔记", self)
            new_note_action.setEnabled(False)  # 禁用新建笔记
            menu.addAction(new_note_action)
            
            new_folder_action = QAction("新建文件夹", self)
            new_folder_action.triggered.connect(self.create_new_folder)
            menu.addAction(new_folder_action)
            
            new_tag_action = QAction("新建标签", self)
            new_tag_action.triggered.connect(self.create_new_tag)
            menu.addAction(new_tag_action)
            
            menu.exec(self.folder_list.mapToGlobal(position))
            return
        
        # 判断是否是标签标题或标签项
        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] in ("tag_header", "tag"):
            # 点击在标签标题或标签上，显示统一的三项菜单
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(self.create_new_note_from_tag)
            # 如果当前选中的是系统文件夹（所有笔记或最近删除），禁用新建笔记
            if self.current_folder_id is None or self.current_folder_id == -1:
                new_note_action.setEnabled(False)
            menu.addAction(new_note_action)
            
            new_folder_action = QAction("新建文件夹", self)
            new_folder_action.triggered.connect(self.create_new_folder)
            menu.addAction(new_folder_action)
            
            new_tag_action = QAction("新建标签", self)
            new_tag_action.triggered.connect(self.create_new_tag)
            menu.addAction(new_tag_action)
            
            menu.exec(self.folder_list.mapToGlobal(position))
            return
        
        # 判断是否是文件夹
        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder":
            folder_id = payload[1]
            # 点击在文件夹上，显示文件夹特定操作菜单
            # 新建笔记（若该文件夹已存在"空的新笔记草稿"，则禁用）
            new_note_action = QAction("新建笔记", self)
            try:
                notes = self.note_manager.get_notes_by_folder(folder_id)
            except Exception:
                notes = []
            if any(self._is_empty_new_note(n) for n in notes):
                new_note_action.setEnabled(False)
            new_note_action.triggered.connect(lambda: self.create_note_in_folder(folder_id))
            menu.addAction(new_note_action)
            
            # 新建子文件夹
            new_subfolder_action = QAction("新建文件夹", self)
            new_subfolder_action.triggered.connect(lambda: self.create_subfolder(folder_id))
            menu.addAction(new_subfolder_action)
            
            menu.addSeparator()
            
            # 重命名文件夹
            rename_action = QAction("重命名文件夹", self)
            rename_action.triggered.connect(lambda: self.rename_folder(folder_id))
            menu.addAction(rename_action)
            
            # 删除文件夹
            delete_action = QAction("删除文件夹", self)
            delete_action.triggered.connect(lambda: self.delete_folder_confirm(folder_id))
            menu.addAction(delete_action)
            
            menu.exec(self.folder_list.mapToGlobal(position))
            return
        
        # 其他情况（系统项等），显示统一的三项菜单
        new_note_action = QAction("新建笔记", self)
        new_note_action.triggered.connect(self.create_new_note)
        menu.addAction(new_note_action)
        
        new_folder_action = QAction("新建文件夹", self)
        new_folder_action.triggered.connect(self.create_new_folder)
        menu.addAction(new_folder_action)
        
        new_tag_action = QAction("新建标签", self)
        new_tag_action.triggered.connect(self.create_new_tag)
        menu.addAction(new_tag_action)
        
        menu.exec(self.folder_list.mapToGlobal(position))
    
    def show_note_context_menu(self, position):
        """显示笔记列表的右键菜单"""
        item = self.note_list.itemAt(position)
        menu = QMenu(self)

        if item:
            # 点击在笔记上
            note_id = item.data(Qt.ItemDataRole.UserRole)

            # 新建笔记（在"所有笔记"和"最近删除"视图中禁用）
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(self.create_new_note)
            if self.current_folder_id is None or self.is_viewing_deleted:
                new_note_action.setEnabled(False)
            menu.addAction(new_note_action)

            menu.addSeparator()

            # 移到...
            move_to_menu = menu.addMenu("移到")
            self._populate_move_to_menu(move_to_menu, note_id)

            menu.addSeparator()

            # 置顶/取消置顶
            is_pinned = self.note_manager.is_note_pinned(note_id)
            pin_text = "取消置顶" if is_pinned else "置顶"
            pin_action = QAction(pin_text, self)
            pin_action.triggered.connect(lambda: self.toggle_pin_note(note_id))
            menu.addAction(pin_action)

            menu.addSeparator()

            # 重命名笔记
            rename_action = QAction("重命名笔记", self)
            rename_action.triggered.connect(lambda: self.rename_note(note_id))
            menu.addAction(rename_action)

            # 删除笔记
            delete_action = QAction("删除笔记", self)
            delete_action.triggered.connect(lambda: self.delete_note_by_id(note_id))
            menu.addAction(delete_action)
        else:
            # 点击在空白区域（在"所有笔记"和"最近删除"视图中禁用）
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(self.create_new_note)
            if self.current_folder_id is None or self.is_viewing_deleted:
                new_note_action.setEnabled(False)
            menu.addAction(new_note_action)

        menu.exec(self.note_list.mapToGlobal(position))

    def _populate_move_to_menu(self, menu: QMenu, note_id: str):
        """填充"移到"子菜单：展示所有文件夹（含层级）"""

        # 构建文件夹树
        try:
            all_folders = self.note_manager.get_all_folders()
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
                    # 子菜单的标题不可直接触发移动（和备忘录一致：展开后选择具体目标）
                    _add_folder_branch(sub, fid)

                    # 允许移动到这个父文件夹
                    sub.addSeparator()
                    act_here = QAction(f"移动到 \"{name}\"", self)
                    act_here.triggered.connect(lambda checked=False, _fid=fid: self._move_note_to_folder_and_refresh(note_id, _fid))
                    sub.addAction(act_here)
                else:
                    act = QAction(f"📁 {name}", self)
                    act.triggered.connect(lambda checked=False, _fid=fid: self._move_note_to_folder_and_refresh(note_id, _fid))
                    parent_menu.addAction(act)

        _add_folder_branch(menu, None)

        # 如果没有任何文件夹，给一个禁用提示
        if not children_map.get(None):
            empty = QAction("（暂无文件夹）", self)
            empty.setEnabled(False)
            menu.addAction(empty)

    def _move_note_to_folder_and_refresh(self, note_id: str, folder_id: str | None):
        """执行移动，并刷新笔记列表与左侧计数（尽量保持选中不跳）。"""
        try:
            self.note_manager.move_note_to_folder(note_id, folder_id)
        except Exception:
            return

        # 记录当前选中（避免刷新后跳走）
        selected_folder_row = self.folder_list.currentRow()
        selected_note_id = note_id

        # 刷新：笔记列表（当前视图可能会变化：比如从文件夹A移到B，A里会消失）
        self.load_notes()

        # 同步刷新左侧文件夹计数
        self.load_folders()
        try:
            if selected_folder_row is not None and 0 <= selected_folder_row < self.folder_list.count():
                self.folder_list.setCurrentRow(selected_folder_row)
        except Exception:
            pass

        # 尝试重新选中该笔记（如果移动后仍在当前列表里）
        try:
            for i in range(self.note_list.count()):
                it = self.note_list.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == selected_note_id:
                    self.note_list.setCurrentRow(i)
                    break
        except Exception:
            pass

    
    def create_subfolder(self, parent_folder_id: str):
        """在指定文件夹下创建子文件夹（不弹窗）：自动创建“新建文件夹/新建文件夹1/...”并进入就地重命名"""
        base_name = "新建文件夹"

        try:
            all_folders = self.note_manager.get_all_folders()
            existing = {
                str(f.get("name", "")).strip().casefold()
                for f in all_folders
                if f.get("parent_folder_id") == parent_folder_id
            }
        except Exception:
            existing = set()

        if base_name.casefold() not in existing:
            name = base_name
        else:
            i = 1
            while True:
                candidate = f"{base_name}{i}"
                if candidate.casefold() not in existing:
                    name = candidate
                    break
                i += 1

        folder_id = self.note_manager.create_folder(name, parent_folder_id)
        self.load_folders()

        # 选中新创建的子文件夹
        created_row = None
        for i, folder in enumerate(self.custom_folders):
            if folder['id'] == folder_id:
                created_row = 2 + i
                self.folder_list.setCurrentRow(created_row)
                break

        if created_row is not None:
            QTimer.singleShot(0, lambda: self.rename_folder(folder_id))

    
    def create_note_in_folder(self, folder_id: str, default_title: str | None = None):
        """在指定文件夹下创建笔记"""
        if default_title is None:
            default_title = "新笔记"

        # “同一文件夹只允许一个空的新笔记草稿”
        if folder_id and default_title == "新笔记":
            try:
                notes = self.note_manager.get_notes_by_folder(folder_id)
            except Exception:
                notes = []
            if any(self._is_empty_new_note(n) for n in notes):
                self._update_new_note_action_enabled()
                return

        # 创建笔记
        note_id = self.note_manager.create_note(title=default_title, folder_id=folder_id)
        try:
            self.note_manager.update_note(note_id, title=default_title)
        except Exception:
            pass

        # 刷新笔记列表
        self.load_notes()

        # 同步刷新左侧文件夹计数
        selected_row = self.folder_list.currentRow()
        self.load_folders()
        try:
            if selected_row is not None and 0 <= selected_row < self.folder_list.count():
                self.folder_list.setCurrentRow(selected_row)
        except Exception:
            pass

        # 选中新创建的笔记
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentItem(item)
                break

        # 设置焦点到编辑器，让光标闪烁
        self.editor.text_edit.setFocus()

        # self._update_new_note_action_enabled()
    
    def toggle_pin_note(self, note_id: str):
        """切换笔记的置顶状态"""
        is_pinned = self.note_manager.toggle_pin_note(note_id)
        
        # 重新加载笔记列表
        self.load_notes()
        
        # 显示提示信息
        status_text = "已置顶" if is_pinned else "已取消置顶"
        self.statusBar().showMessage(status_text, 2000)
    
    def batch_delete_notes(self, note_ids: list):
        """批量删除笔记"""
        count = len(note_ids)
        
        # 根据当前视图决定删除方式和提示信息
        if self.is_viewing_deleted:
            # 在"最近删除"视图中，执行永久删除
            title = "确认永久删除"
            message = f"确定要永久删除这 {count} 条笔记吗？此操作不可恢复！"
        else:
            # 在其他视图中，移到回收站
            title = "确认删除"
            message = f"确定要删除这 {count} 条笔记吗？笔记将会被移到“最近删除”中"
        
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for note_id in note_ids:
                if self.is_viewing_deleted:
                    # 永久删除
                    self.note_manager.permanently_delete_note(note_id)
                else:
                    # 移到回收站
                    self.note_manager.delete_note(note_id)
            
            # 清除多选状态
            self.selected_note_rows.clear()
            
            # 重新加载笔记列表
            self.load_notes()
            
            # 同步刷新左侧文件夹计数
            selected_row = self.folder_list.currentRow()
            self.load_folders()
            try:
                if selected_row is not None and 0 <= selected_row < self.folder_list.count():
                    self.folder_list.setCurrentRow(selected_row)
            except Exception:
                pass
            
            # 如果删除的包含当前笔记，清空编辑器
            if self._get_current_note_id() in note_ids:
                self._set_current_note_id(None)
                self.editor.clear()
            
            status_message = f"已永久删除 {count} 条笔记" if self.is_viewing_deleted else f"已删除 {count} 条笔记"
            self.statusBar().showMessage(status_message, 2000)
    
    def batch_move_notes(self, note_ids: list, target_folder_id: str):
        """批量移动笔记到指定文件夹"""
        for note_id in note_ids:
            self.note_manager.move_note_to_folder(note_id, target_folder_id)
        
        # 清除多选状态
        self.selected_note_rows.clear()
        
        # 重新加载笔记列表和文件夹列表
        self.load_notes()
        self.load_folders()
        
        count = len(note_ids)
        folder_name = "所有笔记" if target_folder_id is None else self.note_manager.get_folder(target_folder_id)['name']
        self.statusBar().showMessage(f"已将 {count} 条笔记移动到 {folder_name}", 2000)
    
    def batch_toggle_pin_notes(self, note_ids: list):
        """批量切换笔记的置顶状态"""
        # 检查是否都已置顶
        all_pinned = all(self.note_manager.is_note_pinned(nid) for nid in note_ids)
        
        # 统一设置为相反状态
        for note_id in note_ids:
            current_pinned = self.note_manager.is_note_pinned(note_id)
            if all_pinned and current_pinned:
                # 都已置顶，则取消置顶
                self.note_manager.toggle_pin_note(note_id)
            elif not all_pinned and not current_pinned:
                # 不是都置顶，则将未置顶的置顶
                self.note_manager.toggle_pin_note(note_id)
        
        # 清除多选状态
        self.selected_note_rows.clear()
        
        # 重新加载笔记列表
        self.load_notes()
        
        count = len(note_ids)
        status_text = f"已取消置顶 {count} 条笔记" if all_pinned else f"已置顶 {count} 条笔记"
        self.statusBar().showMessage(status_text, 2000)
    
    def batch_add_tag_to_notes(self, note_ids: list, tag_id: str, tag_name: str):
        """批量为笔记添加标签"""
        for note_id in note_ids:
            self.note_manager.add_tag_to_note(note_id, tag_id)
        
        # 清除多选状态
        self.selected_note_rows.clear()
        
        # 重新加载笔记列表和文件夹列表（更新标签数字）
        self.load_notes()
        self.load_folders()
        
        count = len(note_ids)
        self.statusBar().showMessage(f"已为 {count} 条笔记添加标签 '{tag_name}'", 2000)
    
    def toggle_tag_for_notes(self, note_ids: list, tag_id: str, tag_name: str, has_tag: bool):
        """切换笔记的标签（添加或移除）"""
        if has_tag:
            # 移除标签
            for note_id in note_ids:
                self.note_manager.remove_tag_from_note(note_id, tag_id)
            action_text = "移除"
        else:
            # 添加标签
            for note_id in note_ids:
                self.note_manager.add_tag_to_note(note_id, tag_id)
            action_text = "添加"
        
        # 清除多选状态
        self.selected_note_rows.clear()
        
        # 重新加载笔记列表和文件夹列表（更新标签数字）
        self.load_notes()
        self.load_folders()
        
        count = len(note_ids)
        self.statusBar().showMessage(f"已为 {count} 条笔记{action_text}标签 '{tag_name}'", 2000)
    
    def create_note_in_current_folder(self):
        """在当前文件夹下创建笔记"""
        if self.current_folder_id:
            self.create_note_in_folder(self.current_folder_id)
    
    def delete_note_by_id(self, note_id: str):
        """根据ID删除笔记"""
        # 根据当前视图决定删除方式和提示信息
        if self.is_viewing_deleted:
            # 在"最近删除"视图中，执行永久删除
            title = "确认永久删除"
            message = "确定要永久删除这条笔记吗？此操作不可恢复！"
        else:
            # 在其他视图中，移到回收站
            title = "确认删除"
            message = "确定要删除这条笔记吗？"
        
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.is_viewing_deleted:
                # 永久删除
                self.note_manager.permanently_delete_note(note_id)
            else:
                # 移到回收站
                self.note_manager.delete_note(note_id)
            
            self.load_notes()

            # 同步刷新左侧文件夹计数
            selected_row = self.folder_list.currentRow()
            self.load_folders()
            try:
                if selected_row is not None and 0 <= selected_row < self.folder_list.count():
                    self.folder_list.setCurrentRow(selected_row)
            except Exception:
                pass
            
            # 如果删除的是当前笔记，清空编辑器
            if note_id == self._get_current_note_id():
                self._set_current_note_id(None)
                self.editor.clear()
    
    def delete_note(self):
        """删除当前笔记（保留用于快捷键）"""
        if self._get_current_note_id() is None:
            return
        
        self.delete_note_by_id(self._get_current_note_id())
            
    def _set_row_widget_selected(self, row_widget: QWidget | None, selected: bool):
        """设置行 widget 的选中状态"""
        if not row_widget or row_widget.objectName() != "folder_row_widget":
            return
        row_widget.setProperty("selected", selected)
        row_widget.style().unpolish(row_widget)
        row_widget.style().polish(row_widget)
        row_widget.update()

    def _find_row_widget_by_payload(self, item_type: str, item_id: str):
        """根据 payload 类型和 ID 查找对应的 row widget"""
        if not item_id:
            return None
        
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if not item:
                continue
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, tuple) and len(payload) == 2:
                if payload[0] == item_type and payload[1] == item_id:
                    return self.folder_list.itemWidget(item)
        return None

    def _get_current_view_key(self):
        """获取当前视图的唯一标识
        
        Returns:
            str: 视图key，格式如 "system:all_notes", "folder:123", "tag:456"
        """
        if self.is_viewing_deleted:
            return "system:deleted"
        elif self.current_tag_id is not None:
            return f"tag:{self.current_tag_id}"
        elif self.current_folder_id is not None:
            return f"folder:{self.current_folder_id}"
        else:
            # 默认是"所有笔记"
            return "system:all_notes"
    
    def _get_current_note_id(self):
        """获取当前视图的笔记ID
        
        Returns:
            int or None: 当前笔记ID
        """
        view_key = self._get_current_view_key()
        return self._last_note_per_view.get(view_key)
    
    def _set_current_note_id(self, note_id):
        """设置当前视图的笔记ID
        
        Args:
            note_id: 笔记ID，可以为None
        """
        view_key = self._get_current_view_key()
        if note_id is None:
            # 删除该视图的记录
            self._last_note_per_view.pop(view_key, None)
        else:
            self._last_note_per_view[view_key] = note_id
        
        # 如果是文件夹视图，同时保存到数据库
        if view_key.startswith("folder:"):
            folder_id = view_key.split(":", 1)[1]
            try:
                self.note_manager.set_folder_last_note_id(folder_id, note_id)
            except Exception as e:
                print(f"保存文件夹上次笔记失败: {e}")

    def _get_current_item_info(self, index):
        """获取当前选中项的信息
        
        Returns:
            tuple: (item_type, folder_id, system_key, tag_id, cur_item)
        """
        if index is None or not (0 <= index < self.folder_list.count()):
            return None, None, None, None, None
        
        cur_item = self.folder_list.item(index)
        if not cur_item:
            return None, None, None, None, None
        
        payload = cur_item.data(Qt.ItemDataRole.UserRole)
        if not (isinstance(payload, tuple) and len(payload) == 2):
            return None, None, None, None, None
        
        item_type = payload[0]
        item_id = payload[1]
        
        # 根据类型返回对应的信息
        if item_type == "folder":
            return item_type, item_id, None, None, cur_item
        elif item_type == "system":
            return item_type, None, item_id, None, cur_item
        elif item_type == "tag":
            return item_type, None, None, item_id, cur_item
        
        return item_type, None, None, None, cur_item

    def _handle_tag_selection(self, cur_item, cur_tag_id: str):
        """处理标签选中逻辑"""
        # 取消之前选中标签的高亮
        prev_tag_id = getattr(self, "_prev_selected_tag_id", None)
        if prev_tag_id:
            prev_tag_widget = self._find_row_widget_by_payload("tag", prev_tag_id)
            self._set_row_widget_selected(prev_tag_widget, False)
        
        # 设置当前标签高亮
        cur_tag_widget = self.folder_list.itemWidget(cur_item) if cur_item else None
        self._set_row_widget_selected(cur_tag_widget, True)
        
        # 记录当前选中的标签（保持文件夹的选中状态，实现双选中）
        self.current_tag_id = cur_tag_id
        self._prev_selected_tag_id = cur_tag_id

    def _handle_folder_or_system_selection(self, cur_item, cur_folder_id: str, cur_system_key: str):
        """处理文件夹或系统项选中逻辑"""
        # 取消之前的标签高亮
        prev_tag_id = getattr(self, "_prev_selected_tag_id", None)
        if prev_tag_id:
            prev_tag_widget = self._find_row_widget_by_payload("tag", prev_tag_id)
            self._set_row_widget_selected(prev_tag_widget, False)
            self._prev_selected_tag_id = None
        
        # 取消之前的文件夹/系统项高亮
        prev_folder_id = getattr(self, "_prev_selected_folder_id", None)
        prev_system_key = getattr(self, "_prev_selected_system_key", None)
        
        prev_widget = None
        if prev_folder_id:
            prev_widget = self._find_row_widget_by_payload("folder", prev_folder_id)
        elif prev_system_key:
            prev_widget = self._find_row_widget_by_payload("system", prev_system_key)
        if prev_widget:
            self._set_row_widget_selected(prev_widget, False)
        
        # 设置当前行选中
        cur_widget = self.folder_list.itemWidget(cur_item) if cur_item else None
        self._set_row_widget_selected(cur_widget, True)
        
        # 记录当前选中的语义ID
        self._prev_selected_folder_id = cur_folder_id
        self._prev_selected_system_key = cur_system_key
        self.current_tag_id = None

    def on_folder_changed(self, index):
        """文件夹切换：选中行变化时，更新高亮状态并加载笔记"""
        try:
            # 1. 保存当前视图的笔记（在切换视图之前）
            current_note_id = self._get_current_note_id()
            if current_note_id:
                self.save_current_note()
            
            # 2. 获取当前选中项的信息
            item_type, folder_id, system_key, tag_id, cur_item = self._get_current_item_info(index)
            
            if not item_type:
                return
            
            # 3. 根据类型处理选中逻辑（这会更新 current_folder_id/current_tag_id/is_viewing_deleted）
            if item_type == "tag":
                self._handle_tag_selection(cur_item, tag_id)
            else:
                self._handle_folder_or_system_selection(cur_item, folder_id, system_key)
        except Exception:
            pass
        
        # 4. 加载新视图的笔记，并尝试恢复该视图上次编辑的笔记
        new_view_key = self._get_current_view_key()
        last_note_id = self._last_note_per_view.get(new_view_key)
        self.load_notes(select_note_id=last_note_id)

    def on_folder_item_double_clicked(self, item: QListWidgetItem):
        """左侧文件夹列表：双击文件夹行时展开/折叠（仅对有子文件夹的自定义文件夹生效）"""
        if not item:
            return

        payload = item.data(Qt.ItemDataRole.UserRole)
        if not (isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder"):
            return

        folder_id = payload[1]

        # 仅当该文件夹确实有子文件夹时才切换
        try:
            all_folders = self.note_manager.get_all_folders()
            has_children = any(f.get('parent_folder_id') == folder_id for f in all_folders)
        except Exception:
            has_children = False

        if not has_children:
            return

        self._toggle_folder_expanded(folder_id)

    def on_folder_item_clicked(self, item: QListWidgetItem):
        """左侧文件夹列表：选中状态下再次单击进入重命名（仅自定义文件夹和标签）。

        说明：由于文件夹行使用了 `setItemWidget`，Qt 的原生 inline 编辑器无法正常工作，
        这里采用 Finder 风格的"再次单击"触发弹窗重命名。
        """
        if not item:
            return

        payload = item.data(Qt.ItemDataRole.UserRole)
        
        # 支持文件夹和标签
        if not (isinstance(payload, tuple) and len(payload) == 2 and payload[0] in ("folder", "tag")):
            # 仅文件夹和标签支持该交互（系统项/标题不处理）
            self._last_folder_click_folder_id = None
            self._last_folder_click_ms = 0
            return


        item_type = payload[0]  # "folder" 或 "tag"
        item_id = payload[1]

        # 判断这次点击是否点在"当前已选中的同一行"
        current_item = self.folder_list.currentItem()
        is_clicking_selected_same_item = (current_item is item)

        from PyQt6.QtCore import QElapsedTimer
        if not hasattr(self, "_folder_click_timer"):
            self._folder_click_timer = QElapsedTimer()
            self._folder_click_timer.start()
            self._last_folder_click_folder_id = item_id
            self._last_folder_click_type = item_type
            return

        elapsed_ms = self._folder_click_timer.elapsed()
        same_item = (self._last_folder_click_folder_id == item_id and 
                     hasattr(self, '_last_folder_click_type') and 
                     self._last_folder_click_type == item_type)

        # 第二次点击：时间间隔不要太短（避免与双击冲突），也不要太长
        if is_clicking_selected_same_item and same_item and 350 <= elapsed_ms <= 1200:
            if item_type == "folder":
                self.rename_folder(item_id)
            elif item_type == "tag":
                self.rename_tag(item_id)
            self._folder_click_timer.restart()
            self._last_folder_click_folder_id = item_id
            self._last_folder_click_type = item_type
            return

        # 第一次点击：记录
        self._folder_click_timer.restart()
        self._last_folder_click_folder_id = item_id
        self._last_folder_click_type = item_type

        
    def _update_item_widget_selection(self, item, selected: bool):
        """更新列表项widget的选中状态
        
        让选中背景由条目widget自身绘制（避免QListWidget默认选中背景出现上下错位）
        
        Args:
            item: QListWidgetItem 列表项
            selected: bool 是否选中
        """
        if not item:
            return
        
        widget = self.note_list.itemWidget(item)
        if not widget or widget.objectName() != "note_item_widget":
            return
        
        widget.setProperty("selected", selected)
        # 触发QSS重新应用
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
    
    def _handle_previous_note_cleanup(self, previous_item):
        """处理之前笔记的清理工作
        
        Args:
            previous_item: QListWidgetItem 之前选中的列表项
        """
        if not previous_item:
            return
        
        # 取消之前项的选中状态
        self._update_item_widget_selection(previous_item, False)
        
        # 保存之前的笔记（包括光标位置）
        prev_note_id = self._get_current_note_id()
        self.save_current_note()  # 保存笔记内容（包括光标位置）
        
        # 切换笔记时：清理"已删除但可撤销"的附件（此时用户已离开该笔记）
        self._cleanup_note_attachment_trash(prev_note_id)
    
    def _cleanup_note_attachment_trash(self, note_id):
        """清理笔记的附件垃圾
        
        Args:
            note_id: str 笔记ID
        """
        try:
            if note_id and getattr(self.note_manager, 'attachment_manager', None):
                self.note_manager.attachment_manager.cleanup_note_attachment_trash(note_id)
        except Exception:
            pass

    def restore_cursor_position(self, note):
        """恢复笔记的光标位置

        Args:
            note: dict 笔记对象，包含 cursor_position 字段

        功能：
            1. 如果笔记有保存的光标位置且大于0，恢复到该位置
            2. 否则，设置光标到标题末尾
            3. 设置光标位置时会触发 cursorPositionChanged 信号，从而调用 update_title_and_input_format 进行标题格式设置
        """
        note_id = note.get('id', 'unknown')
        try:
            cursor_position = note.get('cursor_position', 0)
            if cursor_position is not None and cursor_position > 0:
                # 恢复到上次保存的光标位置
                self._set_editor_cursor_to_position(cursor_position, note_id)
            else:
                # 如果没有保存的光标位置，设置到标题末尾
                logger.debug(f"[restore_cursor_position] 没有保存的光标位置或者光标位置为0，设置到标题末尾: note_id={note_id}, "
                             f"cursor_position={cursor_position}")
                self._set_editor_cursor_to_title_end()
        except Exception as e:
            # 出错时设置到标题末尾
            logger.debug(f"[restore_cursor_position] 恢复光标位置出错，设置到标题末尾: note_id={note_id}, error={e}")
            self._set_editor_cursor_to_title_end()

    def _set_editor_cursor_to_position(self, cursor_position, note_id='unknown'):
        """设置编辑器光标到指定位置

        Args:
            cursor_position: int 光标位置
            note_id: str 笔记ID，用于日志记录

        功能：
            使用封装的 setCursorPosition 方法设置光标位置
            这会触发 cursorPositionChanged 信号，从而调用 update_title_and_input_format 进行标题格式设置
        """
        logger.debug(f"[_set_editor_cursor_to_position] 设置光标位置: note_id={note_id}, "
                     f"cursor_position={cursor_position}")
        # 使用封装的 setCursorPosition 方法设置光标位置
        # 这会触发 cursorPositionChanged 信号，从而调用 update_title_and_input_format 进行标题格式设置
        self.editor.text_edit.setCursorPosition(cursor_position)

    def _set_editor_cursor_to_title_end(self):
        """将编辑器光标移动到标题末尾，标题格式通过cursorPositionChanged信号处理"""
        from PyQt6.QtGui import QTextCursor
        cursor = self.editor.text_edit.textCursor()
        initial_position = cursor.position()
        cursor.movePosition(QTextCursor.MoveOperation.Start)  # 移动到第一行末尾
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)  # 移动到第一行末尾
        final_position = cursor.position()
        # 如果光标位置有变化，设置光标，会触发cursorPositionChanged信号，进而调用update_title_and_input_format设置标题格式
        if final_position != initial_position:
            self.editor.text_edit.setCursorPosition(final_position)
        logger.debug(f"[_set_editor_cursor_to_title_end] 初始光标位置: {initial_position}, 最终光标位置: {final_position}")

        # 如果cursor位置没有变化（文档为空时），手动触发标题格式设置，因为前面的setTextCursor在position位置
        # 相同的情况下不会调用setTextCursor（实际上即便调用了，因为position相同也不会触发cursorPositionChanged信号）
        if initial_position == final_position:
            self.editor.text_edit.update_title_and_input_format()

    def _load_and_display_note(self, note_id):
        """加载并显示笔记内容
        
        Args:
            note_id: str 笔记ID
        """
        note = self.note_manager.get_note(note_id)
        if not note:
            logger.warning(f"[_load_and_display_note] 笔记不存在: note_id={note_id}")
            return
        
        # 记录加载信息
        content = note.get('content', '')
        plain_text_preview = self.editor.toPlainText() if hasattr(self.editor, 'toPlainText') else ''
        logger.info(f"[_load_and_display_note] 开始加载笔记: note_id={note_id}, title={note.get('title', '')}, "
                    f"content_length={len(content)}, cursor_position={note.get('cursor_position', 0)}")
        logger.debug(f"[_load_and_display_note] 内容前100字符: {content[:100] if content else '(空)'}")
        
        # 加载笔记内容（阻止信号避免触发自动保存）
        self.editor.blockSignals(True)
        self.editor.setHtml(note['content'])
        self.editor.blockSignals(False)
        
        # 验证加载后的内容
        loaded_plain_text = self.editor.toPlainText()
        logger.info(f"[_load_and_display_note] 笔记内容已加载到编辑器: plain_text_length={len(loaded_plain_text)}")

        # 恢复光标位置
        self.restore_cursor_position(note)
        
        # 标记编辑器已初始化（已加载过内容）
        self._editor_initialized = True
        logger.debug(f"[_load_and_display_note] 编辑器已初始化: note_id={note_id}")
    
    def _clear_editor(self):
        """清空编辑器"""
        self._set_current_note_id(None)
        self.editor.clear()
        try:
            self.editor.text_edit.clearFocus()
        except Exception:
            pass

    # note_list.clear()会触发这个事件，需要解决
    def on_note_selected(self, current, previous):
        """笔记选中事件
        
        Args:
            current: QListWidgetItem 当前选中的列表项
            previous: QListWidgetItem 之前选中的列表项
        """
        # 1. 处理之前笔记的清理工作
        self._handle_previous_note_cleanup(previous)
        
        # 2. 处理当前选中的笔记
        if current:
            # 更新选中状态
            self._update_item_widget_selection(current, True)
            
            # 设置当前笔记ID
            note_id = current.data(Qt.ItemDataRole.UserRole)
            self._set_current_note_id(note_id)
            
            # 加载并显示笔记
            self._load_and_display_note(note_id)
        else:
            # 没有选中任何笔记，清空编辑器
            self._clear_editor()
        
        # 3. 刷新"新建笔记"按钮的可用状态
        self._update_new_note_action_enabled()

    def select_single_note(self, row):
        """单选笔记"""
        # 清除之前的多选状态
        self._clear_all_selections()
        
        # 选中指定行
        self.selected_note_rows = {row}
        self._update_visual_selection()
        
        # 加载笔记到编辑器
        item = self.note_list.item(row)
        if item:
            # 保存之前的笔记（包括光标位置）
            if self._get_current_note_id():
                self.save_current_note()  # 保存笔记内容（包括光标位置）
            
            # 阻止信号，避免触发on_note_selected，如果不阻塞，此操作会触发currentItemChanged 信号，导致调用on_note_selected
            self.note_list.blockSignals(True)
            self.note_list.setCurrentItem(item)
            self.note_list.blockSignals(False)
            
            # 加载新笔记
            note_id = item.data(Qt.ItemDataRole.UserRole)
            self._set_current_note_id(note_id)
            self._load_and_display_note(note_id)
    
    def toggle_note_selection(self, row):
        """切换笔记的选中状态（Command键跳选）"""
        if row in self.selected_note_rows:
            # 如果已选中，则取消选中
            self.selected_note_rows.discard(row)
            if not self.selected_note_rows:
            # 如果没有选中项了，保存当前笔记，然后清空编辑器
                if self._get_current_note_id():
                    self.save_current_note()
                self._set_current_note_id(None)
                self.editor.clear()
        else:
            # 如果未选中，则添加到选中集合
            # 先保存当前笔记
            if self._get_current_note_id():
                self.save_current_note()
            
            self.selected_note_rows.add(row)
            # 将最后选中的项设为当前项
            item = self.note_list.item(row)
            if item:
                self.note_list.blockSignals(True)
                self.note_list.setCurrentItem(item)
                self.note_list.blockSignals(False)
                # 加载这个笔记到编辑器
                note_id = item.data(Qt.ItemDataRole.UserRole)
                self._set_current_note_id(note_id)
                self._load_and_display_note(note_id)
        
        self._update_visual_selection()
    
    def select_note_range(self, start_row, end_row):
        """范围选择笔记（Shift键）"""
        # 清除之前的选择
        self._clear_all_selections()
        
        # 确定范围
        min_row = min(start_row, end_row)
        max_row = max(start_row, end_row)
        
        # 选中范围内所有可选中的笔记项
        for row in range(min_row, max_row + 1):
            item = self.note_list.item(row)
            if item and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                self.selected_note_rows.add(row)
        
        # 设置最后点击的项为当前项
        if self.selected_note_rows:
            item = self.note_list.item(end_row)
            if item:
                self.note_list.blockSignals(True)
                self.note_list.setCurrentItem(item)
                self.note_list.blockSignals(False)
                # 加载这个笔记到编辑器
                note_id = item.data(Qt.ItemDataRole.UserRole)
                self._set_current_note_id(note_id)
                note = self.note_manager.get_note(note_id)
                if note:
                    self.editor.blockSignals(True)
                    self.editor.setHtml(note['content'])
                    self.editor.blockSignals(False)
        
        self._update_visual_selection()
    
    def _clear_all_selections(self):
        """清除所有选中状态的视觉效果"""
        for row in self.selected_note_rows:
            item = self.note_list.item(row)
            if item:
                widget = self.note_list.itemWidget(item)
                if widget and widget.objectName() == "note_item_widget":
                    widget.setProperty("selected", False)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()
        self.selected_note_rows.clear()
    
    def _update_visual_selection(self):
        """更新所有笔记项的视觉选中状态"""
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                widget = self.note_list.itemWidget(item)
                if widget and widget.objectName() == "note_item_widget":
                    is_selected = i in self.selected_note_rows
                    widget.setProperty("selected", is_selected)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()

    def on_text_changed(self):
        """文本变化事件"""
        if self._get_current_note_id():
            # 自动保存
            self.save_current_note()

    def _normalize_text(self, text):
        """标准化文本：统一换行符
        
        Args:
            text: 原始文本
            
        Returns:
            str: 标准化后的文本（使用\n作为换行符）
        """
        return (text or "").replace("\r\n", "\n").replace("\r", "\n")
    
    def _extract_title_from_content(self, plain_text):
        """从笔记内容中提取标题
        
        规则：
        - 整条笔记为空（没有任何可见字符）=> 标题使用"新笔记"
        - 第一行只有零宽度字符（U+200B）=> 标题使用"新笔记"
        - 正文有内容但第一行为空 => 标题为"无标题"
        
        Args:
            plain_text: 笔记的纯文本内容
            
        Returns:
            str: 提取的标题
        """
        normalized_plain = self._normalize_text(plain_text)
        is_note_empty = normalized_plain.strip() == ""

        if is_note_empty:
            return "新笔记"
        
        first_line = normalized_plain.split("\n")[0][:50]
        # 移除零宽度字符后检查
        first_line_cleaned = first_line.replace('\u200B', '').strip()
        
        if not first_line_cleaned:
            # 第一行只有零宽度字符或空白
            return "新笔记"
        
        return first_line.strip() or "无标题"
    
    def _extract_preview_text(self, plain_text, title):
        """从笔记内容中提取预览文本（正文第一行）
        
        规则：跳过空行、跳过与标题相同的行
        
        Args:
            plain_text: 笔记的纯文本内容
            title: 笔记标题
            
        Returns:
            str: 预览文本（最多35个字符）
        """
        normalized_plain = self._normalize_text(plain_text)
        lines = [l.strip() for l in normalized_plain.split("\n") if l.strip()]
        candidates = lines[1:] if len(lines) >= 2 else []

        preview_text = ""
        for c in candidates:
            if not c:
                continue
            if title and c == title:
                continue
            preview_text = c
            break

        if len(preview_text) > 35:
            preview_text = preview_text[:35] + '...'
        
        return preview_text
    
    def _get_note_time_string(self, note_id):
        """获取笔记的更新时间字符串
        
        Args:
            note_id: 笔记ID
            
        Returns:
            str: 格式化的时间字符串（YYYY/MM/DD）
        """
        from datetime import datetime
        try:
            note_obj = self.note_manager.get_note(note_id)
            updated_at = datetime.fromisoformat(note_obj.get('updated_at')) if note_obj else None
            return updated_at.strftime('%Y/%m/%d') if updated_at else ''
        except Exception:
            return ''
    
    def _update_label_text(self, label, text):
        """更新标签文本（支持 ElidedLabel 和 QLabel）
        
        Args:
            label: 标签控件
            text: 要设置的文本
        """
        if isinstance(label, ElidedLabel):
            label.setFullText(text)
            label.setToolTip(text)
        elif isinstance(label, QLabel):
            label.setText(text)
    
    def _update_note_list_item_title(self, layout, title):
        """更新笔记列表项的标题
        
        Args:
            layout: 笔记列表项的布局
            title: 新标题
        """
        if layout.count() > 0:
            title_label = layout.itemAt(0).widget()
            self._update_label_text(title_label, title)
    
    def _update_note_list_item_preview(self, layout, plain_text, title):
        """更新笔记列表项的预览信息（时间 + 正文第一行）
        
        Args:
            layout: 笔记列表项的布局
            plain_text: 笔记的纯文本内容
            title: 笔记标题
        """
        try:
            preview_text = self._extract_preview_text(plain_text, title)
            time_str = self._get_note_time_string(self._get_current_note_id())
            info_text = f"{time_str}    {preview_text}"

            if layout.count() > 1:
                info_label = layout.itemAt(1).widget()
                self._update_label_text(info_label, info_text)
        except Exception:
            pass
    
    def _find_note_list_item_by_id(self, note_id):
        """根据笔记ID查找列表中对应的item
        
        Args:
            note_id: 笔记ID
            
        Returns:
            tuple: (item, widget, layout) 或 (None, None, None)
        """
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == note_id:
                widget = self.note_list.itemWidget(item)
                if widget:
                    layout = widget.layout()
                    if layout and layout.count() > 0:
                        return item, widget, layout
        return None, None, None
    
    def _update_note_list_display(self, title, plain_text):
        """更新笔记列表中的显示（标题和预览）
        
        Args:
            title: 笔记标题
            plain_text: 笔记的纯文本内容
        """
        item, widget, layout = self._find_note_list_item_by_id(self._get_current_note_id())
        if layout:
            # 更新标题
            self._update_note_list_item_title(layout, title)
            # 更新预览
            self._update_note_list_item_preview(layout, plain_text, title)
    
    def save_current_note(self):
        """保存当前笔记"""
        # 如果编辑器还未初始化（启动阶段），不保存
        if not self._editor_initialized:
            logger.debug("[save_current_note] 编辑器未初始化，跳过保存")
            return
        
        if not self._get_current_note_id():
            logger.debug("[save_current_note] 没有当前笔记ID，跳过保存")
            return
        
        # 1. 获取编辑器内容
        content = self.editor.toHtml()
        plain_text = self.editor.toPlainText()
        
        # 2. 提取标题
        title = self._extract_title_from_content(plain_text)
        
        # 3. 获取光标位置
        try:
            cursor = self.editor.text_edit.textCursor()
            cursor_position = cursor.position()
        except Exception:
            cursor_position = 0
        
        # 记录保存信息
        logger.info(f"[save_current_note] 开始保存笔记: note_id={self._get_current_note_id()}, title={title}, "
                    f"content_length={len(content)}, plain_text_length={len(plain_text)}, "
                    f"cursor_position={cursor_position}")
        logger.debug(f"[save_current_note] 内容前100字符: {plain_text[:len(plain_text)] if plain_text else '(空)'}")
        
        # 4. 更新笔记到数据库（包括光标位置）
        self.note_manager.update_note(
            self._get_current_note_id(),
            title=title,
            content=content,
            cursor_position=cursor_position
        )
        
        logger.info(f"[save_current_note] 笔记保存完成: note_id={self._get_current_note_id()}")
        
        # 5. 更新列表中的显示
        self._update_note_list_display(title, plain_text)

    def insert_image(self):
        """插入图片"""
        if not self._get_current_note_id():
            QMessageBox.warning(self, "提示", "请先选择或创建一个笔记")
            return
        
        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.svg);;所有文件 (*.*)"
        )
        
        if file_path:
            # 调用编辑器的插入图片方法
            from PyQt6.QtGui import QImage
            image = QImage(file_path)
            if not image.isNull():
                self.editor.insert_image_to_editor(image)
            else:
                QMessageBox.warning(self, "错误", "无法加载图片文件")
    
    def insert_attachment(self):
        """插入附件"""
        if not self._get_current_note_id():
            QMessageBox.warning(self, "提示", "请先选择或创建一个笔记")
            return
        
        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择附件",
            "",
            "所有文件 (*.*)"
        )
        
        if file_path:
            # 调用编辑器的内部方法处理附件（传递文件路径）
            self.editor._insert_attachment_with_path(file_path)
                
    def export_to_pdf(self):
        """导出当前笔记为PDF"""
        if not self._get_current_note_id():
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self._get_current_note_id())
        if not note:
            return
            
        filepath = self.export_manager.export_to_pdf(note['title'], note['content'])
        
        if filepath:
            reply = QMessageBox.question(
                self, "导出成功",
                f"笔记已导出为PDF\n\n{filepath}\n\n是否打开文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))
        else:
            QMessageBox.critical(self, "导出失败", "导出PDF时发生错误")
            
    def export_to_word(self):
        """导出当前笔记为Word"""
        if not self._get_current_note_id():
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self._get_current_note_id())
        if not note:
            return
            
        filepath = self.export_manager.export_to_word(note['title'], note['content'])
        
        if filepath:
            reply = QMessageBox.question(
                self, "导出成功",
                f"笔记已导出为Word\n\n{filepath}\n\n是否打开文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))
        else:
            QMessageBox.critical(self, "导出失败", "导出Word时发生错误\n\n请确保已安装 python-docx 和 beautifulsoup4 库")
            
    def export_to_markdown(self):
        """导出当前笔记为Markdown"""
        if not self._get_current_note_id():
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self._get_current_note_id())
        if not note:
            return
            
        filepath = self.export_manager.export_to_markdown(note['title'], note['content'])
        
        if filepath:
            reply = QMessageBox.question(
                self, "导出成功",
                f"笔记已导出为Markdown\n\n{filepath}\n\n是否打开文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))
        else:
            QMessageBox.critical(self, "导出失败", "导出Markdown时发生错误\n\n请确保已安装 html2text 和 beautifulsoup4 库")
            
    def export_to_html(self):
        """导出当前笔记为HTML"""
        if not self._get_current_note_id():
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self._get_current_note_id())
        if not note:
            return
            
        filepath = self.export_manager.export_to_html(note['title'], note['content'])
        
        if filepath:
            reply = QMessageBox.question(
                self, "导出成功",
                f"笔记已导出为HTML\n\n{filepath}\n\n是否打开文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))
        else:
            QMessageBox.critical(self, "导出失败", "导出HTML时发生错误")
            
    def open_export_folder(self):
        """打开导出文件夹"""
        export_dir = self.export_manager.get_export_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(export_dir))
        
    def toggle_sync(self, checked):
        """切换同步状态"""
        if checked:
            success, message = self.sync_manager.enable_sync()
            if success:
                QMessageBox.information(self, "成功", message)
            else:
                QMessageBox.warning(self, "失败", message)
                self.enable_sync_action.setChecked(False)
        else:
            success, message = self.sync_manager.disable_sync()
            QMessageBox.information(self, "提示", message)
            
    def sync_now(self):
        """立即同步到iCloud"""
        if not self.sync_manager.sync_enabled:
            QMessageBox.warning(self, "提示", "请先启用iCloud同步")
            return
            
        # 保存当前笔记
        self.save_current_note()
        
        # 执行同步
        success, message = self.sync_manager.sync_notes()
        
        if success:
            QMessageBox.information(self, "同步成功", message)
        else:
            QMessageBox.warning(self, "同步失败", message)
            
    def pull_from_icloud(self):
        """从iCloud拉取笔记"""
        if not self.sync_manager.sync_enabled:
            QMessageBox.warning(self, "提示", "请先启用iCloud同步")
            return
            
        reply = QMessageBox.question(
            self, "确认拉取",
            "从iCloud拉取数据会合并远程笔记，可能会覆盖本地修改。\n\n确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        # 拉取数据
        success, result = self.sync_manager.pull_notes()
        
        if success:
            remote_records = result['notes']
            
            # 合并笔记
            merged_count = self.sync_manager.merge_notes(remote_records)
            
            # 刷新列表
            self.load_notes()
            
            QMessageBox.information(
                self, "拉取成功",
                f"已从iCloud拉取并合并笔记\n\n共合并{merged_count}条笔记"
            )
        else:
            QMessageBox.warning(self, "拉取失败", result)
            
    def auto_sync(self):
        """自动同步"""
        if self.sync_manager.sync_enabled:
            self.save_current_note()
            self.sync_manager.auto_sync()
            
    def show_sync_status(self):
        """显示同步状态"""
        status = self.sync_manager.get_sync_status()
        
        status_text = f"同步状态:\n\n"
        status_text += f"同步方式: {status.get('sync_method', 'CloudKit')}\n"
        status_text += f"iCloud同步: {'已启用' if status['enabled'] else '未启用'}\n"
        status_text += f"iCloud可用: {'是' if status['icloud_available'] else '否'}\n"
        status_text += f"容器ID: {status.get('container_id', 'N/A')}\n"
        status_text += f"上次同步: {status['last_sync_time'] or '从未同步'}\n"
        
        QMessageBox.information(self, "同步状态", status_text)
    
    def _handle_encryption_setup(self) -> bool:
        """
        处理加密设置和解锁
        
        Returns:
            是否成功设置/解锁
        """
        # 检查是否已设置密码
        if not self.encryption_manager.is_password_set():
            # 首次使用，设置密码
            dialog = SetupPasswordDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                password = dialog.get_password()
                success, message = self.encryption_manager.setup_password(password)
                
                if success:
                    QMessageBox.information(
                        self, "设置成功",
                        "密码设置成功！\n\n您的笔记将使用端到端加密保护。\n密码已保存到系统钥匙串，下次启动时可自动解锁。"
                    )
                    return True
                else:
                    QMessageBox.critical(self, "设置失败", message)
                    return False
            else:
                # 用户取消设置密码
                reply = QMessageBox.question(
                    self, "确认退出",
                    "未设置密码将无法使用笔记应用。\n\n确定要退出吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                return reply == QMessageBox.StandardButton.No
        else:
            # 尝试自动解锁
            if self.encryption_manager.try_auto_unlock():
                return True
                
            # 自动解锁失败，显示密码输入对话框（不限制输错次数）
            attempts = 0
            
            while True:
                dialog = UnlockDialog(self, allow_cancel=(attempts > 0))
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    password = dialog.get_password()
                    success, message = self.encryption_manager.verify_password(password)
                    
                    if success:
                        return True
                    
                    attempts += 1
                    QMessageBox.warning(
                        self, "密码错误",
                        message
                    )
                else:
                    # 用户取消/退出解锁
                    if hasattr(dialog, "should_exit") and dialog.should_exit():
                        from PyQt6.QtWidgets import QApplication
                        QApplication.quit()
                        return False
                    return False
            
    def change_password(self):
        """修改密码"""
        dialog = ChangePasswordDialog(self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            old_password, new_password = dialog.get_passwords()
            
            # 显示进度对话框
            progress = QMessageBox(self)
            progress.setWindowTitle("修改密码")
            progress.setText("正在修改密码，请稍候...")
            progress.setStandardButtons(QMessageBox.StandardButton.NoButton)
            progress.show()
            
            # 处理事件，显示对话框
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
            try:
                # 修改密码
                success, message = self.encryption_manager.change_password(old_password, new_password)
                
                if success:
                    # 重新加密所有笔记
                    count = self.note_manager.re_encrypt_all_notes()
                    
                    progress.close()
                    
                    QMessageBox.information(
                        self, "修改成功",
                        f"密码修改成功！\n\n已使用新密码重新加密{count}条笔记。"
                    )
                else:
                    progress.close()
                    QMessageBox.warning(self, "修改失败", message)
                    
            except Exception as e:
                progress.close()
                QMessageBox.critical(self, "修改失败", f"修改密码时发生错误：{e}")
                
    def lock_notes(self):
        """锁定笔记"""
        reply = QMessageBox.question(
            self, "确认锁定",
            "锁定后需要重新输入密码才能访问笔记。\n\n确定要锁定吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 保存当前笔记
            self.save_current_note()
            
            # 锁定加密管理器
            self.encryption_manager.lock()
            
            # 清空编辑器
            self.editor.clear()
            self._set_current_note_id(None)
            
            # 清空笔记列表
            self.note_list.clear()
            
            QMessageBox.information(self, "已锁定", "笔记已锁定，请重新启动应用并输入密码解锁。")
            
            # 退出应用
            self.close()
    
    def _get_settings(self):
        """获取设置（已废弃，保留用于兼容性）
        
        Returns:
            None: 现在使用数据库存储，不再返回QSettings对象
        """
        return None
    
    def _save_window_geometry(self):
        """保存窗口几何信息（位置和大小）"""
        try:
            import base64
            geo = self.saveGeometry()
            geo_str = base64.b64encode(geo).decode()
            self.note_manager.set_app_state("main_window/geometry", geo_str)
            
            state = self.saveState()
            state_str = base64.b64encode(state).decode()
            self.note_manager.set_app_state("main_window/state", state_str)
        except Exception:
            pass
    
    def _save_current_folder_state(self):
        """保存当前选中的文件夹状态"""
        try:
            current_folder_row = self.folder_list.currentRow()
            
            # 如果没有选中任何文件夹，清除保存的状态
            if current_folder_row < 0:
                self.note_manager.remove_app_state("last_folder_type")
                self.note_manager.remove_app_state("last_folder_value")
                return
            
            # 获取当前选中的文件夹项
            current_item = self.folder_list.item(current_folder_row)
            if not current_item:
                self.note_manager.remove_app_state("last_folder_type")
                self.note_manager.remove_app_state("last_folder_value")
                return
            
            # 获取文件夹数据并保存
            payload = current_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, tuple) and len(payload) == 2:
                folder_type, folder_value = payload
                self.note_manager.set_app_state("last_folder_type", folder_type)
                self.note_manager.set_app_state("last_folder_value", folder_value)
            else:
                self.note_manager.remove_app_state("last_folder_type")
                self.note_manager.remove_app_state("last_folder_value")
        except Exception:
            pass
    
    def _save_last_note_per_view(self):
        """保存所有视图的笔记映射到数据库"""
        try:
            import json
            if self._last_note_per_view:
                last_note_per_view_str = json.dumps(self._last_note_per_view)
                self.note_manager.set_app_state("last_note_per_view", last_note_per_view_str)
            else:
                self.note_manager.remove_app_state("last_note_per_view")
        except Exception as e:
            print(f"保存 last_note_per_view 失败: {e}")
    
    def _save_current_note_state(self):
        """保存所有视图的笔记状态"""
        self._save_last_note_per_view()
    
    def _cleanup_attachments_on_close(self):
        """关闭前的清理工作：清理附件垃圾箱"""
        # 清理当前笔记"已删除但可撤销"的附件
        try:
            if self._get_current_note_id() and getattr(self.note_manager, 'attachment_manager', None):
                self.note_manager.attachment_manager.cleanup_note_attachment_trash(self._get_current_note_id())
        except Exception:
            pass
    
    def _sync_before_close(self):
        """关闭前同步笔记（如果启用了同步）"""
        try:
            if self.sync_manager.sync_enabled:
                self.sync_manager.sync_notes()
        except Exception:
            pass
    
    def closeEvent(self, event):
        """关闭事件
        
        Args:
            event: QCloseEvent 关闭事件对象
        """
        logger.info(f"[closeEvent] 应用程序关闭，开始保存状态: current_note_id={self._get_current_note_id()}")
        
        # 1. 保存窗口状态
        self._save_window_geometry()
        
        # 2. 保存当前文件夹状态
        self._save_current_folder_state()
        
        # 3. 保存当前笔记和状态
        logger.info(f"[closeEvent] 保存当前笔记: note_id={self._get_current_note_id()}")
        self.save_current_note()  # 保存笔记内容和光标位置到数据库
        self._save_current_note_state()  # 保存笔记ID到数据库
        logger.info(f"[closeEvent] 当前笔记保存完成")
        
        # 4. 清理附件垃圾箱
        self._cleanup_attachments_on_close()
        
        # 5. 同步笔记（如果启用）
        self._sync_before_close()
        
        # 6. 关闭数据库连接
        try:
            self.note_manager.close()
        except Exception:
            pass
        
        # 7. 接受关闭事件
        event.accept()
