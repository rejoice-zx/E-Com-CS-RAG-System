# -*- coding: utf-8 -*-
"""
日志管理模块 - 支持日志轮转、分级记录

优化内容 (v2.3.0):
- 使用 RotatingFileHandler 实现日志轮转
- 按模块分级记录（DEBUG/INFO/WARNING/ERROR）
- 支持控制台和文件双输出
- 日志文件自动清理
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional


class LogManager:
    """日志管理器"""
    
    _instance = None
    _initialized = False
    
    # 日志级别映射
    LEVEL_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._log_dir = self._get_log_dir()
        self._log_file = os.path.join(self._log_dir, "app.log")
        self._error_file = os.path.join(self._log_dir, "error.log")
        
        # 默认配置
        self._max_bytes = 5 * 1024 * 1024  # 5MB
        self._backup_count = 5  # 保留5个备份
        self._console_level = logging.INFO
        self._file_level = logging.DEBUG
        
        self._setup_logging()
    
    def _get_log_dir(self) -> str:
        """获取日志目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    
    def _setup_logging(self):
        """配置日志系统"""
        # 获取根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # 清除现有处理器
        root_logger.handlers.clear()
        
        # 日志格式
        detailed_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        simple_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self._console_level)
        console_handler.setFormatter(simple_format)
        root_logger.addHandler(console_handler)
        
        # 文件处理器（所有日志）
        file_handler = RotatingFileHandler(
            self._log_file,
            maxBytes=self._max_bytes,
            backupCount=self._backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self._file_level)
        file_handler.setFormatter(detailed_format)
        root_logger.addHandler(file_handler)
        
        # 错误日志处理器（仅ERROR及以上）
        error_handler = RotatingFileHandler(
            self._error_file,
            maxBytes=self._max_bytes,
            backupCount=self._backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_format)
        root_logger.addHandler(error_handler)
        
        # 设置第三方库日志级别
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("PySide6").setLevel(logging.WARNING)
        
        logging.info("日志系统初始化完成，日志目录: %s", self._log_dir)
    
    def set_level(self, level: str, target: str = "all"):
        """设置日志级别
        
        Args:
            level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
            target: 目标（console/file/all）
        """
        log_level = self.LEVEL_MAP.get(level.upper(), logging.INFO)
        root_logger = logging.getLogger()
        
        for handler in root_logger.handlers:
            if target == "all":
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                    handler.setLevel(log_level)
                elif isinstance(handler, RotatingFileHandler) and handler.baseFilename == self._log_file:
                    handler.setLevel(log_level)
            elif target == "console" and isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                handler.setLevel(log_level)
            elif target == "file" and isinstance(handler, RotatingFileHandler) and handler.baseFilename == self._log_file:
                handler.setLevel(log_level)
    
    def get_log_files(self) -> list:
        """获取所有日志文件"""
        files = []
        for filename in os.listdir(self._log_dir):
            if filename.endswith('.log'):
                filepath = os.path.join(self._log_dir, filename)
                stat = os.stat(filepath)
                files.append({
                    "name": filename,
                    "path": filepath,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        return sorted(files, key=lambda x: x["modified"], reverse=True)
    
    def read_log(self, filename: str, lines: int = 100) -> str:
        """读取日志文件最后N行"""
        filepath = os.path.join(self._log_dir, filename)
        if not os.path.exists(filepath):
            return ""
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            return f"读取日志失败: {e}"
    
    def clear_logs(self, keep_days: int = 7) -> int:
        """清理旧日志文件
        
        Args:
            keep_days: 保留最近N天的日志
        
        Returns:
            删除的文件数量
        """
        import time
        
        deleted = 0
        cutoff = time.time() - (keep_days * 24 * 60 * 60)
        
        for filename in os.listdir(self._log_dir):
            filepath = os.path.join(self._log_dir, filename)
            if os.path.isfile(filepath):
                if os.path.getmtime(filepath) < cutoff:
                    try:
                        os.remove(filepath)
                        deleted += 1
                    except:
                        pass
        
        return deleted
    
    @property
    def log_dir(self) -> str:
        """获取日志目录"""
        return self._log_dir


def setup_logging():
    """初始化日志系统（便捷函数）"""
    return LogManager()


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器"""
    return logging.getLogger(name)
