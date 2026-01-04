#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口 - Mac风格三栏布局
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QListWidget, QToolBar, QPushButton,
    QListWidgetItem, QMessageBox, QFileDialog, QDialog,
    QLabel, QCheckBox, QProgressDialog, QInputDialog, QMenu
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QDesktopServices
from PyQt6.QtCore import QUrl
from note_editor import NoteEditor
from note_manager import NoteManager
from export_manager import ExportManager
from icloud_sync import CloudKitSyncManager
import datetime


class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        self.note_manager = NoteManager()
        self.export_manager = ExportManager()
        self.sync_manager = CloudKitSyncManager(self.note_manager)
        self.current_note_id = None
        self.current_folder_id = None  # 当前选中的文件夹ID
        self.custom_folders = []  # 自定义文件夹列表
        self.init_ui()
        self.load_folders()  # 加载文件夹
        self.load_notes()
        
        # 设置自动同步定时器（每5分钟）
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.auto_sync)
        self.sync_timer.start(300000)  # 5分钟
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("数学笔记")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：文件夹列表
        self.folder_list = QListWidget()
        self.folder_list.setMaximumWidth(200)
        self.folder_list.addItem("📝 所有笔记")
        self.folder_list.addItem("⭐ 收藏")
        self.folder_list.addItem("🗑️ 最近删除")
        self.folder_list.setCurrentRow(0)
        self.folder_list.currentRowChanged.connect(self.on_folder_changed)
        
        # 为文件夹列表添加右键菜单
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self.show_folder_context_menu)
        
        # 中间：笔记列表
        self.note_list = QListWidget()
        self.note_list.setMaximumWidth(300)
        self.note_list.currentItemChanged.connect(self.on_note_selected)
        
        # 右侧：编辑器
        self.editor = NoteEditor()
        self.editor.textChanged.connect(self.on_text_changed)
        
        # 添加到分割器
        splitter.addWidget(self.folder_list)
        splitter.addWidget(self.note_list)
        splitter.addWidget(self.editor)
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 5)
        
        main_layout.addWidget(splitter)
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建菜单栏
        self.create_menubar()
        
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # 新建笔记按钮
        new_note_action = QAction("➕ 新建笔记", self)
        new_note_action.setShortcut(QKeySequence("Ctrl+N"))
        new_note_action.triggered.connect(self.create_new_note)
        toolbar.addAction(new_note_action)
        
        # 新建文件夹按钮
        new_folder_action = QAction("📁 新建文件夹", self)
        new_folder_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_folder_action.triggered.connect(self.create_new_folder)
        toolbar.addAction(new_folder_action)
        
        toolbar.addSeparator()
        
        # 删除笔记按钮
        delete_note_action = QAction("🗑️ 删除", self)
        delete_note_action.setShortcut(QKeySequence("Ctrl+D"))
        delete_note_action.triggered.connect(self.delete_note)
        toolbar.addAction(delete_note_action)
        
    def create_menubar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        new_action = QAction("新建笔记", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.create_new_note)
        file_menu.addAction(new_action)
        
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
        
    def load_notes(self):
        """加载笔记列表"""
        self.note_list.clear()
        
        # 根据当前选中的文件夹加载笔记
        current_row = self.folder_list.currentRow()
        
        if current_row == 0:  # 所有笔记
            notes = self.note_manager.get_all_notes()
        elif current_row == 1:  # 收藏
            notes = self.note_manager.get_favorite_notes()
        elif current_row == 2:  # 最近删除
            notes = self.note_manager.get_deleted_notes()
        else:  # 自定义文件夹
            folder_index = current_row - 3
            if 0 <= folder_index < len(self.custom_folders):
                folder_id = self.custom_folders[folder_index]['id']
                notes = self.note_manager.get_notes_by_folder(folder_id)
            else:
                notes = []
        
        for note in notes:
            item = QListWidgetItem(note['title'])
            item.setData(Qt.ItemDataRole.UserRole, note['id'])
            self.note_list.addItem(item)
            
        if notes:
            self.note_list.setCurrentRow(0)
            
    def load_folders(self):
        """加载文件夹列表"""
        # 保存当前选中的行
        current_row = self.folder_list.currentRow()
        
        # 清空并重新添加系统文件夹
        self.folder_list.clear()
        self.folder_list.addItem("📝 所有笔记")
        self.folder_list.addItem("⭐ 收藏")
        self.folder_list.addItem("🗑️ 最近删除")
        
        # 加载自定义文件夹
        self.custom_folders = self.note_manager.get_all_folders()
        for folder in self.custom_folders:
            item_text = f"📁 {folder['name']}"
            self.folder_list.addItem(item_text)
        
        # 恢复选中状态
        if current_row >= 0 and current_row < self.folder_list.count():
            self.folder_list.setCurrentRow(current_row)
        else:
            self.folder_list.setCurrentRow(0)
            
    def create_new_folder(self):
        """创建新文件夹"""
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "请输入文件夹名称:"
        )
        
        if ok and name.strip():
            folder_id = self.note_manager.create_folder(name.strip())
            self.load_folders()
            
            # 选中新创建的文件夹
            for i, folder in enumerate(self.custom_folders):
                if folder['id'] == folder_id:
                    self.folder_list.setCurrentRow(3 + i)
                    break
                    
    def rename_folder(self, folder_id: str):
        """重命名文件夹"""
        folder = self.note_manager.get_folder(folder_id)
        if not folder:
            return
            
        name, ok = QInputDialog.getText(
            self, "重命名文件夹", 
            "请输入新名称:",
            text=folder['name']
        )
        
        if ok and name.strip():
            self.note_manager.update_folder(folder_id, name.strip())
            self.load_folders()
            
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
            self.note_manager.delete_folder(folder_id)
            self.load_folders()
            self.load_notes()
            
    def show_folder_context_menu(self, position):
        """显示文件夹右键菜单"""
        item = self.folder_list.itemAt(position)
        if not item:
            return
            
        row = self.folder_list.row(item)
        
        # 只为自定义文件夹显示菜单
        if row < 3:
            return
            
        folder_index = row - 3
        if folder_index >= len(self.custom_folders):
            return
            
        folder = self.custom_folders[folder_index]
        
        # 创建菜单
        menu = QMenu(self)
        
        rename_action = QAction("重命名", self)
        rename_action.triggered.connect(lambda: self.rename_folder(folder['id']))
        menu.addAction(rename_action)
        
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self.delete_folder_confirm(folder['id']))
        menu.addAction(delete_action)
        
        # 显示菜单
        menu.exec(self.folder_list.mapToGlobal(position))
            
    def create_new_note(self):
        """创建新笔记"""
        # 获取当前文件夹ID
        current_row = self.folder_list.currentRow()
        folder_id = None
        
        if current_row >= 3:  # 自定义文件夹
            folder_index = current_row - 3
            if 0 <= folder_index < len(self.custom_folders):
                folder_id = self.custom_folders[folder_index]['id']
        
        note_id = self.note_manager.create_note(folder_id=folder_id)
        self.load_notes()
        
        # 选中新创建的笔记
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentItem(item)
                break
                
    def delete_note(self):
        """删除当前笔记"""
        if self.current_note_id is None:
            return
            
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这条笔记吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.note_manager.delete_note(self.current_note_id)
            self.load_notes()
            
    def on_folder_changed(self, index):
        """文件夹切换"""
        self.load_notes()
        
    def on_note_selected(self, current, previous):
        """笔记选中事件"""
        if previous:
            # 保存之前的笔记
            self.save_current_note()
            
        if current:
            note_id = current.data(Qt.ItemDataRole.UserRole)
            self.current_note_id = note_id
            note = self.note_manager.get_note(note_id)
            
            if note:
                self.editor.blockSignals(True)
                self.editor.setHtml(note['content'])
                self.editor.blockSignals(False)
        else:
            self.current_note_id = None
            self.editor.clear()
            
    def on_text_changed(self):
        """文本变化事件"""
        if self.current_note_id:
            # 自动保存
            self.save_current_note()
            
    def save_current_note(self):
        """保存当前笔记"""
        if self.current_note_id:
            content = self.editor.toHtml()
            plain_text = self.editor.toPlainText()
            
            # 从内容中提取标题（第一行）
            title = plain_text.split('\n')[0][:50] if plain_text else "无标题"
            if not title.strip():
                title = "无标题"
                
            self.note_manager.update_note(
                self.current_note_id,
                title=title,
                content=content
            )
            
            # 更新列表中的标题
            current_item = self.note_list.currentItem()
            if current_item:
                current_item.setText(title)
                
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
    
    def closeEvent(self, event):
        """关闭事件"""
        self.save_current_note()
        
        # 如果启用了同步，在关闭前同步一次
        if self.sync_manager.sync_enabled:
            self.sync_manager.sync_notes()
        
        # 关闭数据库连接
        self.note_manager.close()
            
        event.accept()
