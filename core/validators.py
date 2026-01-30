# -*- coding: utf-8 -*-
"""
数据验证模块 - 输入验证和数据清理

优化内容 (v2.3.0):
- 输入验证器
- 防止负数、超大值等异常数据
- 文本长度和格式验证
"""

import re
import logging
from typing import Any, Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    value: Any  # 清理后的值
    error: str = ""  # 错误信息


class Validators:
    """验证器集合"""
    
    # 价格范围
    MIN_PRICE = 0.01
    MAX_PRICE = 99999999.99
    
    # 库存范围
    MIN_STOCK = 0
    MAX_STOCK = 9999999
    
    # 文本长度限制
    MAX_NAME_LENGTH = 200
    MAX_DESCRIPTION_LENGTH = 5000
    MAX_QUESTION_LENGTH = 500
    MAX_ANSWER_LENGTH = 10000
    MAX_KEYWORD_LENGTH = 50
    MAX_KEYWORDS_COUNT = 20
    
    @staticmethod
    def validate_price(value: Any) -> ValidationResult:
        """验证价格"""
        try:
            price = float(value)
            
            if price < Validators.MIN_PRICE:
                return ValidationResult(False, None, f"价格不能小于 {Validators.MIN_PRICE}")
            
            if price > Validators.MAX_PRICE:
                return ValidationResult(False, None, f"价格不能大于 {Validators.MAX_PRICE}")
            
            # 保留两位小数
            price = round(price, 2)
            return ValidationResult(True, price)
            
        except (ValueError, TypeError):
            return ValidationResult(False, None, "价格必须是有效数字")
    
    @staticmethod
    def validate_stock(value: Any) -> ValidationResult:
        """验证库存"""
        try:
            stock = int(value)
            
            if stock < Validators.MIN_STOCK:
                return ValidationResult(False, None, f"库存不能小于 {Validators.MIN_STOCK}")
            
            if stock > Validators.MAX_STOCK:
                return ValidationResult(False, None, f"库存不能大于 {Validators.MAX_STOCK}")
            
            return ValidationResult(True, stock)
            
        except (ValueError, TypeError):
            return ValidationResult(False, None, "库存必须是有效整数")
    
    @staticmethod
    def validate_text(value: Any, max_length: int, field_name: str = "文本", 
                      required: bool = True, strip: bool = True) -> ValidationResult:
        """验证文本"""
        if value is None:
            if required:
                return ValidationResult(False, None, f"{field_name}不能为空")
            return ValidationResult(True, "")
        
        text = str(value)
        if strip:
            text = text.strip()
        
        if required and not text:
            return ValidationResult(False, None, f"{field_name}不能为空")
        
        if len(text) > max_length:
            return ValidationResult(False, None, f"{field_name}长度不能超过 {max_length} 个字符")
        
        return ValidationResult(True, text)
    
    @staticmethod
    def validate_name(value: Any, required: bool = True) -> ValidationResult:
        """验证名称"""
        return Validators.validate_text(value, Validators.MAX_NAME_LENGTH, "名称", required)
    
    @staticmethod
    def validate_description(value: Any, required: bool = True) -> ValidationResult:
        """验证描述"""
        return Validators.validate_text(value, Validators.MAX_DESCRIPTION_LENGTH, "描述", required)
    
    @staticmethod
    def validate_question(value: Any, required: bool = True) -> ValidationResult:
        """验证问题"""
        return Validators.validate_text(value, Validators.MAX_QUESTION_LENGTH, "问题", required)
    
    @staticmethod
    def validate_answer(value: Any, required: bool = True) -> ValidationResult:
        """验证答案"""
        return Validators.validate_text(value, Validators.MAX_ANSWER_LENGTH, "答案", required)
    
    @staticmethod
    def validate_keywords(value: Any) -> ValidationResult:
        """验证关键词列表"""
        if value is None:
            return ValidationResult(True, [])
        
        if isinstance(value, str):
            # 支持逗号分隔的字符串
            keywords = [k.strip() for k in value.split(",") if k.strip()]
        elif isinstance(value, list):
            keywords = [str(k).strip() for k in value if k]
        else:
            return ValidationResult(False, None, "关键词格式无效")
        
        # 验证数量
        if len(keywords) > Validators.MAX_KEYWORDS_COUNT:
            return ValidationResult(False, None, f"关键词数量不能超过 {Validators.MAX_KEYWORDS_COUNT} 个")
        
        # 验证每个关键词长度
        valid_keywords = []
        for kw in keywords:
            if len(kw) > Validators.MAX_KEYWORD_LENGTH:
                continue  # 跳过过长的关键词
            valid_keywords.append(kw)
        
        return ValidationResult(True, valid_keywords)
    
    @staticmethod
    def validate_category(value: Any, allowed_categories: List[str] = None) -> ValidationResult:
        """验证分类"""
        result = Validators.validate_text(value, 50, "分类", required=True)
        if not result.valid:
            return result
        
        if allowed_categories and result.value not in allowed_categories:
            # 不在允许列表中，但仍然接受（可能是自定义分类）
            logger.warning("分类 '%s' 不在预定义列表中", result.value)
        
        return result
    
    @staticmethod
    def validate_email(value: Any) -> ValidationResult:
        """验证邮箱"""
        if not value:
            return ValidationResult(True, "")
        
        email = str(value).strip()
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(pattern, email):
            return ValidationResult(False, None, "邮箱格式无效")
        
        return ValidationResult(True, email)
    
    @staticmethod
    def validate_phone(value: Any) -> ValidationResult:
        """验证手机号"""
        if not value:
            return ValidationResult(True, "")
        
        phone = str(value).strip()
        # 中国手机号格式
        pattern = r'^1[3-9]\d{9}$'
        
        if not re.match(pattern, phone):
            return ValidationResult(False, None, "手机号格式无效")
        
        return ValidationResult(True, phone)
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """清理HTML标签（防XSS）"""
        if not text:
            return ""
        
        # 移除HTML标签
        clean = re.sub(r'<[^>]+>', '', text)
        
        # 转义特殊字符
        clean = clean.replace('&', '&amp;')
        clean = clean.replace('<', '&lt;')
        clean = clean.replace('>', '&gt;')
        clean = clean.replace('"', '&quot;')
        clean = clean.replace("'", '&#x27;')
        
        return clean


class ProductValidator:
    """商品数据验证器"""
    
    @staticmethod
    def validate(data: dict) -> Tuple[bool, dict, List[str]]:
        """验证商品数据
        
        Returns:
            (是否有效, 清理后的数据, 错误列表)
        """
        errors = []
        cleaned = {}
        
        # 验证名称
        result = Validators.validate_name(data.get("name"))
        if result.valid:
            cleaned["name"] = result.value
        else:
            errors.append(result.error)
        
        # 验证价格
        result = Validators.validate_price(data.get("price"))
        if result.valid:
            cleaned["price"] = result.value
        else:
            errors.append(result.error)
        
        # 验证库存
        result = Validators.validate_stock(data.get("stock", 0))
        if result.valid:
            cleaned["stock"] = result.value
        else:
            errors.append(result.error)
        
        # 验证分类
        result = Validators.validate_category(data.get("category"))
        if result.valid:
            cleaned["category"] = result.value
        else:
            errors.append(result.error)
        
        # 验证描述
        result = Validators.validate_description(data.get("description"))
        if result.valid:
            cleaned["description"] = result.value
        else:
            errors.append(result.error)
        
        # 验证关键词
        result = Validators.validate_keywords(data.get("keywords"))
        if result.valid:
            cleaned["keywords"] = result.value
        else:
            errors.append(result.error)
        
        # 规格参数（直接传递，不做严格验证）
        cleaned["specifications"] = data.get("specifications", {})
        
        return len(errors) == 0, cleaned, errors


class KnowledgeValidator:
    """知识条目数据验证器"""
    
    @staticmethod
    def validate(data: dict) -> Tuple[bool, dict, List[str]]:
        """验证知识条目数据
        
        Returns:
            (是否有效, 清理后的数据, 错误列表)
        """
        errors = []
        cleaned = {}
        
        # 验证问题
        result = Validators.validate_question(data.get("question"))
        if result.valid:
            cleaned["question"] = result.value
        else:
            errors.append(result.error)
        
        # 验证答案
        result = Validators.validate_answer(data.get("answer"))
        if result.valid:
            cleaned["answer"] = result.value
        else:
            errors.append(result.error)
        
        # 验证关键词
        result = Validators.validate_keywords(data.get("keywords"))
        if result.valid:
            cleaned["keywords"] = result.value
        else:
            errors.append(result.error)
        
        # 验证分类
        result = Validators.validate_category(data.get("category", "通用"))
        if result.valid:
            cleaned["category"] = result.value
        else:
            errors.append(result.error)
        
        return len(errors) == 0, cleaned, errors
