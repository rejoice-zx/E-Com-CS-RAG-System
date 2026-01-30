# -*- coding: utf-8 -*-
"""
用户管理界面 - 管理员专用
"""

import os
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import (
    CardWidget, TitleLabel, SubtitleLabel, BodyLabel,
    PrimaryPushButton, PushButton, LineEdit, ComboBox,
    InfoBar, InfoBarPosition, FluentIcon, MessageBox
)


class UserInterface(QWidget):
    """用户管理界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("userInterface")
        self._data_dir = self._get_data_dir()
        self._users_file = os.path.join(self._data_dir, "users.json")
        self._pending_file = os.path.join(self._data_dir, "pending_registrations.json")
        
        self._init_ui()
        self._load_data()
        
        # 定时刷新待审核列表
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._load_pending)
        self._refresh_timer.start(5000)  # 每5秒刷新
    
    def _get_data_dir(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # 标题
        title = TitleLabel("👥 用户管理")
        layout.addWidget(title)
        
        # 待审核注册申请区域
        pending_card = CardWidget()
        pending_layout = QVBoxLayout(pending_card)
        pending_layout.setContentsMargins(16, 16, 16, 16)
        
        pending_title = SubtitleLabel("📋 待审核注册申请")
        pending_layout.addWidget(pending_title)
        
        self.pending_table = QTableWidget()
        self.pending_table.setColumnCount(5)
        self.pending_table.setHorizontalHeaderLabels(["用户名", "申请角色", "申请时间", "操作", ""])
        self.pending_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pending_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pending_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pending_table.setMaximumHeight(200)
        self.pending_table.verticalHeader().setDefaultSectionSize(42)  # 设置行高
        pending_layout.addWidget(self.pending_table)
        
        layout.addWidget(pending_card)
        
        # 用户列表区域
        users_card = CardWidget()
        users_layout = QVBoxLayout(users_card)
        users_layout.setContentsMargins(16, 16, 16, 16)
        
        users_header = QHBoxLayout()
        users_title = SubtitleLabel("📝 用户列表")
        users_header.addWidget(users_title)
        users_header.addStretch()
        
        self.refresh_btn = PushButton("刷新")
        self.refresh_btn.setIcon(FluentIcon.SYNC)
        self.refresh_btn.clicked.connect(self._load_data)
        users_header.addWidget(self.refresh_btn)
        
        users_layout.addLayout(users_header)
        
        self.users_table = QTableWidget()
        self.users_table.setColumnCount(5)
        self.users_table.setHorizontalHeaderLabels(["用户名", "显示名称", "角色", "状态", "操作"])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.users_table.verticalHeader().setDefaultSectionSize(42)  # 设置行高
        users_layout.addWidget(self.users_table)
        
        layout.addWidget(users_card)
        
        # 添加用户区域
        add_card = CardWidget()
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(16, 16, 16, 16)
        
        add_title = SubtitleLabel("➕ 添加新用户")
        add_layout.addWidget(add_title)
        
        form_layout = QHBoxLayout()
        
        self.new_username = LineEdit()
        self.new_username.setPlaceholderText("用户名")
        self.new_username.setFixedWidth(150)
        form_layout.addWidget(self.new_username)
        
        self.new_password = LineEdit()
        self.new_password.setPlaceholderText("密码")
        self.new_password.setEchoMode(LineEdit.Password)
        self.new_password.setFixedWidth(150)
        form_layout.addWidget(self.new_password)
        
        self.new_role = ComboBox()
        self.new_role.addItems(["管理员", "客服"])
        self.new_role.setFixedWidth(100)
        form_layout.addWidget(self.new_role)
        
        self.add_btn = PrimaryPushButton("添加用户")
        self.add_btn.clicked.connect(self._add_user)
        form_layout.addWidget(self.add_btn)
        
        form_layout.addStretch()
        add_layout.addLayout(form_layout)
        
        layout.addWidget(add_card)
    
    def _load_data(self):
        self._load_users()
        self._load_pending()
    
    def _load_users(self):
        """加载用户列表"""
        self.users_table.setRowCount(0)
        
        try:
            with open(self._users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except:
            users = {}
        
        for username, data in users.items():
            row = self.users_table.rowCount()
            self.users_table.insertRow(row)
            
            self.users_table.setItem(row, 0, QTableWidgetItem(username))
            self.users_table.setItem(row, 1, QTableWidgetItem(data.get("name", username)))
            
            role = data.get("role", "cs")
            role_name = "管理员" if role == "admin" else "客服"
            self.users_table.setItem(row, 2, QTableWidgetItem(role_name))
            
            status = "启用" if data.get("is_active", True) else "禁用"
            self.users_table.setItem(row, 3, QTableWidgetItem(status))
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            
            delete_btn = PushButton("删除")
            delete_btn.setFixedSize(60, 30)
            delete_btn.clicked.connect(lambda checked, u=username: self._delete_user(u))
            btn_layout.addWidget(delete_btn)
            
            self.users_table.setCellWidget(row, 4, btn_widget)
    
    def _load_pending(self):
        """加载待审核申请"""
        self.pending_table.setRowCount(0)
        
        try:
            with open(self._pending_file, 'r', encoding='utf-8') as f:
                pending = json.load(f)
        except:
            pending = {}
        
        for username, data in pending.items():
            row = self.pending_table.rowCount()
            self.pending_table.insertRow(row)
            
            self.pending_table.setItem(row, 0, QTableWidgetItem(username))
            
            role = data.get("role", "cs")
            role_name = "管理员" if role == "admin" else "客服"
            self.pending_table.setItem(row, 1, QTableWidgetItem(role_name))
            
            apply_time = data.get("apply_time", "")
            self.pending_table.setItem(row, 2, QTableWidgetItem(apply_time))
            
            # 批准按钮
            approve_btn = PrimaryPushButton("批准")
            approve_btn.setFixedSize(60, 30)
            approve_btn.clicked.connect(lambda checked, u=username: self._approve_registration(u))
            self.pending_table.setCellWidget(row, 3, approve_btn)
            
            # 拒绝按钮
            reject_btn = PushButton("拒绝")
            reject_btn.setFixedSize(60, 32)
            reject_btn.clicked.connect(lambda checked, u=username: self._reject_registration(u))
            self.pending_table.setCellWidget(row, 4, reject_btn)
    
    def _add_user(self):
        """添加新用户"""
        username = self.new_username.text().strip()
        password = self.new_password.text()
        role_text = self.new_role.currentText()
        role = "admin" if role_text == "管理员" else "cs"
        
        if not username or not password:
            InfoBar.warning(
                title="提示",
                content="请填写用户名和密码",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        if len(username) < 3:
            InfoBar.warning(
                title="提示",
                content="用户名至少3个字符",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        if len(password) < 8:
            InfoBar.warning(
                title="提示",
                content="密码至少8个字符",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        try:
            with open(self._users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except:
            users = {}
        
        if username in users:
            InfoBar.error(
                title="错误",
                content="用户名已存在",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        # 创建密码哈希
        from ui.login_dialog import AuthManager
        auth = AuthManager()
        password_record = auth._make_password_record(password)
        
        users[username] = {
            "password": password_record,
            "role": role,
            "name": username,
            "is_active": True,
            "created_at": datetime.now().isoformat()
        }
        
        with open(self._users_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        
        InfoBar.success(
            title="成功",
            content=f"用户 {username} 添加成功",
            parent=self,
            position=InfoBarPosition.TOP
        )
        
        self.new_username.clear()
        self.new_password.clear()
        self._load_users()
    
    def _delete_user(self, username: str):
        """删除用户"""
        if username == "admin":
            InfoBar.warning(
                title="提示",
                content="不能删除默认管理员账户",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        box = MessageBox("确认删除", f"确定要删除用户 {username} 吗？", self)
        if box.exec():
            try:
                with open(self._users_file, 'r', encoding='utf-8') as f:
                    users = json.load(f)
                
                if username in users:
                    del users[username]
                    
                    with open(self._users_file, 'w', encoding='utf-8') as f:
                        json.dump(users, f, ensure_ascii=False, indent=2)
                    
                    InfoBar.success(
                        title="成功",
                        content=f"用户 {username} 已删除",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                    self._load_users()
            except Exception as e:
                InfoBar.error(
                    title="错误",
                    content=f"删除失败: {e}",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
    
    def _approve_registration(self, username: str):
        """批准注册申请"""
        try:
            with open(self._pending_file, 'r', encoding='utf-8') as f:
                pending = json.load(f)
        except:
            pending = {}
        
        if username not in pending:
            InfoBar.warning(
                title="提示",
                content="申请不存在",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        data = pending[username]
        
        # 添加到用户列表
        try:
            with open(self._users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except:
            users = {}
        
        users[username] = {
            "password": data.get("password"),
            "role": data.get("role", "cs"),
            "name": data.get("name", username),
            "is_active": True,
            "created_at": datetime.now().isoformat()
        }
        
        with open(self._users_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        
        # 从待审核列表移除
        del pending[username]
        with open(self._pending_file, 'w', encoding='utf-8') as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        
        InfoBar.success(
            title="成功",
            content=f"已批准用户 {username} 的注册申请",
            parent=self,
            position=InfoBarPosition.TOP
        )
        
        self._load_data()
    
    def _reject_registration(self, username: str):
        """拒绝注册申请"""
        try:
            with open(self._pending_file, 'r', encoding='utf-8') as f:
                pending = json.load(f)
        except:
            pending = {}
        
        if username in pending:
            del pending[username]
            with open(self._pending_file, 'w', encoding='utf-8') as f:
                json.dump(pending, f, ensure_ascii=False, indent=2)
            
            InfoBar.info(
                title="已拒绝",
                content=f"已拒绝用户 {username} 的注册申请",
                parent=self,
                position=InfoBarPosition.TOP
            )
            self._load_pending()
