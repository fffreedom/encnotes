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
from password_dialog import UnlockDialog, SetupPasswordDialog, ChangePasswordDialog
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
        self.current_tag_id = None  # 当前选中的标签ID
        self.custom_folders = []  # 自定义文件夹列表
        self.tags = []  # 标签列表
        
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
        
        # 设置自动同步定时器（每5分钟）
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.auto_sync)
        self.sync_timer.start(300000)  # 5分钟
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("加密笔记")
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
        self.folder_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #f5f5f5;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border: none;
            }
            QListWidget::item:selected {
                background-color: #FFE066;
                color: #000000;
            }
            QListWidget::item:hover {
                background-color: #FFF4CC;
            }
        """)
        self.folder_list.setCurrentRow(0)
        self.folder_list.currentRowChanged.connect(self.on_folder_changed)
        
        # 为文件夹列表添加右键菜单
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self.show_folder_context_menu)
        
        # 中间：笔记列表
        self.note_list = QListWidget()
        # 为笔记列表添加右键菜单
        self.note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.note_list.customContextMenuRequested.connect(self.show_note_context_menu)
        self.note_list.setMaximumWidth(300)
        self.note_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 去掉焦点边框
        self.note_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #ffffff;
                font-size: 15px;
                outline: none;
            }
            QListWidget::item {
                padding: 0px;
                border: none;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #FFE066;
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
        """)
        self.note_list.currentItemChanged.connect(self.on_note_selected)
        
        # 右侧：编辑器
        self.editor = NoteEditor(self.note_manager)
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
        group_separator = QWidget()
        group_separator.setFixedHeight(1)
        group_separator.setStyleSheet("""
            background-color: #e0e0e0;
            margin-left: 0px;
            margin-right: 8px;
        """)
        widget_layout.addWidget(group_separator)

        widget.setFixedHeight(41)  # 40 + 1px分隔线
        
        self.note_list.addItem(item)
        self.note_list.setItemWidget(item, widget)
        item.setSizeHint(QSize(280, 41))
    
    def load_notes(self):
        """加载笔记列表"""
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
        elif current_row == deleted_row:  # 最近删除
            notes = self.note_manager.get_deleted_notes()
            self.current_folder_id = None
            self.current_tag_id = None
        elif 2 <= current_row < deleted_row:  # 自定义文件夹
            folder_index = current_row - 2
            if 0 <= folder_index < len(self.custom_folders):
                folder_id = self.custom_folders[folder_index]['id']
                notes = self.note_manager.get_notes_by_folder(folder_id)
                self.current_folder_id = folder_id
                self.current_tag_id = None
            else:
                notes = []
        elif current_row >= first_tag_row:  # 标签
            tag_index = current_row - first_tag_row
            if 0 <= tag_index < len(self.tags):
                tag_id = self.tags[tag_index]['id']
                notes = self.note_manager.get_notes_by_tag(tag_id)
                self.current_folder_id = None
                self.current_tag_id = tag_id
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
            for note in pinned_notes:
                self._add_note_item(note)
        
        # 显示按时间分组的普通笔记
        for group_name in group_order:
            if group_name in time_groups and time_groups[group_name]:
                self._add_group_header(group_name)
                for note in time_groups[group_name]:
                    self._add_note_item(note)
        
        if notes:
            # 选中第一个可选中的笔记项（跳过分组标题）
            for i in range(self.note_list.count()):
                item = self.note_list.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    self.note_list.setCurrentRow(i)
                    break
    
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
        widget_layout = QVBoxLayout(widget)
        widget_layout.setContentsMargins(32, 6, 8, 6)  # 笔记内容缩进32px（相对分组标识再缩进一层）
        widget_layout.setSpacing(2)  # 减小间距，从4改为2
        
        # 第一行：标题
        title_label = QLabel(note['title'])
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
        widget_layout.addWidget(title_label)
        
        # 第二行：时间 + 预览
        info_text = f"{time_str}    {preview_text}"
        info_label = QLabel(info_text)
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
        widget_layout.addWidget(info_label)
        
        # 添加底部分隔线（缩进显示）
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("""
            background-color: #e0e0e0;
            margin-left: 0px;
            margin-right: 8px;
        """)
        widget_layout.addWidget(separator)
        
        # 设置widget固定高度
        widget.setFixedHeight(61)  # 增加1px以容纳分隔线
        
        self.note_list.addItem(item)
        self.note_list.setItemWidget(item, widget)
        
        # 设置item高度
        item.setSizeHint(QSize(280, 61))  # 增加1px以容纳分隔线
            
    def load_folders(self):
        """加载文件夹列表（新布局：iCloud分组，支持多级文件夹）"""
        # 保存当前选中的行
        current_row = self.folder_list.currentRow()
        
        # 清空列表
        self.folder_list.clear()
        
        # 添加iCloud标题（不可选中）
        icloud_header = QListWidgetItem("☁️ iCloud")
        icloud_header.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中
        font = icloud_header.font()
        font.setBold(True)
        icloud_header.setFont(font)
        self.folder_list.addItem(icloud_header)
        
        # 添加系统文件夹（缩进显示）
        self.folder_list.addItem("    📝 所有笔记")
        
        # 加载自定义文件夹（支持层级显示）
        all_folders = self.note_manager.get_all_folders()
        
        # 构建文件夹树结构
        self.custom_folders = []
        self._add_folders_recursive(all_folders, None, 1, self.custom_folders)
        
        # 添加最近删除（缩进显示，在iCloud下面）
        self.folder_list.addItem("    🗑️ 最近删除")
        
        # 添加标签标题（与iCloud并列）
        tag_header = QListWidgetItem("🏷️ 标签")
        tag_header.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中
        font = tag_header.font()
        font.setBold(True)
        tag_header.setFont(font)
        self.folder_list.addItem(tag_header)
        
        # 加载标签（缩进显示）
        self.tags = self.note_manager.get_all_tags()
        for tag in self.tags:
            count = self.note_manager.get_tag_count(tag['id'])
            item_text = f"    # {tag['name']} ({count})"
            self.folder_list.addItem(item_text)
        
        # 恢复选中状态
        if current_row >= 0 and current_row < self.folder_list.count():
            item = self.folder_list.item(current_row)
            if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                self.folder_list.setCurrentRow(current_row)
            else:
                self.folder_list.setCurrentRow(1)  # 默认选中"所有笔记"
        else:
            self.folder_list.setCurrentRow(1)  # 默认选中"所有笔记"
    
    def _add_folders_recursive(self, all_folders, parent_id, level, flat_list):
        """递归添加文件夹，支持多级层级显示
        
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
        
        # 添加到列表
        for folder in current_level_folders:
            # 计算缩进（每级增加4个空格）
            indent = "    " * level
            item_text = f"{indent}📁 {folder['name']}"
            self.folder_list.addItem(item_text)
            
            # 添加到扁平列表（保持与原有逻辑兼容）
            flat_list.append(folder)
            
            # 递归添加子文件夹
            self._add_folders_recursive(all_folders, folder['id'], level + 1, flat_list)
            
    def create_new_folder(self):
        """创建新文件夹"""
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "请输入文件夹名称:"
        )
        
        if ok and name.strip():
            folder_id = self.note_manager.create_folder(name.strip())
            self.load_folders()
            
            # 选中新创建的文件夹（索引从2开始）
            for i, folder in enumerate(self.custom_folders):
                if folder['id'] == folder_id:
                    self.folder_list.setCurrentRow(2 + i)
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
            
    # ========== 标签管理方法 ==========
    
    def create_new_tag(self):
        """创建新标签"""
        name, ok = QInputDialog.getText(
            self, "新建标签", "请输入标签名称:"
        )
        
        if ok and name.strip():
            self.note_manager.create_tag(name.strip())
            self.load_folders()
            
    def rename_tag(self, tag_id: str):
        """重命名标签"""
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
        """创建新笔记"""
        # 获取当前文件夹ID
        current_row = self.folder_list.currentRow()
        folder_id = None
        
        folder_count = len(self.custom_folders)
        deleted_row = 2 + folder_count
        
        if 2 <= current_row < deleted_row:  # 自定义文件夹
            folder_index = current_row - 2
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
        
        # 设置焦点到编辑器，让光标闪烁
        self.editor.text_edit.setFocus()
                
    def show_folder_context_menu(self, position):
        """显示文件夹列表的右键菜单"""
        item = self.folder_list.itemAt(position)
        menu = QMenu(self)
        
        # 获取当前行
        current_row = self.folder_list.currentRow()
        folder_count = len(self.custom_folders)
        
        # 判断是否点击在自定义文件夹上（索引从2开始，到2+folder_count-1）
        if item and 2 <= current_row < 2 + folder_count:
            # 点击在文件夹上
            folder_index = current_row - 2
            if 0 <= folder_index < len(self.custom_folders):
                folder_id = self.custom_folders[folder_index]['id']
                
                # 新建笔记
                new_note_action = QAction("新建笔记", self)
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
        else:
            # 点击在空白区域或其他位置，只显示新建文件夹
            new_folder_action = QAction("新建文件夹", self)
            new_folder_action.triggered.connect(self.create_new_folder)
            menu.addAction(new_folder_action)
        
        menu.exec(self.folder_list.mapToGlobal(position))
    
    def show_note_context_menu(self, position):
        """显示笔记列表的右键菜单"""
        item = self.note_list.itemAt(position)
        menu = QMenu(self)
        
        if item:
            # 点击在笔记上
            note_id = item.data(Qt.ItemDataRole.UserRole)
            
            # 新建笔记
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(self.create_new_note)
            menu.addAction(new_note_action)
            
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
            # 点击在空白区域
            new_note_action = QAction("新建笔记", self)
            new_note_action.triggered.connect(self.create_new_note)
            menu.addAction(new_note_action)
        
        menu.exec(self.note_list.mapToGlobal(position))
    
    def create_subfolder(self, parent_folder_id: str):
        """在指定文件夹下创建子文件夹"""
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "请输入文件夹名称:"
        )
        
        if ok and name.strip():
            # 创建子文件夹，传入父文件夹ID
            folder_id = self.note_manager.create_folder(name.strip(), parent_folder_id)
            self.load_folders()
            
            # 选中新创建的文件夹
            for i, folder in enumerate(self.custom_folders):
                if folder['id'] == folder_id:
                    self.folder_list.setCurrentRow(2 + i)
                    break
    
    def create_note_in_folder(self, folder_id: str):
        """在指定文件夹下创建笔记"""
        # 创建笔记
        note_id = self.note_manager.create_note(folder_id=folder_id)
        
        # 刷新笔记列表
        self.load_notes()
        
        # 选中新创建的笔记
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentItem(item)
                break
        
        # 设置焦点到编辑器，让光标闪烁
        self.editor.text_edit.setFocus()
    
    def rename_note(self, note_id: str):
        """重命名笔记"""
        note = self.note_manager.get_note(note_id)
        if not note:
            return
        
        # 获取当前标题（从HTML内容中提取第一行）
        current_title = note.get('title', '无标题')
        
        name, ok = QInputDialog.getText(
            self, "重命名笔记",
            "请输入新标题:",
            text=current_title
        )
        
        if ok and name.strip():
            # 更新笔记标题
            self.note_manager.update_note(note_id, title=name.strip())
            self.load_notes()
            
            # 如果是当前笔记，重新加载编辑器内容
            if note_id == self.current_note_id:
                self.load_note_content(note_id)
    
    def toggle_pin_note(self, note_id: str):
        """切换笔记的置顶状态"""
        is_pinned = self.note_manager.toggle_pin_note(note_id)
        
        # 重新加载笔记列表
        self.load_notes()
        
        # 显示提示信息
        status_text = "已置顶" if is_pinned else "已取消置顶"
        self.statusBar().showMessage(status_text, 2000)
    
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
        self.load_notes()
        
    def on_note_selected(self, current, previous):
        """笔记选中事件"""
        if previous:
            # 保存之前的笔记
            self.save_current_note()
            
        if current:
            note_id = current.data(Qt.ItemDataRole.UserRole)
            self.current_note_id = note_id
            self.editor.current_note_id = note_id  # 设置编辑器的当前笔记ID
            note = self.note_manager.get_note(note_id)
            
            if note:
                self.editor.blockSignals(True)
                self.editor.setHtml(note['content'])
                self.editor.blockSignals(False)
                
                # 将光标移动到第一行（标题）的末尾
                from PyQt6.QtGui import QTextCursor
                cursor = self.editor.text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)  # 移动到文档开始
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)  # 移动到第一行末尾
                self.editor.text_edit.setTextCursor(cursor)
                
                # 设置焦点到编辑器，让光标闪烁
                self.editor.text_edit.setFocus()
        else:
            self.current_note_id = None
            self.editor.current_note_id = None
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
            
            # 更新列表中的标题（根据note_id查找对应的item）
            for i in range(self.note_list.count()):
                item = self.note_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == self.current_note_id:
                    # 获取自定义widget
                    widget = self.note_list.itemWidget(item)
                    if widget:
                        # 获取widget中的第一个QLabel（标题）
                        layout = widget.layout()
                        if layout and layout.count() > 0:
                            title_label = layout.itemAt(0).widget()
                            if isinstance(title_label, QLabel):
                                title_label.setText(title)
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
        self.save_current_note()
        
        # 如果启用了同步，在关闭前同步一次
        if self.sync_manager.sync_enabled:
            self.sync_manager.sync_notes()
        
        # 关闭数据库连接
        self.note_manager.close()
            
        event.accept()