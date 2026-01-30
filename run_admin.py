# -*- coding: utf-8 -*-
"""
管理后台窗口 - 独立启动入口（需要登录）
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 初始化日志系统（必须在其他模块导入前）
from core.logger import setup_logging
setup_logging()

from ui.main_window import MainWindow
from ui.login_dialog import LoginDialog
from core.config import Config


def main():
    """启动管理后台窗口"""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("智能电商客服 - 管理后台")
    
    config = Config()
    
    # 启用配置热更新
    config.enable_hot_reload()
    
    from PySide6.QtGui import QIcon
    icon_path = os.path.join(os.path.dirname(__file__), "resources", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 显示登录对话框
    login_dialog = LoginDialog()
    
    if login_dialog.exec():
        # 登录成功，从权限管理器获取当前用户信息
        from core.permissions import get_permission_manager
        pm = get_permission_manager()
        current_user = pm.get_current_user()
        
        if current_user:
            username = current_user.username
            role = current_user.role
        else:
            # 回退方案：使用登录对话框中的用户名
            username = login_dialog.login_username.text().strip()
            role = "cs"
        
        # 显示管理后台（传递用户名和角色）
        window = MainWindow(
            username=username,
            role=role
        )
        window.show()
        sys.exit(app.exec())
    else:
        # 登录取消
        sys.exit(0)


if __name__ == "__main__":
    main()
