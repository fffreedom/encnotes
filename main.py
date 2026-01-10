#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac风格备忘录应用 - 支持LaTex和MathML数学公式
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from main_window import MainWindow

# ... existing code ...

def _init_logging():
    """初始化日志：写入用户目录，便于打包后收集问题日志。"""
    import logging
    import os
    import sys
    from logging.handlers import RotatingFileHandler

    try:
        # 日志文件放在与数据库相同的目录下
        base_dir = os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Group Containers",
            "group.com.encnotes",
        )
        os.makedirs(base_dir, exist_ok=True)
        log_path = os.path.join(base_dir, "encnotes.log")

        root = logging.getLogger()
        root.setLevel(logging.INFO)

        fmt = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s:%(lineno)d] %(message)s"
        )

        file_handler = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

        # 开发期仍希望终端可见；打包后没有控制台也不影响
        console = logging.StreamHandler(stream=sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)

        class _StreamToLogger:
            def __init__(self, logger, level):
                self.logger = logger
                self.level = level

            def write(self, buf):
                try:
                    for line in (buf or "").rstrip().splitlines():
                        if line:
                            self.logger.log(self.level, line)
                except Exception:
                    pass

            def flush(self):
                return

        # 把 print / Qt warning / traceback 等也写进日志文件
        sys.stdout = _StreamToLogger(logging.getLogger("stdout"), logging.INFO)
        sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.WARNING)

        def _excepthook(exctype, value, tb):
            logging.getLogger("uncaught").exception(
                "Uncaught exception", exc_info=(exctype, value, tb)
            )

        sys.excepthook = _excepthook

        logging.getLogger(__name__).info("Logging initialized: %s", log_path)
    except Exception:
        # 日志初始化不能影响程序启动
        pass


# ... existing code ...

def main():
    """应用程序入口"""
    _init_logging()
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
