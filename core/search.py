# -*- coding: utf-8 -*-
"""
增强搜索模块
支持正则表达式、模糊搜索、高级过滤
"""

import re
import logging
from typing import List, Dict, Any, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

T = TypeVar('T')


class SearchMode(Enum):
    """搜索模式"""
    EXACT = "exact"           # 精确匹配
    CONTAINS = "contains"     # 包含匹配
    FUZZY = "fuzzy"           # 模糊匹配
    REGEX = "regex"           # 正则表达式
    PREFIX = "prefix"         # 前缀匹配
    SUFFIX = "suffix"         # 后缀匹配


@dataclass
class SearchFilter:
    """搜索过滤器"""
    field: str                          # 字段名
    value: Any                          # 过滤值
    operator: str = "eq"                # 操作符: eq, ne, gt, lt, gte, lte, in, contains


@dataclass
class SearchResult(Generic[T]):
    """搜索结果"""
    item: T                             # 原始项
    score: float                        # 匹配分数 (0-1)
    matched_fields: List[str]           # 匹配的字段
    highlights: Dict[str, str] = None   # 高亮文本


class AdvancedSearch(Generic[T]):
    """高级搜索器"""
    
    def __init__(self, items: List[T], search_fields: List[str] = None):
        """
        Args:
            items: 要搜索的项目列表
            search_fields: 要搜索的字段列表（如果项目是dict或有属性）
        """
        self._items = items
        self._search_fields = search_fields or []
        self._filters: List[SearchFilter] = []
        self._sort_key: Optional[Callable] = None
        self._sort_reverse = False
    
    def _get_field_value(self, item: T, field: str) -> Any:
        """获取字段值"""
        if isinstance(item, dict):
            return item.get(field)
        elif hasattr(item, field):
            return getattr(item, field)
        return None
    
    def _match_text(self, text: str, query: str, mode: SearchMode) -> tuple:
        """文本匹配
        
        Returns:
            (是否匹配, 匹配分数)
        """
        if not text or not query:
            return False, 0.0
        
        text_lower = text.lower()
        query_lower = query.lower()
        
        if mode == SearchMode.EXACT:
            matched = text_lower == query_lower
            return matched, 1.0 if matched else 0.0
        
        elif mode == SearchMode.CONTAINS:
            matched = query_lower in text_lower
            if matched:
                # 分数基于匹配位置和长度比例
                pos = text_lower.find(query_lower)
                score = 0.5 + 0.3 * (1 - pos / len(text)) + 0.2 * (len(query) / len(text))
                return True, min(score, 1.0)
            return False, 0.0
        
        elif mode == SearchMode.FUZZY:
            ratio = SequenceMatcher(None, text_lower, query_lower).ratio()
            return ratio > 0.5, ratio
        
        elif mode == SearchMode.REGEX:
            try:
                pattern = re.compile(query, re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    score = len(match.group()) / len(text)
                    return True, min(score + 0.5, 1.0)
            except re.error:
                pass
            return False, 0.0
        
        elif mode == SearchMode.PREFIX:
            matched = text_lower.startswith(query_lower)
            return matched, 0.9 if matched else 0.0
        
        elif mode == SearchMode.SUFFIX:
            matched = text_lower.endswith(query_lower)
            return matched, 0.8 if matched else 0.0
        
        return False, 0.0
    
    def _apply_filter(self, item: T, filter: SearchFilter) -> bool:
        """应用过滤器"""
        value = self._get_field_value(item, filter.field)
        
        if filter.operator == "eq":
            return value == filter.value
        elif filter.operator == "ne":
            return value != filter.value
        elif filter.operator == "gt":
            return value is not None and value > filter.value
        elif filter.operator == "lt":
            return value is not None and value < filter.value
        elif filter.operator == "gte":
            return value is not None and value >= filter.value
        elif filter.operator == "lte":
            return value is not None and value <= filter.value
        elif filter.operator == "in":
            return value in filter.value
        elif filter.operator == "contains":
            if isinstance(value, str):
                return filter.value.lower() in value.lower()
            elif isinstance(value, (list, tuple)):
                return filter.value in value
        
        return True
    
    def filter(self, field: str, value: Any, operator: str = "eq") -> 'AdvancedSearch[T]':
        """添加过滤条件
        
        Args:
            field: 字段名
            value: 过滤值
            operator: 操作符 (eq, ne, gt, lt, gte, lte, in, contains)
        
        Returns:
            self（支持链式调用）
        """
        self._filters.append(SearchFilter(field, value, operator))
        return self
    
    def sort(self, key: Callable[[T], Any], reverse: bool = False) -> 'AdvancedSearch[T]':
        """设置排序
        
        Args:
            key: 排序键函数
            reverse: 是否降序
        
        Returns:
            self（支持链式调用）
        """
        self._sort_key = key
        self._sort_reverse = reverse
        return self
    
    def search(self, query: str, mode: SearchMode = SearchMode.CONTAINS,
               min_score: float = 0.0) -> List[SearchResult[T]]:
        """执行搜索
        
        Args:
            query: 搜索查询
            mode: 搜索模式
            min_score: 最小匹配分数
        
        Returns:
            搜索结果列表（按分数降序）
        """
        results = []
        
        for item in self._items:
            # 应用过滤器
            if not all(self._apply_filter(item, f) for f in self._filters):
                continue
            
            # 搜索匹配
            best_score = 0.0
            matched_fields = []
            
            if not query:
                # 无查询时返回所有（过滤后的）项目
                results.append(SearchResult(item=item, score=1.0, matched_fields=[]))
                continue
            
            # 搜索指定字段
            fields_to_search = self._search_fields or self._get_searchable_fields(item)
            
            for field in fields_to_search:
                value = self._get_field_value(item, field)
                if value is None:
                    continue
                
                # 处理列表字段
                if isinstance(value, (list, tuple)):
                    for v in value:
                        if isinstance(v, str):
                            matched, score = self._match_text(v, query, mode)
                            if matched and score > best_score:
                                best_score = score
                                if field not in matched_fields:
                                    matched_fields.append(field)
                elif isinstance(value, str):
                    matched, score = self._match_text(value, query, mode)
                    if matched and score > best_score:
                        best_score = score
                        if field not in matched_fields:
                            matched_fields.append(field)
            
            if best_score >= min_score and matched_fields:
                results.append(SearchResult(
                    item=item,
                    score=best_score,
                    matched_fields=matched_fields
                ))
        
        # 排序
        if self._sort_key:
            results.sort(key=lambda r: self._sort_key(r.item), reverse=self._sort_reverse)
        else:
            results.sort(key=lambda r: r.score, reverse=True)
        
        return results
    
    def _get_searchable_fields(self, item: T) -> List[str]:
        """获取可搜索的字段"""
        if isinstance(item, dict):
            return [k for k, v in item.items() if isinstance(v, (str, list))]
        else:
            return [attr for attr in dir(item) 
                    if not attr.startswith('_') and 
                    isinstance(getattr(item, attr, None), (str, list))]
    
    def clear_filters(self) -> 'AdvancedSearch[T]':
        """清除所有过滤器"""
        self._filters.clear()
        return self
    
    def reset(self) -> 'AdvancedSearch[T]':
        """重置搜索器"""
        self._filters.clear()
        self._sort_key = None
        self._sort_reverse = False
        return self


def fuzzy_match(text: str, query: str, threshold: float = 0.6) -> bool:
    """模糊匹配
    
    Args:
        text: 要匹配的文本
        query: 查询字符串
        threshold: 匹配阈值 (0-1)
    
    Returns:
        是否匹配
    """
    if not text or not query:
        return False
    
    ratio = SequenceMatcher(None, text.lower(), query.lower()).ratio()
    return ratio >= threshold


def highlight_text(text: str, query: str, 
                   start_tag: str = "<mark>", end_tag: str = "</mark>") -> str:
    """高亮文本中的匹配部分
    
    Args:
        text: 原始文本
        query: 查询字符串
        start_tag: 高亮开始标签
        end_tag: 高亮结束标签
    
    Returns:
        高亮后的文本
    """
    if not text or not query:
        return text
    
    try:
        pattern = re.compile(f"({re.escape(query)})", re.IGNORECASE)
        return pattern.sub(f"{start_tag}\\1{end_tag}", text)
    except:
        return text


def search_knowledge(query: str, mode: SearchMode = SearchMode.CONTAINS,
                    category: str = None) -> List[SearchResult]:
    """搜索知识库
    
    Args:
        query: 搜索查询
        mode: 搜索模式
        category: 分类过滤
    
    Returns:
        搜索结果列表
    """
    try:
        from core.shared_data import KnowledgeStore
        store = KnowledgeStore()
        
        searcher = AdvancedSearch(
            store.items,
            search_fields=["question", "answer", "keywords"]
        )
        
        if category and category != "全部":
            searcher.filter("category", category)
        
        return searcher.search(query, mode)
    except Exception as e:
        logger.exception("搜索知识库失败")
        return []


def search_products(query: str, mode: SearchMode = SearchMode.CONTAINS,
                   category: str = None, min_price: float = None,
                   max_price: float = None) -> List[SearchResult]:
    """搜索商品
    
    Args:
        query: 搜索查询
        mode: 搜索模式
        category: 分类过滤
        min_price: 最低价格
        max_price: 最高价格
    
    Returns:
        搜索结果列表
    """
    try:
        from core.shared_data import ProductStore
        store = ProductStore()
        
        searcher = AdvancedSearch(
            store.products,
            search_fields=["name", "description", "keywords"]
        )
        
        if category and category != "全部":
            searcher.filter("category", category)
        
        if min_price is not None:
            searcher.filter("price", min_price, "gte")
        
        if max_price is not None:
            searcher.filter("price", max_price, "lte")
        
        return searcher.search(query, mode)
    except Exception as e:
        logger.exception("搜索商品失败")
        return []
