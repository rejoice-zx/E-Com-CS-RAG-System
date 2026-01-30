# -*- coding: utf-8 -*-
"""
智能电商客服RAG系统 - 客户问答窗口入口
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 初始化日志系统（必须在其他模块导入前）
from core.logger import setup_logging
setup_logging()

from ui.chat_window import ChatWindow
from core.config import Config


def main():
    """启动客户问答窗口"""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("智能电商客服")
    app.setApplicationVersion("2.3.0")
    font = app.font()
    if font.pointSize() <= 0:
        font.setPointSize(10)
        app.setFont(font)

    from core.ui_utils import install_font_point_size_normalizer
    install_font_point_size_normalizer(app)
    
    config = Config()
    
    # 启用配置热更新
    config.enable_hot_reload()
    
    from PySide6.QtGui import QIcon
    icon_path = os.path.join(os.path.dirname(__file__), "resources", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 启动客户问答窗口
    chat_window = ChatWindow()
    chat_window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
