# -*- coding: utf-8 -*-
"""
主窗口模块 - 使用 Fluent Widgets
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    NavigationPushButton
)

from ui.workbench_interface import WorkbenchInterface
from ui.knowledge_interface import KnowledgeInterface
from ui.product_interface import ProductInterface
from ui.human_service_interface import HumanServiceInterface
from ui.log_interface import LogInterface
from ui.performance_interface import PerformanceInterface
from ui.statistics_interface import StatisticsInterface
from ui.user_interface import UserInterface
from ui.settings_dialog import SettingsDialog
from core.config import Config
from core.permissions import get_permission_manager


class MainWindow(FluentWindow):
    """主窗口类 - 使用Fluent导航窗口"""
    
    def __init__(self, username: str = "", role: str = "cs"):
        super().__init__()
        self.config = Config()
        self.username = username
        self.role = role
        self.permission_manager = get_permission_manager()
        
        self._init_window()
        self._init_navigation()
        self._connect_signals()
    
    def _init_window(self):
        """初始化窗口"""
        # 根据角色显示不同的窗口标题
        role_name = "管理员" if self.role == "admin" else "客服"
        self.setWindowTitle(f"智能电商客服RAG系统 - {self.username} ({role_name})")
        self.resize(1200, 750)
        self.setMinimumSize(1000, 650)
        
        # 窗口居中
        self._center_window()
    
    def _center_window(self):
        """窗口居中显示"""
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
    
    def _init_navigation(self):
        """初始化导航栏 - 根据用户角色显示不同页面"""
        # 获取用户可见的页面列表
        visible_pages = self.permission_manager.get_visible_pages()
        
        # 客服工作台界面（作为首页）- 所有角色可见
        if "workbench" in visible_pages:
            self.workbench_interface = WorkbenchInterface(self)
            self.addSubInterface(
                self.workbench_interface,
                FluentIcon.PEOPLE,
                "AI工作台"
            )
        
        # 人工客服界面 - 所有角色可见
        if "human_service" in visible_pages:
            self.human_service_interface = HumanServiceInterface(self)
            self.addSubInterface(
                self.human_service_interface,
                FluentIcon.HEADPHONE,
                "人工客服"
            )
        
        # 知识库管理界面 - 仅管理员可见
        if "knowledge" in visible_pages:
            self.knowledge_interface = KnowledgeInterface(self)
            self.addSubInterface(
                self.knowledge_interface,
                FluentIcon.BOOK_SHELF,
                "知识库管理"
            )
        
        # 商品管理界面 - 管理员和客服可见
        if "product" in visible_pages:
            self.product_interface = ProductInterface(self)
            self.addSubInterface(
                self.product_interface,
                FluentIcon.SHOPPING_CART,
                "商品管理"
            )
        
        # 数据统计界面 - 仅管理员可见
        if "statistics" in visible_pages:
            self.statistics_interface = StatisticsInterface(self)
            self.addSubInterface(
                self.statistics_interface,
                FluentIcon.IOT,
                "数据统计"
            )
        
        # 性能监控界面 - 仅管理员可见
        if "performance" in visible_pages:
            self.performance_interface = PerformanceInterface(self)
            self.addSubInterface(
                self.performance_interface,
                FluentIcon.SPEED_HIGH,
                "性能监控"
            )
        
        # 日志管理界面 - 仅管理员可见
        if "log" in visible_pages:
            self.log_interface = LogInterface(self)
            self.addSubInterface(
                self.log_interface,
                FluentIcon.DOCUMENT,
                "日志管理"
            )
        
        # 用户管理界面 - 仅管理员可见
        if "user" in visible_pages:
            self.user_interface = UserInterface(self)
            self.addSubInterface(
                self.user_interface,
                FluentIcon.PEOPLE,
                "用户管理"
            )
        
        # 底部设置按钮
        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text="设置",
            onClick=self._on_settings_clicked,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )
    
    def _connect_signals(self):
        """连接信号"""
        pass
    
    def _on_settings_clicked(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()
    
    def _on_settings_changed(self):
        """设置变更"""
        pass
