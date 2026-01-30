# -*- coding: utf-8 -*-
"""
数据统计模块
提供系统使用情况统计和分析
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class UsageStats:
    """使用统计数据"""
    total_conversations: int = 0
    total_messages: int = 0
    total_knowledge_items: int = 0
    total_products: int = 0
    total_users: int = 0
    
    # 时间范围统计
    conversations_today: int = 0
    conversations_this_week: int = 0
    conversations_this_month: int = 0
    
    # 分类统计
    knowledge_by_category: Dict[str, int] = field(default_factory=dict)
    products_by_category: Dict[str, int] = field(default_factory=dict)
    
    # 热门问题
    top_questions: List[Tuple[str, int]] = field(default_factory=list)
    
    # 响应统计
    avg_response_time_ms: float = 0.0
    success_rate: float = 0.0


@dataclass
class ConversationStats:
    """对话统计"""
    conversation_id: str
    message_count: int
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_seconds: float = 0.0
    user_messages: int = 0
    assistant_messages: int = 0


class StatisticsManager:
    """统计管理器"""
    
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
        
        self._data_dir = self._get_data_dir()
        self._stats_file = os.path.join(self._data_dir, "statistics.json")
        self._question_counter: Counter = Counter()
        self._load_stats()
    
    def _get_data_dir(self) -> str:
        """获取数据目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    
    def _load_stats(self):
        """加载统计数据"""
        if os.path.exists(self._stats_file):
            try:
                with open(self._stats_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._question_counter = Counter(data.get("question_counter", {}))
            except Exception as e:
                logger.exception("加载统计数据失败")
                self._question_counter = Counter()
    
    def _save_stats(self):
        """保存统计数据"""
        try:
            data = {
                "question_counter": dict(self._question_counter),
                "last_updated": datetime.now().isoformat()
            }
            with open(self._stats_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("保存统计数据失败")
    
    def record_question(self, question: str):
        """记录问题（用于热门问题统计）"""
        # 简化问题（去除标点，截断）
        simplified = question.strip()[:50]
        if simplified:
            self._question_counter[simplified] += 1
            # 定期保存
            if sum(self._question_counter.values()) % 10 == 0:
                self._save_stats()
    
    def get_usage_stats(self) -> UsageStats:
        """获取使用统计"""
        stats = UsageStats()
        
        try:
            # 获取知识库统计
            from core.shared_data import KnowledgeStore, ProductStore
            knowledge_store = KnowledgeStore()
            product_store = ProductStore()
            
            stats.total_knowledge_items = len(knowledge_store.items)
            stats.total_products = len(product_store.products)
            
            # 知识库分类统计
            for item in knowledge_store.items:
                cat = item.category
                stats.knowledge_by_category[cat] = stats.knowledge_by_category.get(cat, 0) + 1
            
            # 商品分类统计
            for item in product_store.products:
                cat = item.category
                stats.products_by_category[cat] = stats.products_by_category.get(cat, 0) + 1
            
            # 获取对话统计
            from core.conversation import ConversationManager
            conv_manager = ConversationManager()
            conversations = conv_manager.get_all_conversations()
            
            stats.total_conversations = len(conversations)
            
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=now.weekday())
            month_start = today_start.replace(day=1)
            
            for conv in conversations:
                # 统计消息数
                stats.total_messages += len(conv.messages)
                
                # 时间范围统计
                if conv.messages:
                    try:
                        first_msg_time = datetime.fromisoformat(conv.messages[0].get("timestamp", ""))
                        if first_msg_time >= today_start:
                            stats.conversations_today += 1
                        if first_msg_time >= week_start:
                            stats.conversations_this_week += 1
                        if first_msg_time >= month_start:
                            stats.conversations_this_month += 1
                    except:
                        pass
            
            # 获取用户统计
            users_file = os.path.join(self._data_dir, "users.json")
            if os.path.exists(users_file):
                with open(users_file, 'r', encoding='utf-8') as f:
                    users = json.load(f)
                    stats.total_users = len(users)
            
            # 热门问题
            stats.top_questions = self._question_counter.most_common(10)
            
            # 性能统计
            try:
                from core.performance import PerformanceMonitor
                monitor = PerformanceMonitor()
                summary = monitor.get_summary()
                
                if "metrics" in summary:
                    api_metrics = summary["metrics"].get("api_call", {})
                    if api_metrics:
                        stats.avg_response_time_ms = api_metrics.get("avg", 0) * 1000
                        stats.success_rate = api_metrics.get("success_rate", 0)
            except:
                pass
            
        except Exception as e:
            logger.exception("获取使用统计失败")
        
        return stats
    
    def get_conversation_stats(self, conversation_id: str) -> Optional[ConversationStats]:
        """获取单个对话的统计"""
        try:
            from core.conversation import ConversationManager
            conv_manager = ConversationManager()
            conv = conv_manager.get_conversation(conversation_id)
            
            if not conv:
                return None
            
            stats = ConversationStats(
                conversation_id=conversation_id,
                message_count=len(conv.messages),
                start_time=None,
                end_time=None
            )
            
            if conv.messages:
                # 统计用户和助手消息
                for msg in conv.messages:
                    role = msg.get("role", "")
                    if role == "user":
                        stats.user_messages += 1
                    elif role == "assistant":
                        stats.assistant_messages += 1
                
                # 时间统计
                try:
                    stats.start_time = datetime.fromisoformat(conv.messages[0].get("timestamp", ""))
                    stats.end_time = datetime.fromisoformat(conv.messages[-1].get("timestamp", ""))
                    stats.duration_seconds = (stats.end_time - stats.start_time).total_seconds()
                except:
                    pass
            
            return stats
        except Exception as e:
            logger.exception("获取对话统计失败")
            return None
    
    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取每日统计（最近N天）"""
        daily_stats = []
        
        try:
            from core.conversation import ConversationManager
            conv_manager = ConversationManager()
            conversations = conv_manager.get_all_conversations()
            
            now = datetime.now()
            
            for i in range(days):
                day = now - timedelta(days=i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                day_convs = 0
                day_messages = 0
                
                for conv in conversations:
                    if conv.messages:
                        try:
                            first_msg_time = datetime.fromisoformat(conv.messages[0].get("timestamp", ""))
                            if day_start <= first_msg_time < day_end:
                                day_convs += 1
                                day_messages += len(conv.messages)
                        except:
                            pass
                
                daily_stats.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "conversations": day_convs,
                    "messages": day_messages
                })
            
            daily_stats.reverse()  # 按时间正序
        except Exception as e:
            logger.exception("获取每日统计失败")
        
        return daily_stats
    
    def get_category_distribution(self) -> Dict[str, Dict[str, int]]:
        """获取分类分布"""
        result = {
            "knowledge": {},
            "products": {}
        }
        
        try:
            from core.shared_data import KnowledgeStore, ProductStore
            
            knowledge_store = KnowledgeStore()
            for item in knowledge_store.items:
                cat = item.category
                result["knowledge"][cat] = result["knowledge"].get(cat, 0) + 1
            
            product_store = ProductStore()
            for item in product_store.products:
                cat = item.category
                result["products"][cat] = result["products"].get(cat, 0) + 1
        except Exception as e:
            logger.exception("获取分类分布失败")
        
        return result
    
    def export_report(self) -> str:
        """导出统计报告（Markdown格式）"""
        stats = self.get_usage_stats()
        daily = self.get_daily_stats(7)
        
        lines = [
            "# 系统使用统计报告",
            f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "\n## 总体概览",
            f"- 总对话数: {stats.total_conversations}",
            f"- 总消息数: {stats.total_messages}",
            f"- 知识库条目: {stats.total_knowledge_items}",
            f"- 商品数量: {stats.total_products}",
            f"- 用户数量: {stats.total_users}",
            "\n## 时间范围统计",
            f"- 今日对话: {stats.conversations_today}",
            f"- 本周对话: {stats.conversations_this_week}",
            f"- 本月对话: {stats.conversations_this_month}",
        ]
        
        if stats.knowledge_by_category:
            lines.append("\n## 知识库分类分布")
            for cat, count in sorted(stats.knowledge_by_category.items(), key=lambda x: -x[1]):
                lines.append(f"- {cat}: {count}")
        
        if stats.products_by_category:
            lines.append("\n## 商品分类分布")
            for cat, count in sorted(stats.products_by_category.items(), key=lambda x: -x[1]):
                lines.append(f"- {cat}: {count}")
        
        if stats.top_questions:
            lines.append("\n## 热门问题 Top 10")
            for i, (q, count) in enumerate(stats.top_questions, 1):
                lines.append(f"{i}. {q} ({count}次)")
        
        if daily:
            lines.append("\n## 最近7天趋势")
            lines.append("| 日期 | 对话数 | 消息数 |")
            lines.append("|------|--------|--------|")
            for d in daily:
                lines.append(f"| {d['date']} | {d['conversations']} | {d['messages']} |")
        
        if stats.avg_response_time_ms > 0:
            lines.append("\n## 性能指标")
            lines.append(f"- 平均响应时间: {stats.avg_response_time_ms:.2f}ms")
            lines.append(f"- 成功率: {stats.success_rate*100:.1f}%")
        
        return "\n".join(lines)


def get_statistics_manager() -> StatisticsManager:
    """获取统计管理器单例"""
    return StatisticsManager()
