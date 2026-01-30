# -*- coding: utf-8 -*-
"""
对话管理模块
"""

import os
import json
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple


logger = logging.getLogger(__name__)


class Message:
    """消息类"""
    
    def __init__(self, role: str, content: str, timestamp: str = None, confidence: float = None, rag_trace: dict = None):
        self.role = role  # "user" 或 "assistant"
        self.content = content
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.confidence = confidence  # RAG置信度（仅assistant消息有）
        self.rag_trace = rag_trace
    
    def to_dict(self) -> dict:
        result = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.rag_trace is not None:
            result["rag_trace"] = self.rag_trace
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp"),
            confidence=data.get("confidence"),
            rag_trace=data.get("rag_trace")
        )


class Conversation:
    """对话类"""
    
    # 对话状态常量
    STATUS_NORMAL = "normal"  # 正常AI对话
    STATUS_PENDING_HUMAN = "pending_human"  # 等待人工接入
    STATUS_HUMAN_HANDLING = "human_handling"  # 人工处理中
    STATUS_HUMAN_CLOSED = "human_closed"  # 人工处理完成
    
    def __init__(self, conv_id: str = None, title: str = "新对话", messages: List[Message] = None):
        self.id = conv_id or str(uuid.uuid4())
        self.title = title
        self.messages = messages or []
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = self.created_at
        self.status = self.STATUS_NORMAL  # 对话状态
        self.human_agent_id = None  # 处理的人工客服ID
    
    def add_message(self, role: str, content: str, confidence: float = None, rag_trace: dict = None) -> Message:
        """添加消息"""
        message = Message(role, content, confidence=confidence, rag_trace=rag_trace)
        self.messages.append(message)
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 自动更新标题（取第一条用户消息的前20个字符）
        if role == "user" and self.title == "新对话":
            self.title = content[:20] + ("..." if len(content) > 20 else "")
        return message
    
    def transfer_to_human(self):
        """转人工客服"""
        self.status = self.STATUS_PENDING_HUMAN
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def accept_by_human(self, agent_id: str = "human_agent"):
        """人工客服接入"""
        self.status = self.STATUS_HUMAN_HANDLING
        self.human_agent_id = agent_id
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def close_human_service(self):
        """关闭人工服务"""
        self.status = self.STATUS_HUMAN_CLOSED
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def back_to_ai(self):
        """返回AI对话"""
        self.status = self.STATUS_NORMAL
        self.human_agent_id = None
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "human_agent_id": self.human_agent_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        conv = cls(
            conv_id=data["id"],
            title=data["title"],
            messages=[Message.from_dict(m) for m in data.get("messages", [])]
        )
        conv.created_at = data.get("created_at", conv.created_at)
        conv.updated_at = data.get("updated_at", conv.updated_at)
        conv.status = data.get("status", cls.STATUS_NORMAL)
        conv.human_agent_id = data.get("human_agent_id")
        return conv


class ConversationManager:
    """对话管理器 - 支持分页加载"""
    
    _instance = None
    
    # 分页配置
    DEFAULT_PAGE_SIZE = 20
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_manager()
        return cls._instance
    
    def _init_manager(self):
        """初始化管理器"""
        self.conversations: Dict[str, Conversation] = {}
        self.current_conversation: Optional[Conversation] = None
        self._conversation_ids: List[str] = []  # 按时间排序的ID列表
        self._load_conversations()
    
    def _get_data_dir(self) -> str:
        """获取数据目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data", "conversations")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    
    def _load_conversations(self) -> None:
        """加载所有对话（优化：只加载元数据，延迟加载消息）"""
        current_id = self.current_conversation.id if self.current_conversation else None
        self.conversations.clear()
        self._conversation_ids.clear()
        data_dir = self._get_data_dir()
        
        # 收集所有对话文件信息
        conv_files = []
        for filename in os.listdir(data_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(data_dir, filename)
                try:
                    # 只读取文件修改时间，不加载内容
                    mtime = os.path.getmtime(filepath)
                    conv_id = filename[:-5]  # 去掉 .json
                    conv_files.append((conv_id, filepath, mtime))
                except:
                    continue
        
        # 按修改时间排序
        conv_files.sort(key=lambda x: x[2], reverse=True)
        
        # 只加载最近的对话（分页）
        for conv_id, filepath, mtime in conv_files[:self.DEFAULT_PAGE_SIZE * 2]:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    conv = Conversation.from_dict(data)
                    self.conversations[conv.id] = conv
                    self._conversation_ids.append(conv.id)
            except (json.JSONDecodeError, IOError):
                continue

        if current_id and current_id in self.conversations:
            self.current_conversation = self.conversations[current_id]
        elif current_id:
            self.current_conversation = None
    
    def _save_conversation(self, conversation: Conversation) -> None:
        """保存对话（带文件锁）"""
        data_dir = self._get_data_dir()
        filepath = os.path.join(data_dir, f"{conversation.id}.json")
        try:
            from core.file_lock import FileLock
            
            # 使用文件锁保护写入
            lock = FileLock(filepath, timeout=5.0)
            with lock:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(conversation.to_dict(), f, ensure_ascii=False, indent=2)
        except TimeoutError:
            logger.error("保存对话失败：无法获取文件锁")
        except IOError as e:
            logger.exception("保存对话失败")
    
    def create_conversation(self) -> Conversation:
        """创建新对话"""
        conv = Conversation()
        self.conversations[conv.id] = conv
        self.current_conversation = conv
        self._save_conversation(conv)
        return conv
    
    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        """获取对话"""
        return self.conversations.get(conv_id)
    
    def delete_conversation(self, conv_id: str) -> bool:
        """删除对话"""
        if conv_id in self.conversations:
            del self.conversations[conv_id]
            data_dir = self._get_data_dir()
            filepath = os.path.join(data_dir, f"{conv_id}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
            # 同步清理session_status.json
            self._cleanup_session_status(conv_id)
            if self.current_conversation and self.current_conversation.id == conv_id:
                self.current_conversation = None
            return True
        return False
    
    def _cleanup_session_status(self, conv_id: str):
        """清理session_status.json中的记录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        status_file = os.path.join(base_dir, "data", "session_status.json")
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    statuses = json.load(f)
                if conv_id in statuses:
                    del statuses[conv_id]
                    with open(status_file, 'w', encoding='utf-8') as f:
                        json.dump(statuses, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.exception("清理会话状态失败")
    
    def get_all_conversations(self) -> List[Conversation]:
        """获取所有对话，按更新时间倒序"""
        return sorted(
            self.conversations.values(),
            key=lambda x: x.updated_at,
            reverse=True
        )
    
    def get_conversations_page(self, page: int = 1, page_size: int = None) -> Tuple[List[Conversation], int]:
        """分页获取对话列表
        
        Args:
            page: 页码（从1开始）
            page_size: 每页数量
        
        Returns:
            (对话列表, 总页数)
        """
        page_size = page_size or self.DEFAULT_PAGE_SIZE
        all_convs = self.get_all_conversations()
        
        total_pages = (len(all_convs) + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size
        
        return all_convs[start:end], total_pages
    
    def get_conversation_count(self) -> int:
        """获取对话总数"""
        return len(self.conversations)
    
    def set_current_conversation(self, conv_id: str) -> Optional[Conversation]:
        """设置当前对话"""
        conv = self.get_conversation(conv_id)
        if conv:
            self.current_conversation = conv
        return conv
    
    def add_message(self, role: str, content: str, confidence: float = None, rag_trace: dict = None) -> Optional[Message]:
        """向当前对话添加消息"""
        if self.current_conversation:
            conv_id = self.current_conversation.id
            latest = self.conversations.get(conv_id)
            if latest is not None and latest is not self.current_conversation:
                self.current_conversation = latest
            message = self.current_conversation.add_message(role, content, confidence, rag_trace=rag_trace)
            self._save_conversation(self.current_conversation)
            return message
        return None
