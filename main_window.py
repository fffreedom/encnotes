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

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QSettings
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QDesktopServices
from PyQt6.QtCore import QUrl

from note_editor import NoteEditor
from note_manager import NoteManager
from export_manager import ExportManager
from icloud_sync import CloudKitSyncManager
from password_dialog import UnlockDialog, SetupPasswordDialog, ChangePasswordDialog
import datetime


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
        # 判断是否在拖动笔记（如果是，则不显示蓝色线，只显示淡黄色背景）
        note_list = self.main_window.note_list
        folder_list = self
        
        # 关键修复：通过event.source()判断拖动源是哪个列表
        drag_source = event.source()
        is_dragging_note = False
        
        if drag_source == note_list:
            # 拖动源是笔记列表
            is_dragging_note = True
            note_current_item = note_list.currentItem()
            if not note_current_item:
                event.ignore()
                return
            note_data = note_current_item.data(Qt.ItemDataRole.UserRole)
            if not note_data:
                event.ignore()
                return
        elif drag_source == folder_list:
            # 拖动源是文件夹列表
            is_dragging_note = False
            folder_current_item = folder_list.currentItem()
            if not folder_current_item:
                event.ignore()
                return
            folder_data = folder_current_item.data(Qt.ItemDataRole.UserRole)
            if not (isinstance(folder_data, tuple) and len(folder_data) == 2 and folder_data[0] == "folder"):
                event.ignore()
                return
        else:
            # 拖动源不是笔记列表也不是文件夹列表
            event.ignore()
            return
        
        # 获取鼠标位置
        pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
        target_item = self.itemAt(pos)
        
        # 如果是拖动笔记，只需要简单的"拖到文件夹上"逻辑
        if is_dragging_note:
            if not target_item:
                # 拖到空白处
                self._drop_indicator_position = None
                self._drop_indicator_rect = None
                self._drop_target_item = None
                self.viewport().update()
                event.accept()
                return
            
            # 检查目标是否是文件夹
            target_data = target_item.data(Qt.ItemDataRole.UserRole)
            if not (isinstance(target_data, tuple) and len(target_data) == 2 and target_data[0] == "folder"):
                # 目标不是文件夹
                self._drop_indicator_position = None
                self._drop_indicator_rect = None
                self._drop_target_item = None
                self.viewport().update()
                event.ignore()
                return
            
            # 笔记只能拖到文件夹上，显示淡黄色背景
            item_rect = self.visualItemRect(target_item)
            self._drop_indicator_position = 'on'
            self._drop_indicator_rect = item_rect
            self._drop_target_item = target_item
            self.viewport().update()
            event.accept()
            return
        
        # 以下是文件夹拖动的智能位置检测逻辑
        # 策略：根据鼠标Y坐标，找到最近的文件夹，判断是插入到它之前、之后，还是作为它的子文件夹
        
        # 获取当前拖动的源文件夹
        src_item = self.currentItem()
        if not src_item:
            # 没有选中的源item
            self._drop_indicator_position = None
            self._drop_indicator_rect = None
            self._drop_target_item = None
            self.viewport().update()
            event.ignore()
            return
        
        src_data = src_item.data(Qt.ItemDataRole.UserRole)
        if not (isinstance(src_data, tuple) and len(src_data) == 2 and src_data[0] == "folder"):
            # 源不是文件夹
            self._drop_indicator_position = None
            self._drop_indicator_rect = None
            self._drop_target_item = None
            self.viewport().update()
            event.ignore()
            return
        
        src_folder_id = src_data[1]
        
        if not target_item:
            # 拖到空白处：找到最近的文件夹
            target_item = self._find_nearest_folder_item(pos.y())
            if not target_item:
                # 列表为空
                self._drop_indicator_position = None
                self._drop_indicator_rect = None
                self._drop_target_item = None
                self.viewport().update()
                event.accept()
                return
        
        # 检查目标是否是文件夹
        target_data = target_item.data(Qt.ItemDataRole.UserRole)
        if not (isinstance(target_data, tuple) and len(target_data) == 2 and target_data[0] == "folder"):
            # 目标不是文件夹
            self._drop_indicator_position = None
            self._drop_indicator_rect = None
            self._drop_target_item = None
            self.viewport().update()
            event.ignore()
            return
        
        target_folder_id = target_data[1]
        
        # 检查是否拖到自己身上
        if src_folder_id == target_folder_id:
            # 不能拖到自己身上
            self._drop_indicator_position = None
            self._drop_indicator_rect = None
            self._drop_target_item = None
            self.viewport().update()
            event.ignore()
            return
        
        # 检查是否拖到自己的子孙文件夹下（避免循环）
        if self.main_window.note_manager.is_ancestor_folder(src_folder_id, target_folder_id):
            # 不能拖到自己的子孙文件夹下
            self._drop_indicator_position = None
            self._drop_indicator_rect = None
            self._drop_target_item = None
            self.viewport().update()
            event.ignore()
            return
        
        # 获取目标item的矩形区域
        item_rect = self.visualItemRect(target_item)
        
        # 计算鼠标在item中的相对位置
        relative_y = pos.y() - item_rect.top()
        item_height = item_rect.height()
        
        # 三区域判断逻辑：
        # 1. 上方25%区域 -> 插入到目标之前（同级），显示蓝色线
        # 2. 中间50%区域 -> 作为目标的子文件夹，显示淡黄色背景
        # 3. 下方25%区域 -> 插入到目标之后（同级），显示蓝色线
        
        if relative_y < item_height * 0.25:
            # 上方25%：插入到目标之前（同级）
            self._drop_indicator_position = 'above'
            self._drop_indicator_rect = item_rect
            self._drop_target_item = target_item
        elif relative_y > item_height * 0.75:
            # 下方25%：插入到目标之后（同级）
            self._drop_indicator_position = 'below'
            self._drop_indicator_rect = item_rect
            self._drop_target_item = target_item
        else:
            # 中间50%：作为目标的子文件夹
            self._drop_indicator_position = 'on'
            self._drop_indicator_rect = item_rect
            self._drop_target_item = target_item
        
        self.viewport().update()
        event.accept()
    
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
    
    def dragLeaveEvent(self, event):
        """拖动离开时清除指示器"""
        self._drop_indicator_position = None
        self._drop_indicator_rect = None
        self._drop_target_item = None
        self.viewport().update()
        super().dragLeaveEvent(event)
    
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
    
    def dropEvent(self, event):
        """处理拖拽放下事件：支持文件夹拖拽和笔记拖拽"""
        try:
            import time
            t_start = time.time()
            
            # 1. 获取拖拽源数据
            mime_data = event.mimeData()
            if not mime_data.hasFormat("application/x-qabstractitemmodeldatalist"):
                super().dropEvent(event)
                return
            
            # 从当前选中项获取源数据
            # 需要判断是从文件夹列表拖动还是从笔记列表拖动
            note_list = self.main_window.note_list
            folder_list = self
            
            # 检查拖拽源是笔记还是文件夹
            # 关键修复：通过event.source()判断拖动源是哪个列表
            drag_source = event.source()
            is_note_drag = False
            src_note_id = None
            src_folder_id = None
            
            if drag_source == note_list:
                # 拖动源是笔记列表
                is_note_drag = True
                
                # 检查是否有多选笔记
                src_note_ids = []
                if hasattr(self.main_window, 'selected_note_rows') and self.main_window.selected_note_rows:
                    # 有多选笔记，获取所有选中的笔记ID
                    for row in self.main_window.selected_note_rows:
                        item = note_list.item(row)
                        if item:
                            note_id = item.data(Qt.ItemDataRole.UserRole)
                            if note_id:
                                src_note_ids.append(note_id)
                else:
                    # 没有多选，使用当前选中的笔记
                    note_current_item = note_list.currentItem()
                    if not note_current_item:
                        super().dropEvent(event)
                        return
                    note_data = note_current_item.data(Qt.ItemDataRole.UserRole)
                    if note_data:
                        src_note_ids = [note_data]
                    else:
                        super().dropEvent(event)
                        return
                
                if not src_note_ids:
                    super().dropEvent(event)
                    return
            elif drag_source == folder_list:
                # 拖动源是文件夹列表
                is_note_drag = False
                folder_current_item = folder_list.currentItem()
                if not folder_current_item:
                    super().dropEvent(event)
                    return
                src_data = folder_current_item.data(Qt.ItemDataRole.UserRole)
                if isinstance(src_data, tuple) and len(src_data) == 2 and src_data[0] == "folder":
                    src_folder_id = src_data[1]
                else:
                    super().dropEvent(event)
                    return
            else:
                # 拖动源不是笔记列表也不是文件夹列表
                super().dropEvent(event)
                return
            
            # 2. 获取目标位置
            drop_pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
            target_item = self.itemAt(drop_pos)
            
            # 3. 确定目标文件夹ID
            if target_item:
                # 拖到某个文件夹上
                target_data = target_item.data(Qt.ItemDataRole.UserRole)
                
                # 从 tuple 中提取实际的 folder_id
                if isinstance(target_data, tuple) and len(target_data) == 2 and target_data[0] == "folder":
                    target_folder_id = target_data[1]
                else:
                    # 拖到了非文件夹项（如标签、标题等）
                    event.ignore()
                    return
            else:
                # 拖到空白处
                target_folder_id = None
            
            t_before_db = time.time()
            
            # 4. 根据拖拽类型执行不同的操作
            if is_note_drag:
                # 处理笔记拖拽（支持多选）
                print(f"[性能-笔记拖拽] 准备阶段耗时: {(t_before_db - t_start)*1000:.2f}ms")
                print(f"[笔记拖拽] 移动 {len(src_note_ids)} 个笔记到文件夹: {target_folder_id}")
                
                # 批量更新笔记所属文件夹
                for note_id in src_note_ids:
                    self.main_window.note_manager.move_note_to_folder(note_id, target_folder_id)
                
                t_after_db = time.time()
                print(f"[性能-笔记拖拽] 数据库更新耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
                
                # 如果拖到某个文件夹下，自动展开目标文件夹及其所有祖先文件夹
                if target_folder_id:
                    t_before_expand = time.time()
                    self.main_window._folder_expanded[target_folder_id] = True
                    
                    current_folder_id = target_folder_id
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
                    t_after_expand = time.time()
                    print(f"[性能-笔记拖拽] 展开{ancestor_count}个祖先文件夹耗时: {(t_after_expand - t_before_expand)*1000:.2f}ms")
                
                # 延迟刷新UI
                def delayed_refresh_note():
                    t_refresh_start = time.time()
                    
                    try:
                        self.main_window.note_manager.conn.commit()
                        t_after_commit = time.time()
                        print(f"[性能-笔记拖拽] 数据库commit耗时: {(t_after_commit - t_refresh_start)*1000:.2f}ms")
                    except Exception:
                        pass
                    
                    t_before_load_folders = time.time()
                    self.main_window.load_folders()
                    t_after_load_folders = time.time()
                    print(f"[性能-笔记拖拽] load_folders()耗时: {(t_after_load_folders - t_before_load_folders)*1000:.2f}ms")
                    
                    t_before_load_notes = time.time()
                    self.main_window.load_notes()
                    t_after_load_notes = time.time()
                    print(f"[性能-笔记拖拽] load_notes()耗时: {(t_after_load_notes - t_before_load_notes)*1000:.2f}ms")
                    
                    t_before_ui_refresh = time.time()
                    note_list.viewport().update()
                    folder_list.viewport().update()
                    note_list.repaint()
                    folder_list.repaint()
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                    t_after_ui_refresh = time.time()
                    print(f"[性能-笔记拖拽] UI刷新耗时: {(t_after_ui_refresh - t_before_ui_refresh)*1000:.2f}ms")
                    
                    t_refresh_end = time.time()
                    print(f"[性能-笔记拖拽] delayed_refresh总耗时: {(t_refresh_end - t_refresh_start)*1000:.2f}ms")
                
                QTimer.singleShot(50, delayed_refresh_note)
                
                t_end = time.time()
                print(f"[性能-笔记拖拽] dropEvent总耗时(不含延迟): {(t_end - t_start)*1000:.2f}ms")
                
            else:
                # 处理文件夹拖拽
                print(f"[性能] 准备阶段耗时: {(t_before_db - t_start)*1000:.2f}ms")
                
                # 检查是否拖到自己上
                if target_folder_id == src_folder_id:
                    self._drop_indicator_position = None
                    self._drop_indicator_rect = None
                    self._drop_target_item = None
                    self.viewport().update()
                    event.ignore()
                    return
                
                # 根据拖放指示器位置决定操作类型
                if self._drop_indicator_position == 'on':
                    # 拖到文件夹上：改变父文件夹
                    self.main_window.note_manager.update_folder_parent(src_folder_id, target_folder_id)
                    t_after_db = time.time()
                    print(f"[性能] 数据库更新(改变父文件夹)耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
                    
                    # 自动展开目标父文件夹及其所有祖先文件夹
                    if target_folder_id:
                        t_before_expand = time.time()
                        self.main_window._folder_expanded[target_folder_id] = True
                        
                        current_folder_id = target_folder_id
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
                        t_after_expand = time.time()
                        print(f"[性能] 展开{ancestor_count}个祖先文件夹耗时: {(t_after_expand - t_before_expand)*1000:.2f}ms")
                
                elif self._drop_indicator_position in ('above', 'below'):
                    # 拖到文件夹之间：自动检测父文件夹并调整位置
                    # 策略：目标文件夹的父文件夹就是新位置的父文件夹
                    insert_before = (self._drop_indicator_position == 'above')
                    
                    # 获取目标文件夹的父文件夹ID
                    target_folder_info = self.main_window.note_manager.get_folder(target_folder_id)
                    if target_folder_info:
                        new_parent_id = target_folder_info.get('parent_folder_id')
                        
                        # 获取源文件夹的当前父文件夹ID
                        src_folder_info = self.main_window.note_manager.get_folder(src_folder_id)
                        current_parent_id = src_folder_info.get('parent_folder_id') if src_folder_info else None
                        
                        # 如果父文件夹不同，先改变父文件夹
                        if new_parent_id != current_parent_id:
                            self.main_window.note_manager.update_folder_parent(src_folder_id, new_parent_id)
                            print(f"[调试] 改变父文件夹: {current_parent_id} -> {new_parent_id}")
                        
                        # 调整顺序
                        success = self.main_window.note_manager.reorder_folder(src_folder_id, target_folder_id, insert_before)
                        t_after_db = time.time()
                        if success:
                            print(f"[性能] 数据库更新(调整位置)耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
                        else:
                            print(f"[性能] 调整位置失败: {(t_after_db - t_before_db)*1000:.2f}ms")
                        
                        # 如果新父文件夹存在，自动展开它及其祖先
                        if new_parent_id:
                            t_before_expand = time.time()
                            self.main_window._folder_expanded[new_parent_id] = True
                            
                            current_folder_id = new_parent_id
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
                            t_after_expand = time.time()
                            print(f"[性能] 展开{ancestor_count}个祖先文件夹耗时: {(t_after_expand - t_before_expand)*1000:.2f}ms")
                    else:
                        print(f"[错误] 无法获取目标文件夹信息: {target_folder_id}")
                        t_after_db = time.time()
                
                else:
                    # 拖到空白处：移到顶级
                    self.main_window.note_manager.update_folder_parent(src_folder_id, None)
                    t_after_db = time.time()
                    print(f"[性能] 数据库更新(移到顶级)耗时: {(t_after_db - t_before_db)*1000:.2f}ms")
                
                # 清除拖放指示器并立即更新视图
                self._drop_indicator_position = None
                self._drop_indicator_rect = None
                self._drop_target_item = None
                self.viewport().update()  # 立即触发重绘，清除蓝色线
                
                # 延迟刷新UI
                def delayed_refresh_folder():
                    t_refresh_start = time.time()
                    
                    try:
                        self.main_window.note_manager.conn.commit()
                        t_after_commit = time.time()
                        print(f"[性能] 数据库commit耗时: {(t_after_commit - t_refresh_start)*1000:.2f}ms")
                    except Exception:
                        pass
                    
                    t_before_load = time.time()
                    self.main_window.load_folders()
                    t_after_load = time.time()
                    print(f"[性能] load_folders()耗时: {(t_after_load - t_before_load)*1000:.2f}ms")
                    
                    t_before_ui_refresh = time.time()
                    self.viewport().update()
                    self.repaint()
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                    t_after_ui_refresh = time.time()
                    print(f"[性能] UI刷新耗时: {(t_after_ui_refresh - t_before_ui_refresh)*1000:.2f}ms")
                    
                    # 重新选中被拖动的文件夹
                    t_before_reselect = time.time()
                    found = False
                    for i in range(self.count()):
                        item = self.item(i)
                        if item:
                            item_data = item.data(Qt.ItemDataRole.UserRole)
                            if isinstance(item_data, tuple) and len(item_data) == 2 and item_data[0] == "folder":
                                if item_data[1] == src_folder_id:
                                    self.setCurrentItem(item)
                                    self.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)
                                    found = True
                                    t_after_reselect = time.time()
                                    print(f"[性能] 重新选中文件夹耗时: {(t_after_reselect - t_before_reselect)*1000:.2f}ms")
                                    break
                    
                    if not found:
                        print(f"[警告] 未找到被拖动的文件夹 {src_folder_id}")
                    
                    t_refresh_end = time.time()
                    print(f"[性能] delayed_refresh总耗时: {(t_refresh_end - t_refresh_start)*1000:.2f}ms")
                
                QTimer.singleShot(50, delayed_refresh_folder)
                
                t_end = time.time()
                print(f"[性能] dropEvent总耗时(不含延迟): {(t_end - t_start)*1000:.2f}ms")
            
            event.accept()
            
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

    def mousePressEvent(self, event):
        """处理鼠标按下事件，支持多选"""
        # 获取点击的item
        item = self.itemAt(event.pos())
        if not item:
            super().mousePressEvent(event)
            return
        
        # 检查是否是可选中的笔记项（排除分组标题等）
        if not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
            super().mousePressEvent(event)
            return
        
        clicked_row = self.row(item)
        modifiers = event.modifiers()
        
        # 只处理左键点击的多选逻辑，右键用于显示菜单
        if event.button() != Qt.MouseButton.LeftButton:
            # 不调用super()，直接返回，让Qt的事件系统继续传递到contextMenuEvent
            return
        
        # Command键：跳选（添加/移除单个项）
        if modifiers & Qt.KeyboardModifier.ControlModifier or modifiers & Qt.KeyboardModifier.MetaModifier:
            if self.main_window:
                self.main_window.toggle_note_selection(clicked_row)
            self.last_selected_row = clicked_row
            # 不要return，继续调用super()以支持拖动
        
        # Shift键：范围选择
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            if self.main_window and self.last_selected_row is not None:
                self.main_window.select_note_range(self.last_selected_row, clicked_row)
            # 不要return，继续调用super()以支持拖动
        
        # 普通点击：单选或保持多选（用于拖动）
        else:
            if self.main_window:
                # 如果点击的笔记已经在多选集合中，保持多选状态（用于拖动）
                if clicked_row in self.main_window.selected_note_rows:
                    # 记录点击信息，用于在mouseReleaseEvent中判断是否发生了拖动
                    self.press_pos = event.pos()
                    self.press_row = clicked_row
                    self.was_in_multi_select = len(self.main_window.selected_note_rows) > 1
                    
                    # 保持多选状态，但需要设置currentItem以支持拖动
                    self.blockSignals(True)
                    self.setCurrentRow(clicked_row)
                    self.blockSignals(False)
                    # 强制刷新视觉选中状态，确保所有选中项都正确显示
                    self.main_window._update_visual_selection()
                else:
                    # 点击的是未选中的笔记，执行单选
                    self.main_window.select_single_note(clicked_row)
            self.last_selected_row = clicked_row
        
        # 调用父类方法以支持拖动功能
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件，如果是点击而非拖动，则取消多选状态"""
        # 日志：记录鼠标释放事件
        button_name = "Left" if event.button() == Qt.MouseButton.LeftButton else "Right" if event.button() == Qt.MouseButton.RightButton else "Other"
        print(f"[mouseReleaseEvent] Button: {button_name}, press_pos: {self.press_pos}, was_in_multi_select: {self.was_in_multi_select}")
        
        # 只处理左键释放事件，右键用于显示菜单，不应该影响选中状态
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否记录了按下位置（说明是在多选状态下点击的）
            if self.press_pos is not None and self.was_in_multi_select:
                # 计算鼠标移动距离
                move_distance = (event.pos() - self.press_pos).manhattanLength()
                print(f"[mouseReleaseEvent] Move distance: {move_distance}")
                
                # 如果移动距离很小（小于5像素），认为是点击而非拖动
                if move_distance < 5:
                    # 取消多选状态，只选中当前点击的笔记
                    if self.main_window and self.press_row is not None:
                        print(f"[mouseReleaseEvent] Canceling multi-select, selecting single note: {self.press_row}")
                        self.main_window.select_single_note(self.press_row)
            
            # 清除记录的点击信息
            self.press_pos = None
            self.press_row = None
            self.was_in_multi_select = False
        
        # 调用父类方法
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """处理右键菜单事件（融合单选和多选功能）"""
        if not self.main_window:
            return
        
        # 获取点击位置的笔记
        item = self.itemAt(event.pos())
        if not item:
            # 点击在空白区域，只显示"新建笔记"
            menu = QMenu(self)
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(lambda: self.main_window.create_note_in_current_folder())
            if self.main_window.current_folder_id is None or self.main_window.is_viewing_deleted:
                new_note_action.setEnabled(False)
            menu.addAction(new_note_action)
            menu.exec(event.globalPos())
            return
        
        clicked_row = self.row(item)
        note_id = item.data(Qt.ItemDataRole.UserRole)
        
        # 如果点击的笔记不在选中集合中，则只选中当前笔记
        if clicked_row not in self.main_window.selected_note_rows:
            self.main_window.select_single_note(clicked_row)
        else:
            pass
        
        # 获取所有选中的笔记ID
        selected_note_ids = []
        for row in sorted(self.main_window.selected_note_rows):
            item = self.item(row)
            if item:
                selected_note_ids.append(item.data(Qt.ItemDataRole.UserRole))
        
        print(f"[contextMenuEvent] Final selected note IDs: {selected_note_ids}, count: {len(selected_note_ids)}")
        
        if not selected_note_ids:
            return
        
        is_single_note = len(selected_note_ids) == 1
        
        # 创建右键菜单
        menu = QMenu(self)
        
        # 1. 新建笔记（在"所有笔记"和"最近删除"视图中禁用）
        new_note_action = QAction("新建笔记", self)
        new_note_action.triggered.connect(lambda: self.main_window.create_new_note())
        if self.main_window.current_folder_id is None or self.main_window.is_viewing_deleted:
            new_note_action.setEnabled(False)
        menu.addAction(new_note_action)
        
        menu.addSeparator()
        
        # 2. 移到文件夹（使用树形结构）
        move_menu = menu.addMenu("移到")
        self._populate_move_to_menu(move_menu, selected_note_ids)
        
        menu.addSeparator()
        
        # 3. 置顶/取消置顶
        all_pinned = all(self.main_window.note_manager.is_note_pinned(nid) for nid in selected_note_ids)
        pin_text = "取消置顶" if all_pinned else "置顶"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(lambda: self.main_window.batch_toggle_pin_notes(selected_note_ids))
        menu.addAction(pin_action)
        
        menu.addSeparator()
        
        # 4. 标签
        tag_menu = menu.addMenu("标签")
        all_tags = self.main_window.note_manager.get_all_tags()
        if all_tags:
            # 获取第一个笔记的标签（用于显示对勾）
            first_note_tags = self.main_window.note_manager.get_note_tags(selected_note_ids[0])
            first_note_tag_ids = {t['id'] for t in first_note_tags}
            
            for tag in all_tags:
                tag_id = tag['id']
                tag_name = tag['name']
                
                # 检查是否已添加标签（显示对勾）
                has_tag = tag_id in first_note_tag_ids
                display_name = f"✓ {tag_name}" if has_tag else tag_name
                
                action = QAction(display_name, self)
                action.triggered.connect(lambda checked, tid=tag_id, tname=tag_name, has=has_tag: 
                                       self.main_window.toggle_tag_for_notes(selected_note_ids, tid, tname, has))
                tag_menu.addAction(action)
        else:
            no_tags_action = QAction("(无标签)", self)
            no_tags_action.setEnabled(False)
            tag_menu.addAction(no_tags_action)
        
        menu.addSeparator()
        
        # 5. 删除笔记
        delete_text = f"删除笔记 ({len(selected_note_ids)}个)" if len(selected_note_ids) > 1 else "删除笔记"
        delete_action = QAction(delete_text, self)
        delete_action.triggered.connect(lambda: self.main_window.batch_delete_notes(selected_note_ids))
        menu.addAction(delete_action)
        
        # 显示菜单
        menu.exec(event.globalPos())
    
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
        """根据当前上下文启用/禁用“新建笔记”动作。"""
        enabled = bool(self.current_folder_id) and (not self._current_folder_has_empty_new_note())

        for attr in ("new_note_action_toolbar", "new_note_action_menu"):
            act = getattr(self, attr, None)
            if act is not None:
                act.setEnabled(enabled)

    def eventFilter(self, obj, event):
        # 文件夹重命名：ESC 取消（就地编辑）
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

        # 空文件夹：点击编辑器自动新建笔记
        try:
            from PyQt6.QtCore import QEvent
            from PyQt6.QtCore import Qt
            if (
                getattr(self, "_editor_click_to_create_note_enabled", False)
                and obj is getattr(getattr(self.editor, "text_edit", None), "viewport", lambda: None)()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton

            ):
                # 只有"选中了某个自定义文件夹 + 当前没有选中笔记 + 当前不在标签视图"才自动创建
                if self.current_folder_id and self.current_note_id is None and self.current_tag_id is None:
                    self.create_note_in_folder(self.current_folder_id, default_title="新笔记")
                    event.accept()
                    return True
        except Exception:
            pass

        # 空标签：点击编辑器时阻止进入可编辑状态
        try:
            from PyQt6.QtCore import QEvent
            from PyQt6.QtCore import Qt
            # 检查是否点击了编辑器（viewport或text_edit本身）
            is_editor_click = (
                obj is getattr(getattr(self.editor, "text_edit", None), "viewport", lambda: None)()
                or obj is getattr(self.editor, "text_edit", None)
            )
            if (
                is_editor_click
                and event.type() == QEvent.Type.MouseButtonPress
                and self.current_tag_id is not None
                and self.current_note_id is None
            ):
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

        return super().eventFilter(obj, event)

    
    def __init__(self):
        super().__init__()
        self.note_manager = NoteManager()

        self.export_manager = ExportManager()
        self.sync_manager = CloudKitSyncManager(self.note_manager)
        self.current_note_id = None
        self.current_folder_id = None  # 当前选中的文件夹ID
        self.current_tag_id = None  # 当前选中的标签ID
        self.is_viewing_deleted = False  # 是否正在查看最近删除
        self.custom_folders = []  # 自定义文件夹列表
        self.tags = []  # 标签列表
        
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
        self.load_folders()  # 加载文件夹
        self.load_notes()


        
        # 恢复上次打开的笔记和光标位置
        self._restore_last_note()

        
        # 设置自动同步定时器（每5分钟）
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.auto_sync)
        self.sync_timer.start(300000)  # 5分钟
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("加密笔记")

        # 窗口大小/位置持久化：若用户曾调整过窗口大小，则下次启动按上次值恢复。
        # 若没有历史记录（首次启动），默认最大化。
        self._settings = QSettings("encnotes", "encnotes")
        restored = False
        try:
            geo = self._settings.value("main_window/geometry")
            if geo is not None:
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
            st = self._settings.value("main_window/state")
            if st is not None:
                self.restoreState(st)
        except Exception:
            pass

        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e6e6e6;
            }
        """)
        
        # 左侧：文件夹列表

        self.folder_list = FolderListWidget()
        self.folder_list.main_window = self  # 设置主窗口引用
        # 左侧文件夹栏：设置一个更合理的默认/最小宽度；真正的初始宽度由 QSplitter 的 sizes 决定
        self.folder_list.setMaximumWidth(500)
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_list.setTextElideMode(Qt.TextElideMode.ElideRight)

        # 文件夹拖拽：允许把一个文件夹拖到另一个文件夹上，作为其子文件夹
        self.folder_list.setDragEnabled(True)
        self.folder_list.setAcceptDrops(True)
        self.folder_list.setDropIndicatorShown(True)
        try:
            from PyQt6.QtWidgets import QAbstractItemView
            # 注意：不要用 InternalMove。InternalMove 会执行“列表内重排”，看起来只改变位置不改变层级。
            # 我们把 Drop 交给 eventFilter 处理：写入 ZPARENTFOLDERID 后再 load_folders() 重新渲染层级树。
            self.folder_list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        except Exception:
            pass
        self.folder_list.setDefaultDropAction(Qt.DropAction.MoveAction)

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

        self.folder_list.setCurrentRow(0)
        self.folder_list.currentRowChanged.connect(self.on_folder_changed)
        self.folder_list.itemDoubleClicked.connect(self.on_folder_item_double_clicked)
        self.folder_list.itemClicked.connect(self.on_folder_item_clicked)

        # 让 MainWindow.eventFilter 能收到 folder_list 的 Drop 事件
        try:
            self.folder_list.installEventFilter(self)
        except Exception:
            pass

        # 允许“选中后再次单击”进入重命名（仿Finder）
        self.folder_list.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)
        self._last_folder_click_folder_id = None
        self._last_folder_click_ms = 0

        
        # 为文件夹列表添加右键菜单
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self.show_folder_context_menu)

        # 文件夹列表滚动条：默认不显示；用户滚动/拖动时临时浮动显示；停止交互一段时间后自动隐藏
        self.folder_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._folder_scrollbar_hide_timer = QTimer(self)
        self._folder_scrollbar_hide_timer.setSingleShot(True)
        self._folder_scrollbar_hide_timer.timeout.connect(self._hide_folder_scrollbar)

        self._folder_scrollbar_dragging = False
        folder_sb = self.folder_list.verticalScrollBar()
        folder_sb.valueChanged.connect(self._show_folder_scrollbar_temporarily)
        folder_sb.sliderPressed.connect(self._on_folder_scrollbar_pressed)
        folder_sb.sliderReleased.connect(self._on_folder_scrollbar_released)
        
        # 中间：笔记列表
        self.note_list = NoteListWidget()
        self.note_list.main_window = self  # 设置主窗口引用

        # 启用笔记拖拽功能：只允许拖出到文件夹列表，不接受拖入
        self.note_list.setDragEnabled(True)
        self.note_list.setAcceptDrops(False)  # 笔记列表不接受拖入
        self.note_list.setDropIndicatorShown(False)
        self.note_list.setDragDropMode(QListWidget.DragDropMode.DragOnly)  # 只允许拖出
        
        self.note_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 笔记列表滚动条：默认不显示；用户滚动/拖动时临时浮动显示；停止交互一段时间后自动隐藏
        self.note_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._note_scrollbar_hide_timer = QTimer(self)
        self._note_scrollbar_hide_timer.setSingleShot(True)
        self._note_scrollbar_hide_timer.timeout.connect(self._hide_note_scrollbar)

        self._note_scrollbar_dragging = False
        sb = self.note_list.verticalScrollBar()
        sb.valueChanged.connect(self._show_note_scrollbar_temporarily)
        sb.sliderPressed.connect(self._on_note_scrollbar_pressed)
        sb.sliderReleased.connect(self._on_note_scrollbar_released)

        # 右键菜单由NoteListWidget的contextMenuEvent处理
        self.note_list.setMaximumWidth(500)
        self.note_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 去掉焦点边框
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

        self.note_list.currentItemChanged.connect(self.on_note_selected)
        
        # 右侧：编辑器
        self.editor = NoteEditor(self.note_manager)
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

        
        # 添加到分割器
        splitter.addWidget(self.folder_list)
        splitter.addWidget(self.note_list)
        splitter.addWidget(self.editor)
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 5)

        # 设置分割器启动时初始宽度，文件夹列表和笔记列表最大宽度由各自的setMaximumWidth设置，最小宽度不设置
        # 这里把左侧文件夹栏稍微加宽，避免“新建文件夹”等默认名称显示不全
        splitter.setSizes([200, 200, 900])
        
        main_layout.addWidget(splitter)
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建菜单栏
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
            print(f"解析时间失败: {e}")
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

    
    def load_notes(self, select_note_id=None):
        """加载笔记列表
        
        Args:
            select_note_id: 要选中的笔记ID，如果为None则选中第一个笔记
        """
        # 清除多选状态
        self.selected_note_rows.clear()
        if hasattr(self, 'note_list') and self.note_list:
            self.note_list.last_selected_row = None
        
        # 手动删除所有自定义widget，避免重叠
        # 必须在clear()之前删除所有widget
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
        
        # 根据当前选中的文件夹/标签加载笔记
        current_row = self.folder_list.currentRow()
        
        # 计算实际的索引（考虑不可选中的标题项）
        # 索引布局：
        # 0: iCloud标题（不可选）
        # 1: 所有笔记
        # 2~(2+n-1): 自定义文件夹
        # (2+n): 最近删除
        # (2+n+1): 标签标题（不可选）
        # (2+n+2)~: 标签
        
        folder_count = len(self.custom_folders)
        deleted_row = 2 + folder_count
        tag_header_row = deleted_row + 1
        first_tag_row = tag_header_row + 1
        
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
            folder_index = current_row - 2
            if 0 <= folder_index < len(self.custom_folders):
                folder_id = self.custom_folders[folder_index]['id']
                notes = self.note_manager.get_notes_by_folder(folder_id)
                self.current_folder_id = folder_id
                self.current_tag_id = None
                self.is_viewing_deleted = False
            else:
                notes = []
        elif current_row >= first_tag_row:  # 标签
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

                    self.current_note_id = None
                    self.editor.current_note_id = None
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
        else:
            notes = []
        
        # 将笔记分为置顶和普通笔记
        pinned_notes = []
        normal_notes = []
        
        for note in notes:
            if self.note_manager.is_note_pinned(note['id']):
                pinned_notes.append(note)
            else:
                normal_notes.append(note)
        
        # 按时间分组普通笔记
        time_groups = {}
        for note in normal_notes:
            group_name = self._get_time_group(note['created_at'])
            if group_name not in time_groups:
                time_groups[group_name] = []
            time_groups[group_name].append(note)
        
        # 定义分组顺序
        group_order = ["今天", "昨天", "过去一周", "过去30天"]
        
        # 添加年份分组（按年份降序）
        year_groups = sorted([g for g in time_groups.keys() if g.endswith("年")], reverse=True)
        group_order.extend(year_groups)
        
        # 添加"其他"分组
        if "其他" in time_groups:
            group_order.append("其他")
        
        # 显示置顶笔记
        if pinned_notes:
            self._add_group_header("置顶")
            for idx, note in enumerate(pinned_notes):
                self._add_note_item(note)

                # 分组的第一条笔记：关闭其“顶部线”，避免与分组标题下面的分隔线重复
                if idx == 0:
                    try:
                        it = self.note_list.item(self.note_list.count() - 1)
                        if it and (it.flags() & Qt.ItemFlag.ItemIsSelectable):
                            it.setData(Qt.ItemDataRole.UserRole + 1, False)
                    except Exception:
                        pass
        
        # 显示按时间分组的普通笔记
        for group_name in group_order:
            if group_name in time_groups and time_groups[group_name]:
                group_notes = time_groups[group_name]
                self._add_group_header(group_name)
                for idx, note in enumerate(group_notes):
                    self._add_note_item(note)

                    # 分组的第一条笔记：关闭其“顶部线”，避免与分组标题下面的分隔线重复
                    if idx == 0:
                        try:
                            it = self.note_list.item(self.note_list.count() - 1)
                            if it and (it.flags() & Qt.ItemFlag.ItemIsSelectable):
                                it.setData(Qt.ItemDataRole.UserRole + 1, False)
                        except Exception:
                            pass

        
        if notes:
            # 现在分隔线画在 item 的顶部边缘，因此“最后一条笔记”也应该保留顶部线（无需关闭）。
            pass

            # 触发重绘（应用分隔线状态变化）
            self.note_list.viewport().update()

            
            # 如果指定了要选中的笔记ID，尝试选中它
            note_selected = False
            if select_note_id:
                for i in range(self.note_list.count()):
                    item = self.note_list.item(i)
                    if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                        if item.data(Qt.ItemDataRole.UserRole) == select_note_id:
                            self.note_list.setCurrentRow(i)
                            self.note_list.last_selected_row = i  # 设置last_selected_row以支持Shift多选
                            self.selected_note_rows.add(i)  # 添加到多选集合，支持Command键多选
                            note_selected = True
                            break
            
            # 如果没有指定笔记ID或指定的笔记不存在，选中第一个可选中的笔记项
            if not note_selected:
                for i in range(self.note_list.count()):
                    item = self.note_list.item(i)
                    if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                        self.note_list.setCurrentRow(i)
                        self.note_list.last_selected_row = i  # 设置last_selected_row以支持Shift多选
                        self.selected_note_rows.add(i)  # 添加到多选集合，支持Command键多选
                        break
        else:
            # 空列表：保持编辑器“不可编辑/无光标闪烁”的观感
            self.current_note_id = None
            self.editor.current_note_id = None
            self.editor.clear()
            try:
                self.editor.text_edit.clearFocus()
            except Exception:
                pass

        # 根据当前文件夹是否已有“空的新笔记草稿”刷新菜单可用状态
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

            
    def load_folders(self):
        """加载文件夹列表（新布局：iCloud分组，支持多级文件夹）"""
        # 保存当前选中的行
        current_row = self.folder_list.currentRow()
        
        # 清空列表
        self.folder_list.clear()
        
        # 添加iCloud标题（不可选中）：与“🏷️ 标签”等普通文本项的图标起始位置对齐
        icloud_header = QListWidgetItem()
        icloud_header.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        # 使用与QListWidget默认item padding一致的左边距，让图标起始位置与“🏷️ 标签”对齐
        header_layout.setContentsMargins(0, 0, 10, 0)

        header_layout.setSpacing(6)

        header_label = ElidedLabel("☁️ iCloud")
        header_label.setFullText("☁️ iCloud")
        header_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #000000;
            background: transparent;
        """)
        header_layout.addWidget(header_label, 1)

        header_widget.setFixedHeight(28)
        icloud_header.setSizeHint(QSize(200, 28))

        self.folder_list.addItem(icloud_header)
        self.folder_list.setItemWidget(icloud_header, header_widget)

        
        # 预计算：系统项计数 + folder_id -> 笔记数量（不含已删除）
        # 使用一次SQL聚合，避免逐个文件夹调用 get_notes_by_folder 造成卡顿
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

        # 添加系统文件夹（使用与自定义文件夹一致的布局，保证左侧文字对齐）
        self._add_system_folder_item("all_notes", "📝 所有笔记")
        
        # 加载自定义文件夹（支持层级显示）
        all_folders = self.note_manager.get_all_folders()
        
        # 构建文件夹树结构
        self.custom_folders = []
        self._add_folders_recursive(all_folders, None, 1, self.custom_folders)

        
        # 添加最近删除（使用一致布局）
        self._add_system_folder_item("deleted", "🗑️ 最近删除")

        
        # 添加标签标题（不可选中）：与iCloud标题保持一致的样式
        tag_header = QListWidgetItem()
        tag_header.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中
        tag_header.setData(Qt.ItemDataRole.UserRole, ("tag_header", None))  # 标记为标签标题

        tag_header_widget = QWidget()
        tag_header_layout = QHBoxLayout(tag_header_widget)
        tag_header_layout.setContentsMargins(0, 0, 10, 0)
        tag_header_layout.setSpacing(6)

        tag_header_label = ElidedLabel("🏷️ 标签")
        tag_header_label.setFullText("🏷️ 标签")
        tag_header_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            color: #000000;
            background: transparent;
        """)
        tag_header_layout.addWidget(tag_header_label, 1)

        tag_header_widget.setFixedHeight(28)
        tag_header.setSizeHint(QSize(200, 28))

        self.folder_list.addItem(tag_header)
        self.folder_list.setItemWidget(tag_header, tag_header_widget)
        
        # 加载标签（缩进显示）
        self.tags = self.note_manager.get_all_tags()
        for tag in self.tags:
            raw_name = str(tag.get('name', '') or '')
            tag_name = raw_name.strip()
            count = self.note_manager.get_tag_count(tag['id'])

            is_empty_tag = (tag_name == "")
            display_name = tag_name if not is_empty_tag else "（未命名标签）"
            item_text = f"    🏷️ {display_name} ({count})"

            tag_item = QListWidgetItem()
            tag_item.setData(Qt.ItemDataRole.UserRole, ("tag", tag['id']))  # 标记为标签项

            # 为标签项创建自定义widget以支持高亮显示
            tag_widget = QWidget()
            tag_widget.setObjectName("folder_row_widget")  # 使用相同的样式
            tag_layout = QHBoxLayout(tag_widget)
            tag_layout.setContentsMargins(0, 0, 0, 0)
            tag_layout.setSpacing(0)

            tag_label = QLabel(item_text)
            if is_empty_tag:
                tag_label.setStyleSheet("background: transparent; padding: 8px 10px; font-size: 13px; color: #8e8e93;")
            else:
                tag_label.setStyleSheet("background: transparent; padding: 8px 10px; font-size: 13px;")
            tag_layout.addWidget(tag_label)

            # 如果当前选中的是这个标签，设置高亮
            if self.current_tag_id == tag['id']:
                tag_widget.setProperty("selected", True)
                tag_item.setSelected(True)
            else:
                tag_widget.setProperty("selected", False)

            self.folder_list.addItem(tag_item)
            self.folder_list.setItemWidget(tag_item, tag_widget)
            tag_item.setSizeHint(QSize(200, 40))  # 增加高度到40px，确保显示完整
        
        # 恢复选中状态
        if current_row >= 0 and current_row < self.folder_list.count():
            item = self.folder_list.item(current_row)
            if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                self.folder_list.setCurrentRow(current_row)
            else:
                self.folder_list.setCurrentRow(1)  # 默认选中"所有笔记"
        else:
            self.folder_list.setCurrentRow(1)  # 默认选中"所有笔记"
        
        # 强制刷新UI
        self.folder_list.viewport().update()
        self.folder_list.update()
        self.folder_list.repaint()
    
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
            self._update_new_note_action_enabled()
            return

        # 防御：如果已存在空草稿，直接打开那个草稿
        has_empty_note = self._current_folder_has_empty_new_note()
        
        if has_empty_note:
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
                        self._update_new_note_action_enabled()
                        return
            except Exception as e:
                pass
            self._update_new_note_action_enabled()
            return

        note_id = self.note_manager.create_note(title="新笔记", folder_id=folder_id)
        
        try:
            # 确保标题落库（兼容未来 create_note 默认值变化）
            self.note_manager.update_note(note_id, title="新笔记")
        except Exception as e:
            pass

        # 刷新笔记列表
        self.load_notes()

        # 同步刷新左侧文件夹计数（load_notes 不会重建 folder_list）
        selected_row = self.folder_list.currentRow()
        self.load_folders()
        try:
            if selected_row is not None and 0 <= selected_row < self.folder_list.count():
                self.folder_list.setCurrentRow(selected_row)
        except Exception as e:
            pass

        # 选中新创建的笔记
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentItem(item)
                break

        # 设置焦点到编辑器，让光标闪烁
        self.editor.text_edit.setFocus()

        # 刷新可用状态
        self._update_new_note_action_enabled()

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

        self._update_new_note_action_enabled()

    
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
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这 {count} 条笔记吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for note_id in note_ids:
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
            if self.current_note_id in note_ids:
                self.current_note_id = None
                self.editor.clear()
            
            self.statusBar().showMessage(f"已删除 {count} 条笔记", 2000)
    
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
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这条笔记吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
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
            if note_id == self.current_note_id:
                self.current_note_id = None
                self.editor.clear()
    
    def delete_note(self):
        """删除当前笔记（保留用于快捷键）"""
        if self.current_note_id is None:
            return
        
        self.delete_note_by_id(self.current_note_id)
            
    def on_folder_changed(self, index):
        """文件夹切换"""
        # 选中高亮由 `folder_row_widget` 自己绘制（避免与就地编辑的白色输入框冲突）
        def _set_row_widget_selected(row_widget: QWidget | None, selected: bool):
            if not row_widget:
                return
            if row_widget.objectName() != "folder_row_widget":
                return
            row_widget.setProperty("selected", selected)
            row_widget.style().unpolish(row_widget)
            row_widget.style().polish(row_widget)
            row_widget.update()

        def _find_folder_row_widget_by_id(folder_id: str):
            if not folder_id:
                return None
            for i in range(self.folder_list.count()):
                it = self.folder_list.item(i)
                if not it:
                    continue
                payload = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder" and payload[1] == folder_id:
                    return self.folder_list.itemWidget(it)
            return None

        def _find_tag_row_widget_by_id(tag_id: str):
            if not tag_id:
                return None
            for i in range(self.folder_list.count()):
                it = self.folder_list.item(i)
                if not it:
                    continue
                payload = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "tag" and payload[1] == tag_id:
                    return self.folder_list.itemWidget(it)
            return None

        try:
            # 获取当前选中项的类型
            cur_item_type = None
            cur_folder_id = None
            cur_system_key = None
            cur_tag_id = None
            
            if index is not None and 0 <= index < self.folder_list.count():
                cur_item = self.folder_list.item(index)
                payload = cur_item.data(Qt.ItemDataRole.UserRole) if cur_item else None

                if isinstance(payload, tuple) and len(payload) == 2:
                    cur_item_type = payload[0]
                    if payload[0] == "folder":
                        cur_folder_id = payload[1]
                    elif payload[0] == "system":
                        cur_system_key = payload[1]
                    elif payload[0] == "tag":
                        cur_tag_id = payload[1]
            
            # 如果选中的是标签，保持文件夹的选中状态
            if cur_item_type == "tag":
                # 取消之前选中标签的高亮
                prev_tag_id = getattr(self, "_prev_selected_tag_id", None)
                if prev_tag_id:
                    prev_tag_w = _find_tag_row_widget_by_id(prev_tag_id)
                    _set_row_widget_selected(prev_tag_w, False)
                
                # 设置当前标签高亮
                cur_tag_w = self.folder_list.itemWidget(cur_item) if cur_item else None
                _set_row_widget_selected(cur_tag_w, True)
                
                # 记录当前选中的标签
                self.current_tag_id = cur_tag_id
                self._prev_selected_tag_id = cur_tag_id
                # 不取消文件夹的高亮，保持双选中状态
            else:
                # 选中的是文件夹或系统项，取消之前的标签高亮
                prev_tag_id = getattr(self, "_prev_selected_tag_id", None)
                if prev_tag_id:
                    prev_tag_w = _find_tag_row_widget_by_id(prev_tag_id)
                    _set_row_widget_selected(prev_tag_w, False)
                    self._prev_selected_tag_id = None
                
                # 取消之前的文件夹/系统项高亮
                prev_folder_id = getattr(self, "_prev_selected_folder_id", None)
                prev_system_key = getattr(self, "_prev_selected_system_key", None)

                prev_w = None
                if prev_folder_id:
                    prev_w = _find_folder_row_widget_by_id(prev_folder_id)
                elif prev_system_key:
                    # system item: 通过 key 定位
                    for i in range(self.folder_list.count()):
                        it = self.folder_list.item(i)
                        if not it:
                            continue
                        payload = it.data(Qt.ItemDataRole.UserRole)
                        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "system" and payload[1] == prev_system_key:
                            prev_w = self.folder_list.itemWidget(it)
                            break

                _set_row_widget_selected(prev_w, False)

                # 设置当前行选中
                cur_w = self.folder_list.itemWidget(cur_item) if cur_item else None
                _set_row_widget_selected(cur_w, True)

                # 记录"上一次选中"的语义ID（而不是 row）
                self._prev_selected_folder_id = cur_folder_id
                self._prev_selected_system_key = cur_system_key
                # 清除标签选中状态
                self.current_tag_id = None
        except Exception:
            pass

        self.load_notes()

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

        
    def on_note_selected(self, current, previous):
        """笔记选中事件"""
        
        # 让选中背景由条目widget自身绘制（避免QListWidget默认选中背景出现上下错位）
        def _set_item_widget_selected(item, selected: bool):
            if not item:
                return
            w = self.note_list.itemWidget(item)
            if not w:
                return

            # itemWidget 现在就是 `note_item_widget` 本身
            if w.objectName() != "note_item_widget":
                return

            w.setProperty("selected", selected)
            # 触发QSS重新应用
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()

        if previous:
            _set_item_widget_selected(previous, False)
            # 保存之前的笔记
            prev_note_id = self.current_note_id
            self.save_current_note()

            # 切换笔记时：清理“已删除但可撤销”的附件（此时用户已离开该笔记）
            try:
                if prev_note_id and getattr(self.note_manager, 'attachment_manager', None):
                    self.note_manager.attachment_manager.cleanup_note_attachment_trash(prev_note_id)
            except Exception:
                pass
            
        if current:
            _set_item_widget_selected(current, True)
            note_id = current.data(Qt.ItemDataRole.UserRole)
            self.current_note_id = note_id
            self.editor.current_note_id = note_id  # 设置编辑器的当前笔记ID
            note = self.note_manager.get_note(note_id)
            
            if note:
                self.editor.blockSignals(True)
                self.editor.setHtml(note['content'])
                self.editor.blockSignals(False)
                
                # 手动调用 auto_format_first_line 确保第一行格式正确
                # 因为 blockSignals 阻止了 textChanged 信号，所以需要手动调用
                self.editor.auto_format_first_line()
                
                # 将光标移动到第一行（标题）的末尾，并设置标题格式
                from PyQt6.QtGui import QTextCursor, QFont, QTextCharFormat
                cursor = self.editor.text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)  # 移动到文档开始
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)  # 移动到第一行末尾
                
                # 在应用光标之前，先设置光标的字符格式
                # 这样光标的视觉高度就会正确
                title_fmt = QTextCharFormat()
                title_fmt.setFontPointSize(28)
                title_fmt.setFontWeight(QFont.Weight.Bold)
                cursor.setCharFormat(title_fmt)
                
                # 应用光标
                self.editor.text_edit.setTextCursor(cursor)
                
                # 设置焦点到编辑器，让光标闪烁
                self.editor.text_edit.setFocus()
        else:
            self.current_note_id = None
            self.editor.current_note_id = None
            self.editor.clear()
            try:
                self.editor.text_edit.clearFocus()
            except Exception:
                pass

        # 选中变化后刷新"新建笔记"可用状态
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
            # 保存之前的笔记
            if self.current_note_id:
                self.save_current_note()
            
            # 阻止信号，避免触发on_note_selected
            self.note_list.blockSignals(True)
            self.note_list.setCurrentItem(item)
            self.note_list.blockSignals(False)
            
            # 加载新笔记
            note_id = item.data(Qt.ItemDataRole.UserRole)
            self.current_note_id = note_id
            self.editor.current_note_id = note_id
            note = self.note_manager.get_note(note_id)
            
            if note:
                self.editor.blockSignals(True)
                self.editor.setHtml(note['content'])
                self.editor.blockSignals(False)
                
                # 将光标移动到第一行（标题）的末尾
                from PyQt6.QtGui import QTextCursor
                cursor = self.editor.text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                self.editor.text_edit.setTextCursor(cursor)
                
                # 设置焦点到编辑器
                self.editor.text_edit.setFocus()
            
            # 刷新"新建笔记"可用状态
            self._update_new_note_action_enabled()
    
    def toggle_note_selection(self, row):
        """切换笔记的选中状态（Command键跳选）"""
        if row in self.selected_note_rows:
            # 如果已选中，则取消选中
            self.selected_note_rows.discard(row)
            if not self.selected_note_rows:
                # 如果没有选中项了，清空编辑器
                self.current_note_id = None
                self.editor.current_note_id = None
                self.editor.clear()
        else:
            # 如果未选中，则添加到选中集合
            self.selected_note_rows.add(row)
            # 将最后选中的项设为当前项
            item = self.note_list.item(row)
            if item:
                self.note_list.blockSignals(True)
                self.note_list.setCurrentItem(item)
                self.note_list.blockSignals(False)
                # 加载这个笔记到编辑器
                note_id = item.data(Qt.ItemDataRole.UserRole)
                self.current_note_id = note_id
                self.editor.current_note_id = note_id
                note = self.note_manager.get_note(note_id)
                if note:
                    self.editor.blockSignals(True)
                    self.editor.setHtml(note['content'])
                    self.editor.blockSignals(False)
        
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
                self.current_note_id = note_id
                self.editor.current_note_id = note_id
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
        if self.current_note_id:
            # 自动保存
            self.save_current_note()

        # 文本一旦不再为空，可能需要重新允许“新建笔记”
        self._update_new_note_action_enabled()


            
    def save_current_note(self):
        """保存当前笔记"""
        if self.current_note_id:
            content = self.editor.toHtml()
            plain_text = self.editor.toPlainText()
            
            # 从内容中提取标题（第一行）
            # 规则：
            # - 整条笔记为空（没有任何可见字符）=> 标题使用"新笔记"（便于继续编辑，也用于"仅允许一个空草稿"判断）
            # - 第一行只有零宽度字符（U+200B）=> 标题使用"新笔记"
            # - 正文有内容但第一行为空 => 标题为"无标题"
            normalized_plain = (plain_text or "").replace("\r\n", "\n").replace("\r", "\n")
            is_note_empty = normalized_plain.strip() == ""

            if is_note_empty:
                title = "新笔记"
            else:
                first_line = normalized_plain.split("\n")[0][:50]
                # 移除零宽度字符后检查
                first_line_cleaned = first_line.replace('\u200B', '').strip()
                if not first_line_cleaned:
                    # 第一行只有零宽度字符或空白
                    title = "新笔记"
                else:
                    title = first_line.strip() or "无标题"

            self.note_manager.update_note(
                self.current_note_id,
                title=title,
                content=content
            )
            
            # 更新列表中的标题/预览（根据note_id查找对应的item）
            for i in range(self.note_list.count()):
                item = self.note_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == self.current_note_id:
                    widget = self.note_list.itemWidget(item)
                    if widget:
                        layout = widget.layout()
                        if layout and layout.count() > 0:
                            # 1) 标题（第一行）
                            title_label = layout.itemAt(0).widget()
                            if isinstance(title_label, ElidedLabel):
                                title_label.setFullText(title)
                                title_label.setToolTip(title)
                            elif isinstance(title_label, QLabel):
                                title_label.setText(title)

                            # 2) 预览（第二行：时间 + 正文第一行）
                            try:
                                # 从编辑器纯文本提取“正文第一行”（排除标题行）
                                # 规则与 _add_note_item 保持一致：跳过空行、跳过与标题相同的行。
                                normalized_plain = (plain_text or "").replace("\r\n", "\n").replace("\r", "\n")
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

                                # 更新时间字符串：尽量用 note_manager 里刚写入的 updated_at
                                from datetime import datetime
                                try:
                                    note_obj = self.note_manager.get_note(self.current_note_id)
                                    updated_at = datetime.fromisoformat(note_obj.get('updated_at')) if note_obj else None
                                    time_str = updated_at.strftime('%Y/%m/%d') if updated_at else ''
                                except Exception:
                                    time_str = ''

                                info_text = f"{time_str}    {preview_text}"

                                if layout.count() > 1:
                                    info_label = layout.itemAt(1).widget()
                                    if isinstance(info_label, ElidedLabel):
                                        info_label.setFullText(info_text)
                                        info_label.setToolTip(info_text)
                                    elif isinstance(info_label, QLabel):
                                        info_label.setText(info_text)
                            except Exception:
                                pass
                    break
                
    def insert_image(self):
        """插入图片"""
        if not self.current_note_id:
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
        if not self.current_note_id:
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
        if not self.current_note_id:
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self.current_note_id)
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
        if not self.current_note_id:
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self.current_note_id)
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
        if not self.current_note_id:
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self.current_note_id)
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
        if not self.current_note_id:
            QMessageBox.warning(self, "提示", "请先选择要导出的笔记")
            return
            
        note = self.note_manager.get_note(self.current_note_id)
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
    
    def _restore_last_note(self):
        """恢复上次打开的笔记和光标位置"""
        try:
            settings = getattr(self, "_settings", None)
            if settings is None:
                settings = QSettings("encnotes", "encnotes")
            
            # 先恢复文件夹的选中状态
            last_folder_type = settings.value("last_folder_type")
            last_folder_value = settings.value("last_folder_value")
            
            folder_restored = False
            if last_folder_type and last_folder_value:
                # 在文件夹列表中查找匹配的项
                for i in range(self.folder_list.count()):
                    item = self.folder_list.item(i)
                    if item:
                        payload = item.data(Qt.ItemDataRole.UserRole)
                        if isinstance(payload, tuple) and len(payload) == 2:
                            if payload[0] == last_folder_type and payload[1] == last_folder_value:
                                self.folder_list.setCurrentRow(i)
                                folder_restored = True
                                break
            
            # 如果没有恢复文件夹，使用默认选中（"所有笔记"通常在第1行）
            if not folder_restored:
                # 查找"所有笔记"项
                for i in range(self.folder_list.count()):
                    item = self.folder_list.item(i)
                    if item:
                        payload = item.data(Qt.ItemDataRole.UserRole)
                        if isinstance(payload, tuple) and len(payload) == 2:
                            if payload[0] == "system" and payload[1] == "all_notes":
                                self.folder_list.setCurrentRow(i)
                                break
            
            # 再恢复笔记的选中状态和光标位置
            last_note_id = settings.value("last_note_id")
            if last_note_id:
                # 尝试在当前笔记列表中找到并选中该笔记
                for i in range(self.note_list.count()):
                    item = self.note_list.item(i)
                    if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                        if item.data(Qt.ItemDataRole.UserRole) == last_note_id:
                            self.note_list.setCurrentRow(i)
                            
                            # 恢复光标位置
                            last_cursor_position = settings.value("last_cursor_position")
                            if last_cursor_position is not None:
                                try:
                                    from PyQt6.QtGui import QTextCursor
                                    cursor = self.editor.text_edit.textCursor()
                                    # 确保位置不超过文档长度
                                    max_position = len(self.editor.text_edit.toPlainText())
                                    position = min(int(last_cursor_position), max_position)
                                    cursor.setPosition(position)
                                    self.editor.text_edit.setTextCursor(cursor)
                                    
                                    # 设置焦点到编辑器
                                    self.editor.text_edit.setFocus()
                                except Exception:
                                    pass
                            break
        except Exception:
            pass
            
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
            self.current_note_id = None
            
            # 清空笔记列表
            self.note_list.clear()
            
            QMessageBox.information(self, "已锁定", "笔记已锁定，请重新启动应用并输入密码解锁。")
            
            # 退出应用
            self.close()
    
    def closeEvent(self, event):
        """关闭事件"""
        # 持久化窗口大小/位置（用户调整过的尺寸下次启动恢复）
        try:
            settings = getattr(self, "_settings", None)
            if settings is None:
                settings = QSettings("encnotes", "encnotes")
            settings.setValue("main_window/geometry", self.saveGeometry())
            settings.setValue("main_window/state", self.saveState())
            
            # 保存当前选中的文件夹信息
            current_folder_row = self.folder_list.currentRow()
            if current_folder_row >= 0:
                current_item = self.folder_list.item(current_folder_row)
                if current_item:
                    payload = current_item.data(Qt.ItemDataRole.UserRole)
                    if isinstance(payload, tuple) and len(payload) == 2:
                        folder_type, folder_value = payload
                        settings.setValue("last_folder_type", folder_type)
                        settings.setValue("last_folder_value", folder_value)
                    else:
                        settings.remove("last_folder_type")
                        settings.remove("last_folder_value")
                else:
                    settings.remove("last_folder_type")
                    settings.remove("last_folder_value")
            else:
                settings.remove("last_folder_type")
                settings.remove("last_folder_value")
            
            # 保存当前打开的笔记ID和光标位置
            if self.current_note_id:
                settings.setValue("last_note_id", self.current_note_id)
                try:
                    cursor = self.editor.text_edit.textCursor()
                    cursor_position = cursor.position()
                    settings.setValue("last_cursor_position", cursor_position)
                except Exception:
                    pass
            else:
                # 如果没有打开笔记，清除保存的状态
                settings.remove("last_note_id")
                settings.remove("last_cursor_position")
        except Exception:
            pass

        self.save_current_note()

        # 退出程序时：清理当前笔记“已删除但可撤销”的附件
        try:
            if self.current_note_id and getattr(self.note_manager, 'attachment_manager', None):
                self.note_manager.attachment_manager.cleanup_note_attachment_trash(self.current_note_id)
        except Exception:
            pass
        
        # 如果启用了同步，在关闭前同步一次
        if self.sync_manager.sync_enabled:
            self.sync_manager.sync_notes()
        
        # 关闭数据库连接
        self.note_manager.close()
            
        event.accept()
