# -*- coding: utf-8 -*-
"""
客户问答独立窗口
"""

from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from ui.chat_interface import ChatInterface
from core.config import Config


class ChatWindow(QMainWindow):
    """客户问答独立窗口"""
    
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.admin_window = None  # 管理后台窗口引用
        
        self._init_window()
        self._init_ui()
        self._connect_signals()
    
    def _init_window(self):
        """初始化窗口"""
        self.setWindowTitle("智能客服 - 客户问答")
        self.resize(1100, 750)
        self.setMinimumSize(800, 600)
        
        # 窗口居中偏左
        self._position_window()
    
    def _position_window(self):
        """定位窗口 - 屏幕居中"""
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
    
    def _init_ui(self):
        """初始化界面"""
        self.chat_interface = ChatInterface(self)
        self.setCentralWidget(self.chat_interface)
    
    def _connect_signals(self):
        """连接信号"""
        self.chat_interface.sidebar.admin_clicked.connect(self._open_admin)
    
    def _open_admin(self):
        """打开管理后台（需要登录）"""
        from ui.login_dialog import LoginDialog
        from ui.main_window import MainWindow
        
        # 如果管理后台已经打开，直接激活
        if self.admin_window is not None and self.admin_window.isVisible():
            self.admin_window.activateWindow()
            self.admin_window.raise_()
            return
        
        # 弹出登录对话框
        login_dialog = LoginDialog(self)
        if login_dialog.exec():
            # 登录成功，打开管理后台
            self.admin_window = MainWindow()
            self.admin_window.show()

