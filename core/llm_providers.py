# -*- coding: utf-8 -*-
"""
LLM提供商抽象层
支持多个LLM服务商：OpenAI、硅基流动、通义千问、智谱AI等
"""

import json
import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass
from requests.exceptions import Timeout, ConnectionError

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM响应数据类"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict] = None


class LLMProviderError(Exception):
    """LLM提供商错误"""
    def __init__(self, message: str, status_code: int = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class BaseLLMProvider(ABC):
    """LLM提供商基类"""
    
    # 子类需要定义这些属性
    name: str = "base"
    display_name: str = "基础提供商"
    default_api_url: str = ""
    default_model: str = ""
    supported_models: List[str] = []
    
    def __init__(self, api_key: str, api_url: str = None, model: str = None, **kwargs):
        self.api_key = api_key
        self.api_url = api_url or self.default_api_url
        self.model = model or self.default_model
        self.timeout = kwargs.get("timeout", 30)
        self.extra_config = kwargs
    
    @abstractmethod
    def chat(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送聊天请求"""
        pass
    
    def _handle_response_error(self, response: requests.Response) -> None:
        """处理HTTP响应错误"""
        if response.status_code == 401:
            raise LLMProviderError("API密钥无效或已过期", response.status_code, retryable=False)
        elif response.status_code == 403:
            raise LLMProviderError("API访问被拒绝", response.status_code, retryable=False)
        elif response.status_code == 429:
            raise LLMProviderError("请求过于频繁，已触发限流", response.status_code, retryable=True)
        elif response.status_code >= 500:
            raise LLMProviderError(f"服务器错误 ({response.status_code})", response.status_code, retryable=True)
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text)
            except:
                error_msg = response.text
            raise LLMProviderError(f"API错误 ({response.status_code}): {error_msg}", response.status_code)
    
    def test_connection(self) -> tuple:
        """测试连接"""
        try:
            response = self.chat([{"role": "user", "content": "你好"}], max_tokens=10)
            return True, "连接成功"
        except LLMProviderError as e:
            return False, str(e)
        except Exception as e:
            return False, f"连接失败: {str(e)}"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI提供商"""
    
    name = "openai"
    display_name = "OpenAI"
    default_api_url = "https://api.openai.com/v1"
    default_model = "gpt-3.5-turbo"
    supported_models = [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4",
        "gpt-3.5-turbo", "gpt-3.5-turbo-16k"
    ]
    
    def chat(self, messages: List[Dict], **kwargs) -> LLMResponse:
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code != 200:
                self._handle_response_error(response)
            
            result = response.json()
            return LLMResponse(
                content=result["choices"][0]["message"]["content"],
                model=result.get("model", self.model),
                usage=result.get("usage"),
                raw_response=result
            )
        except Timeout:
            raise LLMProviderError("请求超时", retryable=True)
        except ConnectionError:
            raise LLMProviderError("网络连接失败", retryable=True)
        except json.JSONDecodeError:
            raise LLMProviderError("响应数据格式错误", retryable=False)


class SiliconFlowProvider(BaseLLMProvider):
    """硅基流动提供商"""
    
    name = "siliconflow"
    display_name = "硅基流动"
    default_api_url = "https://api.siliconflow.cn/v1"
    default_model = "Qwen/Qwen3-8B"
    supported_models = [
        "Qwen/Qwen3-8B", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct",
        "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1",
        "THUDM/glm-4-9b-chat", "01-ai/Yi-1.5-9B-Chat"
    ]
    
    def chat(self, messages: List[Dict], **kwargs) -> LLMResponse:
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code != 200:
                self._handle_response_error(response)
            
            result = response.json()
            return LLMResponse(
                content=result["choices"][0]["message"]["content"],
                model=result.get("model", self.model),
                usage=result.get("usage"),
                raw_response=result
            )
        except Timeout:
            raise LLMProviderError("请求超时", retryable=True)
        except ConnectionError:
            raise LLMProviderError("网络连接失败", retryable=True)
        except json.JSONDecodeError:
            raise LLMProviderError("响应数据格式错误", retryable=False)


class QwenProvider(BaseLLMProvider):
    """通义千问提供商（阿里云）"""
    
    name = "qwen"
    display_name = "通义千问"
    default_api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_model = "qwen-turbo"
    supported_models = [
        "qwen-turbo", "qwen-plus", "qwen-max", "qwen-max-longcontext",
        "qwen-long", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct"
    ]
    
    def chat(self, messages: List[Dict], **kwargs) -> LLMResponse:
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code != 200:
                self._handle_response_error(response)
            
            result = response.json()
            return LLMResponse(
                content=result["choices"][0]["message"]["content"],
                model=result.get("model", self.model),
                usage=result.get("usage"),
                raw_response=result
            )
        except Timeout:
            raise LLMProviderError("请求超时", retryable=True)
        except ConnectionError:
            raise LLMProviderError("网络连接失败", retryable=True)
        except json.JSONDecodeError:
            raise LLMProviderError("响应数据格式错误", retryable=False)


class ZhipuProvider(BaseLLMProvider):
    """智谱AI提供商"""
    
    name = "zhipu"
    display_name = "智谱AI"
    default_api_url = "https://open.bigmodel.cn/api/paas/v4"
    default_model = "glm-4-flash"
    supported_models = [
        "glm-4-plus", "glm-4-0520", "glm-4", "glm-4-air",
        "glm-4-airx", "glm-4-long", "glm-4-flash"
    ]
    
    def chat(self, messages: List[Dict], **kwargs) -> LLMResponse:
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code != 200:
                self._handle_response_error(response)
            
            result = response.json()
            return LLMResponse(
                content=result["choices"][0]["message"]["content"],
                model=result.get("model", self.model),
                usage=result.get("usage"),
                raw_response=result
            )
        except Timeout:
            raise LLMProviderError("请求超时", retryable=True)
        except ConnectionError:
            raise LLMProviderError("网络连接失败", retryable=True)
        except json.JSONDecodeError:
            raise LLMProviderError("响应数据格式错误", retryable=False)


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek提供商"""
    
    name = "deepseek"
    display_name = "DeepSeek"
    default_api_url = "https://api.deepseek.com/v1"
    default_model = "deepseek-chat"
    supported_models = ["deepseek-chat", "deepseek-reasoner"]
    
    def chat(self, messages: List[Dict], **kwargs) -> LLMResponse:
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code != 200:
                self._handle_response_error(response)
            
            result = response.json()
            return LLMResponse(
                content=result["choices"][0]["message"]["content"],
                model=result.get("model", self.model),
                usage=result.get("usage"),
                raw_response=result
            )
        except Timeout:
            raise LLMProviderError("请求超时", retryable=True)
        except ConnectionError:
            raise LLMProviderError("网络连接失败", retryable=True)
        except json.JSONDecodeError:
            raise LLMProviderError("响应数据格式错误", retryable=False)


# 提供商注册表
PROVIDER_REGISTRY: Dict[str, Type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "siliconflow": SiliconFlowProvider,
    "qwen": QwenProvider,
    "zhipu": ZhipuProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider(name: str) -> Type[BaseLLMProvider]:
    """获取提供商类"""
    if name not in PROVIDER_REGISTRY:
        raise ValueError(f"未知的LLM提供商: {name}")
    return PROVIDER_REGISTRY[name]


def get_all_providers() -> List[Dict[str, Any]]:
    """获取所有提供商信息"""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "default_api_url": cls.default_api_url,
            "default_model": cls.default_model,
            "supported_models": cls.supported_models,
        }
        for cls in PROVIDER_REGISTRY.values()
    ]


def register_provider(name: str, provider_class: Type[BaseLLMProvider]) -> None:
    """注册自定义提供商"""
    PROVIDER_REGISTRY[name] = provider_class
