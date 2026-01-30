# -*- coding: utf-8 -*-
"""
UI工具模块
提供UI响应性优化工具
"""

import time
import logging
from typing import Callable, Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)

# 尝试导入Qt组件
try:
    from PySide6.QtCore import QTimer, QObject, Signal, QEvent
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


class ProgressThrottler:
    """进度更新节流器
    
    限制进度回调的调用频率，避免UI频繁更新导致卡顿。
    
    用法:
        throttler = ProgressThrottler(callback, min_interval=0.1)
        for i in range(10000):
            throttler.update("处理中", i, 10000)
        throttler.finish()  # 确保最后一次更新被发送
    """
    
    def __init__(self, callback: Callable[[str, int, int], None], 
                 min_interval: float = 0.1,
                 min_progress_change: float = 0.01):
        """
        Args:
            callback: 原始进度回调函数
            min_interval: 最小更新间隔（秒），默认100ms
            min_progress_change: 最小进度变化比例，默认1%
        """
        self._callback = callback
        self._min_interval = min_interval
        self._min_progress_change = min_progress_change
        self._last_update_time = 0.0
        self._last_progress = -1.0
        self._last_stage = ""
        self._pending_update: Optional[tuple] = None
    
    def update(self, stage: str, current: int, total: int) -> bool:
        """更新进度（带节流）
        
        Args:
            stage: 阶段名称
            current: 当前进度
            total: 总数
        
        Returns:
            是否实际发送了更新
        """
        if not self._callback:
            return False
        
        now = time.time()
        progress = current / max(total, 1)
        
        # 保存待处理的更新（用于finish时发送）
        self._pending_update = (stage, current, total)
        
        # 检查是否需要更新
        should_update = False
        
        # 阶段变化时立即更新
        if stage != self._last_stage:
            should_update = True
        # 进度完成时立即更新
        elif current >= total:
            should_update = True
        # 时间间隔足够
        elif now - self._last_update_time >= self._min_interval:
            # 进度变化足够大
            if abs(progress - self._last_progress) >= self._min_progress_change:
                should_update = True
        
        if should_update:
            self._callback(stage, current, total)
            self._last_update_time = now
            self._last_progress = progress
            self._last_stage = stage
            self._pending_update = None
            return True
        
        return False
    
    def finish(self):
        """完成进度更新，确保最后一次更新被发送"""
        if self._pending_update and self._callback:
            self._callback(*self._pending_update)
            self._pending_update = None
    
    def reset(self):
        """重置节流器状态"""
        self._last_update_time = 0.0
        self._last_progress = -1.0
        self._last_stage = ""
        self._pending_update = None


class BatchUpdater:
    """批量更新器
    
    收集多次更新请求，合并为一次UI更新。
    
    用法:
        updater = BatchUpdater(update_ui_func, interval=100)
        for item in items:
            updater.request_update(item)
        updater.flush()  # 强制执行待处理的更新
    """
    
    def __init__(self, update_func: Callable[[], None], interval_ms: int = 100):
        """
        Args:
            update_func: 更新函数
            interval_ms: 批量更新间隔（毫秒）
        """
        self._update_func = update_func
        self._interval_ms = interval_ms
        self._pending = False
        self._timer: Optional[Any] = None
        
        if QT_AVAILABLE:
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.setInterval(interval_ms)
            self._timer.timeout.connect(self._do_update)
    
    def request_update(self):
        """请求更新（会被合并）"""
        self._pending = True
        
        if self._timer and not self._timer.isActive():
            self._timer.start()
    
    def _do_update(self):
        """执行更新"""
        if self._pending:
            self._pending = False
            if self._update_func:
                try:
                    self._update_func()
                except Exception as e:
                    logger.exception(f"批量更新执行失败: {e}")
    
    def flush(self):
        """强制执行待处理的更新"""
        if self._timer:
            self._timer.stop()
        self._do_update()
    
    def cancel(self):
        """取消待处理的更新"""
        self._pending = False
        if self._timer:
            self._timer.stop()


if QT_AVAILABLE:
    class DeferredUpdater(QObject):
        """延迟更新器（Qt版本）
        
        使用QTimer.singleShot延迟执行更新，避免阻塞UI线程。
        """
        
        update_requested = Signal()
        
        def __init__(self, update_func: Callable[[], None], delay_ms: int = 0, parent=None):
            """
            Args:
                update_func: 更新函数
                delay_ms: 延迟时间（毫秒），0表示下一个事件循环
                parent: Qt父对象
            """
            super().__init__(parent)
            self._update_func = update_func
            self._delay_ms = delay_ms
            self._pending = False
            
            self.update_requested.connect(self._schedule_update)
        
        def request_update(self):
            """请求更新"""
            if not self._pending:
                self._pending = True
                self.update_requested.emit()
        
        def _schedule_update(self):
            """调度更新"""
            QTimer.singleShot(self._delay_ms, self._do_update)
        
        def _do_update(self):
            """执行更新"""
            self._pending = False
            if self._update_func:
                try:
                    self._update_func()
                except Exception as e:
                    logger.exception(f"延迟更新执行失败: {e}")


if QT_AVAILABLE:
    class FontPointSizeNormalizer(QObject):
        def eventFilter(self, obj, event):
            from PySide6.QtWidgets import QWidget, QApplication

            if isinstance(obj, QWidget):
                et = event.type()
                if et in (QEvent.Polish, QEvent.Show, QEvent.Enter, QEvent.ToolTip, QEvent.ToolTipChange):
                    font = obj.font()
                    if font.pointSize() <= 0:
                        pixel = font.pixelSize()
                        if pixel > 0:
                            dpi = obj.logicalDpiY()
                            if dpi <= 0:
                                screen = QApplication.primaryScreen()
                                dpi = screen.logicalDotsPerInchY() if screen else 96.0
                            point = int(round(pixel * 72.0 / float(dpi)))
                            if point <= 0:
                                point = QApplication.font().pointSize()
                                if point <= 0:
                                    point = 10
                        else:
                            point = QApplication.font().pointSize()
                            if point <= 0:
                                point = 10

                        font.setPointSize(point)
                        obj.setFont(font)

            return False


def install_font_point_size_normalizer(app):
    if not QT_AVAILABLE or not app:
        return None
    normalizer = FontPointSizeNormalizer(app)
    app.installEventFilter(normalizer)
    return normalizer


def throttle(min_interval: float = 0.1):
    """函数节流装饰器
    
    限制函数的调用频率。
    
    用法:
        @throttle(0.1)  # 最多每100ms调用一次
        def update_progress(value):
            ...
    """
    def decorator(func: Callable):
        last_call_time = [0.0]
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            if now - last_call_time[0] >= min_interval:
                last_call_time[0] = now
                return func(*args, **kwargs)
            return None
        
        return wrapper
    return decorator


def debounce(delay: float = 0.1):
    """函数防抖装饰器
    
    延迟执行函数，如果在延迟期间再次调用则重新计时。
    注意：这个简单实现不支持Qt事件循环，仅用于同步场景。
    
    用法:
        @debounce(0.1)  # 停止调用100ms后才执行
        def save_data():
            ...
    """
    def decorator(func: Callable):
        last_call_time = [0.0]
        pending_args = [None]
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            last_call_time[0] = now
            pending_args[0] = (args, kwargs)
            
            # 简单实现：检查是否应该执行
            # 实际使用中应该配合定时器
            return None
        
        def execute_if_ready():
            """检查并执行（需要外部定时调用）"""
            if pending_args[0] is None:
                return None
            
            now = time.time()
            if now - last_call_time[0] >= delay:
                args, kwargs = pending_args[0]
                pending_args[0] = None
                return func(*args, **kwargs)
            return None
        
        wrapper.execute_if_ready = execute_if_ready
        return wrapper
    return decorator


def create_progress_callback(callback: Callable[[str, int, int], None],
                            min_interval: float = 0.1,
                            min_progress_change: float = 0.01) -> Callable[[str, int, int], None]:
    """创建带节流的进度回调
    
    Args:
        callback: 原始回调函数
        min_interval: 最小更新间隔（秒）
        min_progress_change: 最小进度变化比例
    
    Returns:
        节流后的回调函数
    """
    throttler = ProgressThrottler(callback, min_interval, min_progress_change)
    
    def throttled_callback(stage: str, current: int, total: int):
        throttler.update(stage, current, total)
        # 完成时确保发送最后更新
        if current >= total:
            throttler.finish()
    
    return throttled_callback
