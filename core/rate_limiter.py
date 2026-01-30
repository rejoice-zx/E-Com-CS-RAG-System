# -*- coding: utf-8 -*-
"""
API限流模块 - 令牌桶算法实现
"""

import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    """令牌桶限流器
    
    使用令牌桶算法控制API请求频率，防止触发服务商限制。
    
    Args:
        rate: 每秒生成的令牌数（即允许的请求频率）
        capacity: 桶的最大容量（允许的突发请求数）
    """
    
    def __init__(self, rate: float = 2.0, capacity: int = 10):
        self._rate = max(0.1, rate)  # 每秒生成的令牌数
        self._capacity = max(1, capacity)  # 桶容量
        self._tokens = float(capacity)  # 当前令牌数
        self._last_time = time.monotonic()
        self._lock = threading.Lock()
    
    def _refill(self):
        """补充令牌"""
        now = time.monotonic()
        elapsed = now - self._last_time
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_time = now
    
    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """获取令牌
        
        Args:
            tokens: 需要的令牌数
            timeout: 最大等待时间（秒），None表示不等待
        
        Returns:
            是否成功获取令牌
        """
        if tokens <= 0:
            return True
        
        start_time = time.monotonic()
        
        while True:
            with self._lock:
                self._refill()
                
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
            
            # 检查是否超时
            if timeout is None:
                return False
            
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                return False
            
            # 计算需要等待的时间
            with self._lock:
                wait_time = (tokens - self._tokens) / self._rate
            
            # 等待一小段时间后重试
            sleep_time = min(wait_time, timeout - elapsed, 0.1)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def try_acquire(self, tokens: int = 1) -> bool:
        """尝试获取令牌（不等待）"""
        return self.acquire(tokens, timeout=None)
    
    @property
    def available_tokens(self) -> float:
        """当前可用令牌数"""
        with self._lock:
            self._refill()
            return self._tokens


class RateLimiter:
    """API限流管理器
    
    为不同类型的API调用提供独立的限流控制。
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 不同API的限流器
        # Chat API: 每秒2次，突发最多5次
        self._chat_limiter = TokenBucket(rate=2.0, capacity=5)
        
        # Embedding API: 每秒3次，突发最多10次（批量处理需要更高频率）
        self._embedding_limiter = TokenBucket(rate=3.0, capacity=10)
        
        # 通用API: 每秒5次，突发最多15次
        self._general_limiter = TokenBucket(rate=5.0, capacity=15)
        
        logger.info("API限流器已初始化")
    
    def acquire_chat(self, timeout: float = 30.0) -> bool:
        """获取Chat API调用许可"""
        return self._chat_limiter.acquire(1, timeout)
    
    def acquire_embedding(self, batch_size: int = 1, timeout: float = 60.0) -> bool:
        """获取Embedding API调用许可
        
        Args:
            batch_size: 批次大小，用于计算需要的令牌数
            timeout: 最大等待时间
        """
        # 每32条文本消耗1个令牌
        tokens = max(1, (batch_size + 31) // 32)
        return self._embedding_limiter.acquire(tokens, timeout)
    
    def acquire_general(self, timeout: float = 10.0) -> bool:
        """获取通用API调用许可"""
        return self._general_limiter.acquire(1, timeout)
    
    def try_acquire_chat(self) -> bool:
        """尝试获取Chat API调用许可（不等待）"""
        return self._chat_limiter.try_acquire(1)
    
    def try_acquire_embedding(self, batch_size: int = 1) -> bool:
        """尝试获取Embedding API调用许可（不等待）"""
        tokens = max(1, (batch_size + 31) // 32)
        return self._embedding_limiter.try_acquire(tokens)
    
    def configure(self, chat_rate: float = None, embedding_rate: float = None):
        """配置限流参数
        
        Args:
            chat_rate: Chat API每秒请求数
            embedding_rate: Embedding API每秒请求数
        """
        if chat_rate is not None:
            self._chat_limiter = TokenBucket(rate=chat_rate, capacity=max(5, int(chat_rate * 3)))
        if embedding_rate is not None:
            self._embedding_limiter = TokenBucket(rate=embedding_rate, capacity=max(10, int(embedding_rate * 3)))
        logger.info("限流参数已更新: chat_rate=%s, embedding_rate=%s", chat_rate, embedding_rate)
