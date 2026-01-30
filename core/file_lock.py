# -*- coding: utf-8 -*-
"""
文件锁模块 - 跨平台文件锁实现
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 根据平台导入不同的锁实现
if os.name == 'nt':
    # Windows
    import msvcrt
    
    class FileLock:
        """Windows文件锁"""
        
        def __init__(self, filepath: str, timeout: float = 10.0):
            self.filepath = filepath
            self.timeout = timeout
            self.lockfile = filepath + '.lock'
            self.fd: Optional[int] = None
        
        def acquire(self) -> bool:
            """获取锁"""
            start_time = time.time()
            
            while True:
                try:
                    # 创建锁文件
                    self.fd = os.open(self.lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    
                    # 锁定文件
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                    logger.debug(f"获取文件锁成功: {self.lockfile}")
                    return True
                    
                except (OSError, IOError) as e:
                    # 锁文件已存在或被锁定
                    if time.time() - start_time >= self.timeout:
                        logger.warning(f"获取文件锁超时: {self.lockfile}")
                        return False
                    
                    time.sleep(0.1)
        
        def release(self):
            """释放锁"""
            if self.fd is not None:
                try:
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                    os.close(self.fd)
                    self.fd = None
                    
                    # 删除锁文件
                    if os.path.exists(self.lockfile):
                        os.remove(self.lockfile)
                    
                    logger.debug(f"释放文件锁成功: {self.lockfile}")
                except Exception as e:
                    logger.exception(f"释放文件锁失败: {self.lockfile}")
        
        def __enter__(self):
            if not self.acquire():
                raise TimeoutError(f"无法获取文件锁: {self.lockfile}")
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.release()

else:
    # Unix/Linux/Mac
    import fcntl
    
    class FileLock:
        """Unix文件锁"""
        
        def __init__(self, filepath: str, timeout: float = 10.0):
            self.filepath = filepath
            self.timeout = timeout
            self.lockfile = filepath + '.lock'
            self.fd: Optional[int] = None
        
        def acquire(self) -> bool:
            """获取锁"""
            start_time = time.time()
            
            while True:
                try:
                    # 创建锁文件
                    self.fd = os.open(self.lockfile, os.O_CREAT | os.O_RDWR)
                    
                    # 尝试获取排他锁（非阻塞）
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.debug(f"获取文件锁成功: {self.lockfile}")
                    return True
                    
                except (OSError, IOError) as e:
                    # 锁被占用
                    if time.time() - start_time >= self.timeout:
                        logger.warning(f"获取文件锁超时: {self.lockfile}")
                        if self.fd is not None:
                            os.close(self.fd)
                            self.fd = None
                        return False
                    
                    time.sleep(0.1)
        
        def release(self):
            """释放锁"""
            if self.fd is not None:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
                    os.close(self.fd)
                    self.fd = None
                    
                    # 删除锁文件
                    if os.path.exists(self.lockfile):
                        os.remove(self.lockfile)
                    
                    logger.debug(f"释放文件锁成功: {self.lockfile}")
                except Exception as e:
                    logger.exception(f"释放文件锁失败: {self.lockfile}")
        
        def __enter__(self):
            if not self.acquire():
                raise TimeoutError(f"无法获取文件锁: {self.lockfile}")
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.release()


def with_file_lock(filepath: str, timeout: float = 10.0):
    """文件锁装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            lock = FileLock(filepath, timeout)
            with lock:
                return func(*args, **kwargs)
        return wrapper
    return decorator
