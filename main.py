#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac风格备忘录应用 - 支持LaTex和MathML数学公式
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from main_window import MainWindow


def main():
    """应用程序入口"""
    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("加密笔记")
    app.setOrganizationName("encnotes")
    
    # 设置Mac风格
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
