# -*- coding: utf-8 -*-
"""
配置热更新模块
使用 QFileSystemWatcher 监听配置文件变化，实现配置热更新
"""

import os
import json
import logging
from typing import Callable, Dict, List, Optional, Set
from functools import wraps

logger = logging.getLogger(__name__)

# 尝试导入Qt组件
try:
    from PySide6.QtCore import QObject, Signal, QFileSystemWatcher, QTimer
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    logger.warning("PySide6未安装，配置热更新功能不可用")


class ConfigChangeEvent:
    """配置变更事件"""
    
    def __init__(self, file_path: str, old_config: dict, new_config: dict):
        self.file_path = file_path
        self.old_config = old_config
        self.new_config = new_config
        self._changed_keys: Optional[Set[str]] = None
    
    @property
    def changed_keys(self) -> Set[str]:
        """获取变更的配置键"""
        if self._changed_keys is None:
            self._changed_keys = set()
            all_keys = set(self.old_config.keys()) | set(self.new_config.keys())
            for key in all_keys:
                old_val = self.old_config.get(key)
                new_val = self.new_config.get(key)
                if old_val != new_val:
                    self._changed_keys.add(key)
        return self._changed_keys
    
    def get_old_value(self, key: str):
        """获取旧值"""
        return self.old_config.get(key)
    
    def get_new_value(self, key: str):
        """获取新值"""
        return self.new_config.get(key)
    
    def is_changed(self, key: str) -> bool:
        """检查指定键是否变更"""
        return key in self.changed_keys


if QT_AVAILABLE:
    class ConfigWatcher(QObject):
        """配置文件监听器（Qt版本）"""
        
        # 配置变更信号
        config_changed = Signal(object)  # ConfigChangeEvent
        # 特定键变更信号
        key_changed = Signal(str, object, object)  # key, old_value, new_value
        
        _instance = None
        
        def __new__(cls, *args, **kwargs):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
        
        def __init__(self, parent=None):
            if hasattr(self, '_initialized') and self._initialized:
                return
            
            super().__init__(parent)
            self._initialized = True
            
            self._watcher = QFileSystemWatcher(self)
            self._watched_files: Dict[str, dict] = {}  # path -> last_config
            self._callbacks: Dict[str, List[Callable]] = {}  # key -> callbacks
            self._global_callbacks: List[Callable] = []
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.setInterval(100)  # 100ms防抖
            self._pending_changes: List[str] = []
            
            # 连接信号
            self._watcher.fileChanged.connect(self._on_file_changed)
            self._debounce_timer.timeout.connect(self._process_pending_changes)
            
            logger.info("配置监听器初始化完成")
        
        def watch(self, file_path: str) -> bool:
            """添加监听文件"""
            if not os.path.exists(file_path):
                logger.warning(f"配置文件不存在: {file_path}")
                return False
            
            abs_path = os.path.abspath(file_path)
            
            if abs_path in self._watched_files:
                logger.debug(f"文件已在监听列表中: {abs_path}")
                return True
            
            # 读取当前配置作为基准
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    current_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"读取配置文件失败: {e}")
                current_config = {}
            
            self._watched_files[abs_path] = current_config
            
            if self._watcher.addPath(abs_path):
                logger.info(f"开始监听配置文件: {abs_path}")
                return True
            else:
                logger.error(f"添加文件监听失败: {abs_path}")
                del self._watched_files[abs_path]
                return False
        
        def unwatch(self, file_path: str) -> bool:
            """移除监听文件"""
            abs_path = os.path.abspath(file_path)
            
            if abs_path not in self._watched_files:
                return False
            
            self._watcher.removePath(abs_path)
            del self._watched_files[abs_path]
            logger.info(f"停止监听配置文件: {abs_path}")
            return True
        
        def on_change(self, key: Optional[str] = None):
            """装饰器：注册配置变更回调
            
            用法:
                @config_watcher.on_change("theme")
                def on_theme_change(old_value, new_value):
                    print(f"主题从 {old_value} 变更为 {new_value}")
                
                @config_watcher.on_change()  # 监听所有变更
                def on_any_change(event: ConfigChangeEvent):
                    print(f"配置变更: {event.changed_keys}")
            """
            def decorator(func: Callable):
                if key is None:
                    self._global_callbacks.append(func)
                else:
                    if key not in self._callbacks:
                        self._callbacks[key] = []
                    self._callbacks[key].append(func)
                
                @wraps(func)
                def wrapper(*args, **kwargs):
                    return func(*args, **kwargs)
                return wrapper
            return decorator
        
        def register_callback(self, callback: Callable, key: Optional[str] = None):
            """注册配置变更回调（非装饰器方式）"""
            if key is None:
                self._global_callbacks.append(callback)
            else:
                if key not in self._callbacks:
                    self._callbacks[key] = []
                self._callbacks[key].append(callback)
        
        def unregister_callback(self, callback: Callable, key: Optional[str] = None):
            """取消注册回调"""
            if key is None:
                if callback in self._global_callbacks:
                    self._global_callbacks.remove(callback)
            else:
                if key in self._callbacks and callback in self._callbacks[key]:
                    self._callbacks[key].remove(callback)
        
        def _on_file_changed(self, path: str):
            """文件变更处理（带防抖）"""
            if path not in self._pending_changes:
                self._pending_changes.append(path)
            
            # 重置防抖定时器
            self._debounce_timer.stop()
            self._debounce_timer.start()
            
            # 重新添加监听（某些系统上文件修改后会移除监听）
            if path not in self._watcher.files():
                self._watcher.addPath(path)
        
        def _process_pending_changes(self):
            """处理待处理的文件变更"""
            paths = self._pending_changes.copy()
            self._pending_changes.clear()
            
            for path in paths:
                self._handle_file_change(path)
        
        def _handle_file_change(self, path: str):
            """处理单个文件变更"""
            if path not in self._watched_files:
                return
            
            old_config = self._watched_files[path]
            
            # 读取新配置
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    new_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"读取变更后的配置文件失败: {e}")
                return
            
            # 更新缓存
            self._watched_files[path] = new_config
            
            # 创建变更事件
            event = ConfigChangeEvent(path, old_config, new_config)
            
            if not event.changed_keys:
                logger.debug(f"配置文件内容未变化: {path}")
                return
            
            logger.info(f"检测到配置变更: {event.changed_keys}")
            
            # 发送全局信号
            self.config_changed.emit(event)
            
            # 调用全局回调
            for callback in self._global_callbacks:
                try:
                    callback(event)
                except Exception as e:
                    logger.exception(f"配置变更回调执行失败: {e}")
            
            # 调用特定键的回调
            for key in event.changed_keys:
                old_val = event.get_old_value(key)
                new_val = event.get_new_value(key)
                
                # 发送键变更信号
                self.key_changed.emit(key, old_val, new_val)
                
                # 调用键回调
                if key in self._callbacks:
                    for callback in self._callbacks[key]:
                        try:
                            callback(old_val, new_val)
                        except Exception as e:
                            logger.exception(f"配置键 '{key}' 变更回调执行失败: {e}")
        
        def get_watched_files(self) -> List[str]:
            """获取监听的文件列表"""
            return list(self._watched_files.keys())
        
        def force_reload(self, file_path: Optional[str] = None):
            """强制重新加载配置"""
            if file_path:
                abs_path = os.path.abspath(file_path)
                if abs_path in self._watched_files:
                    self._handle_file_change(abs_path)
            else:
                for path in list(self._watched_files.keys()):
                    self._handle_file_change(path)

else:
    # 非Qt环境的简化实现
    class ConfigWatcher:
        """配置文件监听器（非Qt版本，仅提供接口兼容）"""
        
        _instance = None
        
        def __new__(cls, *args, **kwargs):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
        
        def __init__(self, parent=None):
            if hasattr(self, '_initialized') and self._initialized:
                return
            self._initialized = True
            self._watched_files: Dict[str, dict] = {}
            self._callbacks: Dict[str, List[Callable]] = {}
            self._global_callbacks: List[Callable] = []
            logger.warning("Qt不可用，配置热更新功能受限")
        
        def watch(self, file_path: str) -> bool:
            """添加监听文件（非Qt环境下仅记录）"""
            abs_path = os.path.abspath(file_path)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        self._watched_files[abs_path] = json.load(f)
                    return True
                except:
                    pass
            return False
        
        def unwatch(self, file_path: str) -> bool:
            abs_path = os.path.abspath(file_path)
            if abs_path in self._watched_files:
                del self._watched_files[abs_path]
                return True
            return False
        
        def on_change(self, key: Optional[str] = None):
            def decorator(func: Callable):
                return func
            return decorator
        
        def register_callback(self, callback: Callable, key: Optional[str] = None):
            pass
        
        def unregister_callback(self, callback: Callable, key: Optional[str] = None):
            pass
        
        def get_watched_files(self) -> List[str]:
            return list(self._watched_files.keys())
        
        def force_reload(self, file_path: Optional[str] = None):
            pass


def get_config_watcher(parent=None) -> ConfigWatcher:
    """获取配置监听器单例"""
    return ConfigWatcher(parent)
