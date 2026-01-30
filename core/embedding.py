# -*- coding: utf-8 -*-
"""
Embedding模块 - 调用硅基流动API进行文本向量化

优化内容 (v2.2.0):
- 细化异常处理
- 添加指数退避重试机制
- 集成API限流保护
- 批处理失败时继续处理其他批次
"""

import time
import random
import requests
import logging
from typing import List, Optional, Tuple
from requests.exceptions import RequestException, Timeout, ConnectionError
from core.config import Config
from core.rate_limiter import RateLimiter
from core.performance import PerformanceMonitor


logger = logging.getLogger(__name__)


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
    """计算指数退避延迟时间"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = delay * 0.25 * (random.random() * 2 - 1)
    return max(0.1, delay + jitter)


class EmbeddingClient:
    """Embedding客户端 - 支持硅基流动API"""
    
    _instance = None
    
    # 支持的Embedding模型映射
    MODEL_MAPPING = {
        "bge-large-zh": "BAAI/bge-large-zh-v1.5",
        "m3e-base": "BAAI/bge-m3",
        "text-embedding-ada-002": "BAAI/bge-large-zh-v1.5"  # 使用bge作为替代
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.config = Config()
        self._rate_limiter = RateLimiter()
        self._perf_monitor = PerformanceMonitor()
        self._dimension = 1024  # bge-large-zh-v1.5 维度
        
        # 重试配置
        self._max_retries = 3
        self._base_delay = 1.0
    
    @property
    def dimension(self) -> int:
        """获取向量维度"""
        return self._dimension
    
    def _get_model_name(self) -> str:
        """获取实际的模型名称"""
        ui_model = self.config.get("embedding_model", "bge-large-zh")
        return self.MODEL_MAPPING.get(ui_model, "BAAI/bge-large-zh-v1.5")
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        将单个文本向量化
        
        Args:
            text: 要向量化的文本
        
        Returns:
            向量列表，失败返回None
        """
        result = self.embed_texts([text])
        if result and len(result) > 0:
            return result[0]
        return None
    
    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        批量将文本向量化（自动分批处理，失败时继续处理其他批次）
        
        Args:
            texts: 要向量化的文本列表
        
        Returns:
            向量列表的列表，部分失败时对应位置为None
        """
        if not texts:
            return []
        
        api_key = self.config.get("api_key", "")
        if not api_key:
            logger.warning("未配置API密钥，无法进行向量化")
            return None
        
        # API最大批次大小
        BATCH_SIZE = 32
        
        # 如果数量小于批次大小，直接调用
        if len(texts) <= BATCH_SIZE:
            return self._embed_batch_with_retry(texts)
        
        # 分批处理
        all_embeddings: List[Optional[List[float]]] = [None] * len(texts)
        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE
        success_count = 0
        fail_count = 0
        
        logger.info("共 %s 条文本，分 %s 批处理（每批最多 %s 条）", len(texts), total_batches, BATCH_SIZE)
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(texts))
            batch = texts[start_idx:end_idx]
            batch_num = batch_idx + 1
            
            logger.info("处理批次 %s/%s", batch_num, total_batches)
            
            embeddings = self._embed_batch_with_retry(batch)
            
            if embeddings is None:
                # 批次失败，记录但继续处理
                logger.warning("批次 %s 失败，跳过继续处理", batch_num)
                fail_count += len(batch)
            else:
                # 批次成功，填充结果
                for i, emb in enumerate(embeddings):
                    all_embeddings[start_idx + i] = emb
                success_count += len(embeddings)
        
        logger.info("向量化完成: 成功 %s, 失败 %s", success_count, fail_count)
        
        # 如果全部失败，返回None
        if success_count == 0:
            return None
        
        return all_embeddings
    
    def _embed_batch_with_retry(self, texts: List[str]) -> Optional[List[List[float]]]:
        """带重试的批量向量化"""
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                # 限流检查
                if not self._rate_limiter.acquire_embedding(len(texts), timeout=60.0):
                    logger.warning("Embedding API限流：请求过于频繁")
                    if attempt < self._max_retries - 1:
                        time.sleep(exponential_backoff(attempt, self._base_delay))
                        continue
                    return None
                
                result = self._embed_batch(texts)
                if result is not None:
                    return result
                    
            except Exception as e:
                last_error = e
                logger.warning("Embedding批次处理失败（尝试 %d/%d）: %s", 
                             attempt + 1, self._max_retries, str(e))
            
            # 重试前等待
            if attempt < self._max_retries - 1:
                delay = exponential_backoff(attempt, self._base_delay)
                time.sleep(delay)
        
        if last_error:
            logger.error("Embedding批次处理最终失败: %s", str(last_error))
        return None
    
    def _embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """处理单个批次的embedding（细化异常处理）"""
        import time as time_module
        start_time = time_module.perf_counter()
        success = False
        
        api_key = self.config.get("api_key", "")
        api_base_url = self.config.get("api_base_url", "") or "https://api.siliconflow.cn/v1"
        model = self._get_model_name()
        
        url = f"{api_base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "input": texts,
            "encoding_format": "float"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                embeddings = [item["embedding"] for item in result["data"]]
                if embeddings and len(embeddings) > 0:
                    self._dimension = len(embeddings[0])
                success = True
                return embeddings
            
            elif response.status_code == 401:
                logger.error("Embedding API密钥无效")
                return None
            
            elif response.status_code == 429:
                logger.warning("Embedding API限流，稍后重试")
                raise Exception("API限流")
            
            elif response.status_code >= 500:
                logger.warning("Embedding API服务器错误: %s", response.status_code)
                raise Exception(f"服务器错误 {response.status_code}")
            
            else:
                logger.warning("Embedding API调用失败: %s - %s", response.status_code, response.text)
                return None
                
        except Timeout:
            logger.warning("Embedding API调用超时")
            raise Exception("请求超时")
        
        except ConnectionError:
            logger.warning("Embedding API网络连接失败")
            raise Exception("网络连接失败")
        
        except RequestException as e:
            logger.warning("Embedding API网络错误: %s", str(e))
            raise Exception(f"网络错误: {str(e)}")
        
        finally:
            # 记录性能指标
            duration = time_module.perf_counter() - start_time
            self._perf_monitor.record("embedding_api", duration, success, {
                "batch_size": len(texts),
                "model": model
            })
    
    def is_available(self) -> bool:
        """检查Embedding服务是否可用"""
        api_key = self.config.get("api_key", "")
        return bool(api_key)
