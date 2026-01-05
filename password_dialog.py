#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
密码对话框 - 用于密码输入和管理
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon


class UnlockDialog(QDialog):
    """解锁对话框"""
    
    def __init__(self, parent=None, allow_cancel=False):
        super().__init__(parent)
        self.password = None
        self.allow_cancel = allow_cancel
        self.exit_requested = False
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("解锁笔记")
        self.setModal(True)
        self.setFixedWidth(400)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 标题
        title_label = QLabel("🔒 请输入密码解锁笔记")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 提示文字
        hint_label = QLabel("您的笔记已加密，需要输入密码才能访问")
        hint_label.setStyleSheet("color: #666666; font-size: 13px;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        layout.addSpacing(10)
        
        # 密码输入框
        password_label = QLabel("密码:")
        layout.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #FFE066;
            }
        """)
        self.password_input.returnPressed.connect(self.accept)
        layout.addWidget(self.password_input)
        
        layout.addSpacing(10)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        unlock_btn = QPushButton("解锁")
        unlock_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #FFE066;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
        """)
        unlock_btn.clicked.connect(self.accept)
        unlock_btn.setDefault(True)
        button_layout.addWidget(unlock_btn)

        if self.allow_cancel:
            cancel_btn = QPushButton("取消")
            cancel_btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 20px;
                    background-color: #f0f0f0;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
            """)
            cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(cancel_btn)

        exit_btn = QPushButton("退出")
        exit_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #f0f0f0;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        exit_btn.clicked.connect(self._request_exit)
        button_layout.addWidget(exit_btn)

        layout.addLayout(button_layout)

        
        self.setLayout(layout)
        
        # 聚焦到密码输入框
        self.password_input.setFocus()
        
    def accept(self):
        """确认按钮"""
        self.password = self.password_input.text()
        
        if not self.password:
            QMessageBox.warning(self, "提示", "请输入密码")
            return
            
        super().accept()
        
    def get_password(self):
        """获取输入的密码"""
        return self.password

    def should_exit(self) -> bool:
        """是否点击了退出按钮"""
        return self.exit_requested

    def _request_exit(self):
        """请求退出程序"""
        self.exit_requested = True
        self.reject()


class SetupPasswordDialog(QDialog):
    """首次设置密码对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.password = None
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("设置密码")
        self.setModal(True)
        self.setFixedWidth(450)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 标题
        title_label = QLabel("🔐 设置加密密码")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 提示文字
        hint_label = QLabel(
            "为了保护您的笔记安全，请设置一个加密密码。\n"
            "密码将用于加密所有笔记内容。\n\n"
            "⚠️ 请务必记住密码，忘记密码将无法恢复笔记！"
        )
        hint_label.setStyleSheet("color: #666666; font-size: 13px;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        layout.addSpacing(10)
        
        # 密码输入框
        password_label = QLabel("密码:")
        layout.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("请输入密码（至少8个字符）")
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #FFE066;
            }
        """)
        layout.addWidget(self.password_input)
        
        # 确认密码输入框
        confirm_label = QLabel("确认密码:")
        layout.addWidget(confirm_label)
        
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setPlaceholderText("请再次输入密码")
        self.confirm_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #FFE066;
            }
        """)
        self.confirm_input.returnPressed.connect(self.accept)
        layout.addWidget(self.confirm_input)
        
        layout.addSpacing(10)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #f0f0f0;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        setup_btn = QPushButton("设置密码")
        setup_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #FFE066;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
        """)
        setup_btn.clicked.connect(self.accept)
        setup_btn.setDefault(True)
        button_layout.addWidget(setup_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 聚焦到密码输入框
        self.password_input.setFocus()
        
    def accept(self):
        """确认按钮"""
        password = self.password_input.text()
        confirm = self.confirm_input.text()
        
        # 验证密码
        if not password:
            QMessageBox.warning(self, "提示", "请输入密码")
            return
            
        if len(password) < 8:
            QMessageBox.warning(self, "提示", "密码长度至少为8个字符")
            return
            
        if password != confirm:
            QMessageBox.warning(self, "提示", "两次输入的密码不一致")
            return
            
        self.password = password
        super().accept()
        
    def get_password(self):
        """获取输入的密码"""
        return self.password


class ChangePasswordDialog(QDialog):
    """修改密码对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.old_password = None
        self.new_password = None
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("修改密码")
        self.setModal(True)
        self.setFixedWidth(450)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 标题
        title_label = QLabel("🔑 修改加密密码")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 提示文字
        hint_label = QLabel(
            "修改密码后，所有笔记将使用新密码重新加密。\n"
            "⚠️ 请务必记住新密码！"
        )
        hint_label.setStyleSheet("color: #666666; font-size: 13px;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        layout.addSpacing(10)
        
        # 旧密码输入框
        old_password_label = QLabel("当前密码:")
        layout.addWidget(old_password_label)
        
        self.old_password_input = QLineEdit()
        self.old_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_password_input.setPlaceholderText("请输入当前密码")
        self.old_password_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #FFE066;
            }
        """)
        layout.addWidget(self.old_password_input)
        
        layout.addSpacing(5)
        
        # 新密码输入框
        new_password_label = QLabel("新密码:")
        layout.addWidget(new_password_label)
        
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_input.setPlaceholderText("请输入新密码（至少8个字符）")
        self.new_password_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #FFE066;
            }
        """)
        layout.addWidget(self.new_password_input)
        
        # 确认新密码输入框
        confirm_label = QLabel("确认新密码:")
        layout.addWidget(confirm_label)
        
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setPlaceholderText("请再次输入新密码")
        self.confirm_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #FFE066;
            }
        """)
        self.confirm_input.returnPressed.connect(self.accept)
        layout.addWidget(self.confirm_input)
        
        layout.addSpacing(10)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #f0f0f0;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        change_btn = QPushButton("修改密码")
        change_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #FFE066;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
        """)
        change_btn.clicked.connect(self.accept)
        change_btn.setDefault(True)
        button_layout.addWidget(change_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 聚焦到旧密码输入框
        self.old_password_input.setFocus()
        
    def accept(self):
        """确认按钮"""
        old_password = self.old_password_input.text()
        new_password = self.new_password_input.text()
        confirm = self.confirm_input.text()
        
        # 验证密码
        if not old_password:
            QMessageBox.warning(self, "提示", "请输入当前密码")
            return
            
        if not new_password:
            QMessageBox.warning(self, "提示", "请输入新密码")
            return
            
        if len(new_password) < 8:
            QMessageBox.warning(self, "提示", "新密码长度至少为8个字符")
            return
            
        if new_password != confirm:
            QMessageBox.warning(self, "提示", "两次输入的新密码不一致")
            return
            
        if old_password == new_password:
            QMessageBox.warning(self, "提示", "新密码不能与当前密码相同")
            return
            
        self.old_password = old_password
        self.new_password = new_password
        super().accept()
        
    def get_passwords(self):
        """获取输入的密码"""
        return self.old_password, self.new_password