# -*- coding: utf-8 -*-
"""
用户权限管理模块
实现基于角色的访问控制（RBAC）
"""

import os
import json
import logging
from enum import Enum
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限枚举"""
    # 对话权限
    CHAT_VIEW = "chat.view"
    CHAT_CREATE = "chat.create"
    CHAT_DELETE = "chat.delete"
    
    # 知识库权限
    KNOWLEDGE_VIEW = "knowledge.view"
    KNOWLEDGE_CREATE = "knowledge.create"
    KNOWLEDGE_EDIT = "knowledge.edit"
    KNOWLEDGE_DELETE = "knowledge.delete"
    KNOWLEDGE_REBUILD_INDEX = "knowledge.rebuild_index"
    
    # 商品权限
    PRODUCT_VIEW = "product.view"
    PRODUCT_CREATE = "product.create"
    PRODUCT_EDIT = "product.edit"
    PRODUCT_DELETE = "product.delete"
    
    # 用户管理权限
    USER_VIEW = "user.view"
    USER_CREATE = "user.create"
    USER_EDIT = "user.edit"
    USER_DELETE = "user.delete"
    
    # 系统权限
    SETTINGS_VIEW = "settings.view"
    SETTINGS_EDIT = "settings.edit"
    BACKUP_CREATE = "backup.create"
    BACKUP_RESTORE = "backup.restore"
    STATISTICS_VIEW = "statistics.view"


class Role(Enum):
    """角色枚举"""
    ADMIN = "admin"           # 管理员：所有权限，可见所有页面
    CUSTOMER_SERVICE = "cs"   # 客服：对话和商品管理


# 角色权限映射
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: set(Permission),  # 所有权限
    
    Role.CUSTOMER_SERVICE: {
        # 对话权限
        Permission.CHAT_VIEW,
        Permission.CHAT_CREATE,
        # 商品权限
        Permission.PRODUCT_VIEW,
        Permission.PRODUCT_CREATE,
        Permission.PRODUCT_EDIT,
        Permission.PRODUCT_DELETE,
        # 基础设置
        Permission.SETTINGS_VIEW,
    },
}


@dataclass
class User:
    """用户数据类"""
    username: str
    password_hash: str
    role: str = "readonly"
    display_name: str = ""
    email: str = ""
    created_at: str = ""
    last_login: str = ""
    is_active: bool = True
    custom_permissions: List[str] = field(default_factory=list)  # 额外权限
    denied_permissions: List[str] = field(default_factory=list)  # 禁止权限


class PermissionManager:
    """权限管理器"""
    
    _instance = None
    _current_user: Optional[User] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._data_dir = self._get_data_dir()
        self._users_file = os.path.join(self._data_dir, "users.json")
        self._users: Dict[str, User] = {}
        self._load_users()
    
    def _get_data_dir(self) -> str:
        """获取数据目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    
    def _load_users(self):
        """加载用户数据"""
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for username, user_data in data.items():
                        self._users[username] = User(
                            username=username,
                            password_hash=user_data.get("password", ""),
                            role=user_data.get("role", "readonly"),
                            display_name=user_data.get("display_name", username),
                            email=user_data.get("email", ""),
                            created_at=user_data.get("created_at", ""),
                            last_login=user_data.get("last_login", ""),
                            is_active=user_data.get("is_active", True),
                            custom_permissions=user_data.get("custom_permissions", []),
                            denied_permissions=user_data.get("denied_permissions", []),
                        )
            except Exception as e:
                logger.exception("加载用户数据失败")
    
    def _save_users(self):
        """保存用户数据"""
        try:
            data = {}
            for username, user in self._users.items():
                data[username] = {
                    "password": user.password_hash,
                    "role": user.role,
                    "display_name": user.display_name,
                    "email": user.email,
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                    "is_active": user.is_active,
                    "custom_permissions": user.custom_permissions,
                    "denied_permissions": user.denied_permissions,
                }
            with open(self._users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("保存用户数据失败")
    
    def set_current_user(self, username: str) -> bool:
        """设置当前用户"""
        if username in self._users:
            self._current_user = self._users[username]
            return True
        return False
    
    def get_current_user(self) -> Optional[User]:
        """获取当前用户"""
        return self._current_user
    
    def clear_current_user(self):
        """清除当前用户（登出）"""
        self._current_user = None
    
    def get_user(self, username: str) -> Optional[User]:
        """获取用户"""
        return self._users.get(username)
    
    def get_all_users(self) -> List[User]:
        """获取所有用户"""
        return list(self._users.values())
    
    def create_user(self, username: str, password_hash: str, role: str = "readonly",
                   display_name: str = "", email: str = "") -> bool:
        """创建用户"""
        if username in self._users:
            return False
        
        from datetime import datetime
        self._users[username] = User(
            username=username,
            password_hash=password_hash,
            role=role,
            display_name=display_name or username,
            email=email,
            created_at=datetime.now().isoformat(),
            is_active=True,
        )
        self._save_users()
        return True
    
    def update_user(self, username: str, **kwargs) -> bool:
        """更新用户"""
        if username not in self._users:
            return False
        
        user = self._users[username]
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        self._save_users()
        return True
    
    def delete_user(self, username: str) -> bool:
        """删除用户"""
        if username not in self._users:
            return False
        
        del self._users[username]
        self._save_users()
        return True
    
    def set_user_role(self, username: str, role: str) -> bool:
        """设置用户角色"""
        return self.update_user(username, role=role)
    
    def get_user_permissions(self, username: str = None) -> Set[Permission]:
        """获取用户权限"""
        user = self._users.get(username) if username else self._current_user
        if not user:
            return set()
        
        # 获取角色权限
        try:
            role = Role(user.role)
            permissions = ROLE_PERMISSIONS.get(role, set()).copy()
        except ValueError:
            permissions = set()
        
        # 添加自定义权限
        for perm_str in user.custom_permissions:
            try:
                permissions.add(Permission(perm_str))
            except ValueError:
                pass
        
        # 移除禁止权限
        for perm_str in user.denied_permissions:
            try:
                permissions.discard(Permission(perm_str))
            except ValueError:
                pass
        
        return permissions
    
    def has_permission(self, permission: Permission, username: str = None) -> bool:
        """检查用户是否有指定权限"""
        permissions = self.get_user_permissions(username)
        return permission in permissions
    
    def check_permission(self, permission: Permission, username: str = None) -> bool:
        """检查权限（别名）"""
        return self.has_permission(permission, username)
    
    def require_permission(self, permission: Permission, username: str = None) -> bool:
        """要求权限（如果没有则抛出异常）"""
        if not self.has_permission(permission, username):
            raise PermissionError(f"缺少权限: {permission.value}")
        return True
    
    def add_custom_permission(self, username: str, permission: Permission) -> bool:
        """添加自定义权限"""
        if username not in self._users:
            return False
        
        user = self._users[username]
        if permission.value not in user.custom_permissions:
            user.custom_permissions.append(permission.value)
            self._save_users()
        return True
    
    def remove_custom_permission(self, username: str, permission: Permission) -> bool:
        """移除自定义权限"""
        if username not in self._users:
            return False
        
        user = self._users[username]
        if permission.value in user.custom_permissions:
            user.custom_permissions.remove(permission.value)
            self._save_users()
        return True
    
    def deny_permission(self, username: str, permission: Permission) -> bool:
        """禁止权限"""
        if username not in self._users:
            return False
        
        user = self._users[username]
        if permission.value not in user.denied_permissions:
            user.denied_permissions.append(permission.value)
            self._save_users()
        return True
    
    def allow_permission(self, username: str, permission: Permission) -> bool:
        """取消禁止权限"""
        if username not in self._users:
            return False
        
        user = self._users[username]
        if permission.value in user.denied_permissions:
            user.denied_permissions.remove(permission.value)
            self._save_users()
        return True
    
    @staticmethod
    def get_role_display_name(role: str) -> str:
        """获取角色显示名称"""
        names = {
            "admin": "管理员",
            "cs": "客服",
        }
        return names.get(role, role)
    
    @staticmethod
    def get_all_roles() -> List[tuple]:
        """获取所有角色"""
        return [
            ("admin", "管理员"),
            ("cs", "客服"),
        ]
    
    def is_admin(self, username: str = None) -> bool:
        """检查用户是否为管理员"""
        user = self._users.get(username) if username else self._current_user
        if not user:
            return False
        return user.role == "admin"
    
    def get_visible_pages(self, username: str = None) -> List[str]:
        """获取用户可见的页面列表
        
        管理员：所有页面
        客服：人工客服、商品管理
        """
        user = self._users.get(username) if username else self._current_user
        if not user:
            return []
        
        if user.role == "admin":
            # 管理员可见所有页面
            return [
                "workbench",      # AI工作台
                "human_service",  # 人工客服
                "knowledge",      # 知识库管理
                "product",        # 商品管理
                "statistics",     # 数据统计
                "performance",    # 性能监控
                "log",            # 日志管理
                "user",           # 用户管理
            ]
        else:
            # 客服只能看到人工客服和商品管理
            return [
                "human_service",  # 人工客服
                "product",        # 商品管理
            ]
    
    @staticmethod
    def get_permission_display_name(permission: Permission) -> str:
        """获取权限显示名称"""
        names = {
            Permission.CHAT_VIEW: "查看对话",
            Permission.CHAT_CREATE: "创建对话",
            Permission.CHAT_DELETE: "删除对话",
            Permission.KNOWLEDGE_VIEW: "查看知识库",
            Permission.KNOWLEDGE_CREATE: "创建知识",
            Permission.KNOWLEDGE_EDIT: "编辑知识",
            Permission.KNOWLEDGE_DELETE: "删除知识",
            Permission.KNOWLEDGE_REBUILD_INDEX: "重建索引",
            Permission.PRODUCT_VIEW: "查看商品",
            Permission.PRODUCT_CREATE: "创建商品",
            Permission.PRODUCT_EDIT: "编辑商品",
            Permission.PRODUCT_DELETE: "删除商品",
            Permission.USER_VIEW: "查看用户",
            Permission.USER_CREATE: "创建用户",
            Permission.USER_EDIT: "编辑用户",
            Permission.USER_DELETE: "删除用户",
            Permission.SETTINGS_VIEW: "查看设置",
            Permission.SETTINGS_EDIT: "编辑设置",
            Permission.BACKUP_CREATE: "创建备份",
            Permission.BACKUP_RESTORE: "恢复备份",
            Permission.STATISTICS_VIEW: "查看统计",
        }
        return names.get(permission, permission.value)


def get_permission_manager() -> PermissionManager:
    """获取权限管理器单例"""
    return PermissionManager()


def require_permission(permission: Permission):
    """权限检查装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            manager = get_permission_manager()
            if not manager.has_permission(permission):
                raise PermissionError(f"缺少权限: {permission.value}")
            return func(*args, **kwargs)
        return wrapper
    return decorator
