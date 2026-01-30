# -*- coding: utf-8 -*-
"""
API客户端模块 - 支持硅基流动(SiliconFlow) API

优化内容 (v2.2.0):
- 细化异常处理（区分网络错误、超时、API错误等）
- 添加指数退避重试机制
- 集成API限流保护
"""

import json
import random
import time
import requests
import logging
from typing import Optional, Callable, Tuple
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError
from core.config import Config
from core.rate_limiter import RateLimiter
from core.performance import PerformanceMonitor


logger = logging.getLogger(__name__)


class APIError(Exception):
    """API调用错误"""
    def __init__(self, message: str, status_code: int = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
    """计算指数退避延迟时间
    
    Args:
        attempt: 当前重试次数（从0开始）
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
    
    Returns:
        延迟时间（秒），带有随机抖动
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    # 添加随机抖动（±25%）
    jitter = delay * 0.25 * (random.random() * 2 - 1)
    return max(0.1, delay + jitter)


class APIClient:
    """API客户端类 - 支持硅基流动API"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        """初始化客户端"""
        self.config = Config()
        self._callback: Optional[Callable] = None
        self._rate_limiter = RateLimiter()
        self._perf_monitor = PerformanceMonitor()
        
        # 硅基流动API默认配置
        self._default_api_url = "https://api.siliconflow.cn/v1"
        self._default_model = "Qwen/Qwen3-8B"
        
        # 重试配置
        self._max_retries = 3
        self._base_delay = 1.0

    def is_configured(self) -> bool:
        """检查API是否已配置"""
        api_key = self.config.get("api_key", "")
        return bool(api_key)
    
    def set_response_callback(self, callback: Callable[[str], None]) -> None:
        """设置响应回调函数"""
        self._callback = callback
    
    def send_messages(self, messages: list, history_len: int = 0, context_len: int = 0) -> str:
        if self.is_configured():
            return self._call_api_messages(messages, history_len=history_len, context_len=context_len)

        last_user = ""
        for m in reversed(messages or []):
            if isinstance(m, dict) and m.get("role") == "user" and m.get("content"):
                last_user = str(m.get("content"))
                break
        return self._get_mock_response(last_user)

    def send_message(self, message: str, history: list = None, context: str = None) -> str:
        """
        发送消息并获取回复
        
        Args:
            message: 用户消息
            history: 历史消息列表，每项为 {"role": "user/assistant", "content": "..."}
            context: RAG检索到的上下文内容
        
        Returns:
            AI回复内容
        """
        from core.shared_data import (
            build_system_prompt,
            build_messages,
            trim_history,
            truncate_text,
        )

        max_history_messages = self.config.get("history_max_messages", 12)
        max_history_chars = self.config.get("history_max_chars", 6000)
        max_context_chars = self.config.get("context_max_chars", 4000)

        context_text = truncate_text(context, max_context_chars) if context else None
        system_prompt = build_system_prompt(context_text)
        trimmed_history = trim_history(history, max_history_messages, max_history_chars)
        messages = build_messages(system_prompt, message, trimmed_history)

        if self.is_configured():
            return self._call_api_messages(
                messages,
                history_len=len(trimmed_history),
                context_len=len(context_text) if context_text else 0,
            )

        return self._get_mock_response(message)
    
    def _call_api_messages(self, messages: list, history_len: int = 0, context_len: int = 0) -> str:
        """调用API（带重试和限流）"""
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                # 限流检查
                if not self._rate_limiter.acquire_chat(timeout=30.0):
                    logger.warning("API限流：请求过于频繁，请稍后重试")
                    return "抱歉，请求过于频繁，请稍后重试。"
                
                return self._do_api_call(messages, history_len, context_len)
                
            except APIError as e:
                last_error = e
                if not e.retryable or attempt >= self._max_retries - 1:
                    break
                
                delay = exponential_backoff(attempt, self._base_delay)
                logger.warning("API调用失败（尝试 %d/%d），%s秒后重试: %s", 
                             attempt + 1, self._max_retries, f"{delay:.1f}", str(e))
                time.sleep(delay)
                
            except Exception as e:
                last_error = e
                logger.exception("API调用异常")
                break
        
        # 所有重试都失败
        error_msg = str(last_error) if last_error else "未知错误"
        return f"抱歉，服务暂时不可用：{error_msg}"
    
    def _do_api_call(self, messages: list, history_len: int = 0, context_len: int = 0) -> str:
        """执行实际的API调用"""
        import time as time_module
        start_time = time_module.perf_counter()
        success = False
        
        api_url = self.config.get("api_base_url", "") or self._default_api_url
        api_key = self.config.get("api_key", "")
        model = self.config.get("model_name", "") or self._default_model
        max_tokens = self.config.get("max_tokens", 2048)
        temperature = self.config.get("temperature", 0.7)
        
        url = f"{api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }

        logger.info(
            "调用API: %s, 模型: %s, history_len=%s, context_len=%s",
            url,
            model,
            history_len,
            context_len,
        )
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # 根据状态码处理不同错误
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                logger.info("API回复成功，长度: %s", len(content))
                success = True
                return content
            
            elif response.status_code == 401:
                raise APIError("API密钥无效或已过期", response.status_code, retryable=False)
            
            elif response.status_code == 403:
                raise APIError("API访问被拒绝，请检查权限", response.status_code, retryable=False)
            
            elif response.status_code == 429:
                raise APIError("API请求过于频繁，已触发限流", response.status_code, retryable=True)
            
            elif response.status_code >= 500:
                raise APIError(f"服务器错误 ({response.status_code})", response.status_code, retryable=True)
            
            else:
                # 尝试解析错误信息
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                except:
                    error_msg = response.text
                raise APIError(f"API错误 ({response.status_code}): {error_msg}", response.status_code, retryable=False)
                
        except Timeout:
            raise APIError("请求超时，请稍后重试", retryable=True)
        
        except ConnectionError:
            raise APIError("网络连接失败，请检查网络", retryable=True)
        
        except json.JSONDecodeError:
            raise APIError("API返回数据格式错误", retryable=False)
        
        finally:
            # 记录性能指标
            duration = time_module.perf_counter() - start_time
            self._perf_monitor.record("chat_api", duration, success, {
                "model": model,
                "history_len": history_len,
                "context_len": context_len
            })
    
    def _get_mock_response(self, message: str) -> str:
        """生成模拟回复（未配置API时使用）"""
        
        mock_responses = {
            "退货": '关于退货问题，您可以在收到商品后7天内申请无理由退货。请确保商品完好、不影响二次销售。您可以在"我的订单"中找到对应订单，点击"申请退货"按钮进行操作。',
            "退款": "退款一般会在1-3个工作日内原路返回到您的支付账户。如果超过时间仍未收到，请检查您的账户明细，或联系您的银行确认。",
            "物流": "您可以在订单详情页查看物流信息。一般情况下，普通快递3-5天到达，加急快递1-2天到达。",
            "发货": "我们会在下单后24小时内发货（节假日顺延）。发货后您会收到短信通知。",
            "优惠": "目前我们有以下优惠活动：\n1. 新用户首单立减10元\n2. 满200减30\n3. 部分商品限时折扣",
            "尺码": "关于尺码选择，建议您参考商品详情页的尺码表。",
            "质量": "我们所有商品都经过严格质量检测。如有质量问题，请在收货后48小时内反馈。",
            "支付": "我们支持支付宝、微信支付、银联支付等多种支付方式。"
        }
        
        for keyword, response in mock_responses.items():
            if keyword in message:
                return response + "\n\n[提示：当前为模拟回复，请在设置中配置API密钥以获得更智能的回答]"
        
        return f"您好！关于您的问题，请在设置中配置API密钥以获得更智能的回答。\n\n[当前未配置API，显示模拟回复]"
    
    def get_recommended_questions(self) -> list:
        """获取推荐问题列表"""
        return [
            "如何申请退货退款？",
            "我的订单什么时候发货？",
            "物流信息在哪里查看？",
            "有什么优惠活动吗？",
            "商品尺码怎么选择？",
            "支持哪些支付方式？",
            "如何联系人工客服？",
            "商品质量有保障吗？"
        ]
    
    def test_connection(self) -> tuple:
        """
        测试API连接
        
        Returns:
            (成功与否, 消息)
        """
        if not self.is_configured():
            return False, "未配置API密钥"
        
        try:
            response = self._call_api("你好")
            if "抱歉" in response or "错误" in response:
                return False, response
            return True, "连接成功！"
        except Exception as e:
            return False, str(e)
