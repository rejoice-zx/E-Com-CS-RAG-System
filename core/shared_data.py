# -*- coding: utf-8 -*-
"""
共享数据管理器 - 知识库使用JSON存储，集成向量检索

优化内容 (v2.3.0):
- 添加缓存机制减少重复检索
- 集成性能监控
- 添加知识库去重检测
"""


from typing import List, Optional, Tuple, Dict, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import os
import logging
import re

from core.config import Config


logger = logging.getLogger(__name__)


BASE_SYSTEM_PROMPT = "你是一个专业的电商客服助手，负责解答用户关于商品、订单、物流、退换货等问题。请用友好、专业的语气回复，回答要简洁有帮助。"


def truncate_text(text: Optional[str], max_chars: int) -> str:
    if not text:
        return ""
    if max_chars is None or max_chars <= 0:
        return str(text)
    text = str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def trim_history(history: Optional[list], max_messages: int, max_chars: int) -> list:
    if not history:
        return []

    normalized = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role not in ("user", "assistant") or not content:
            continue
        normalized.append({"role": role, "content": str(content)})

    if not normalized:
        return []

    if max_messages is not None and max_messages > 0:
        normalized = normalized[-max_messages:]

    if max_chars is None or max_chars <= 0:
        return normalized

    picked_reversed = []
    total = 0
    for msg in reversed(normalized):
        content = msg.get("content", "")
        if not content:
            continue
        next_total = total + len(content)
        if next_total > max_chars:
            if not picked_reversed:
                picked_reversed.append({
                    "role": msg.get("role", "user"),
                    "content": truncate_text(content, max_chars),
                })
            break
        picked_reversed.append(msg)
        total = next_total

    return list(reversed(picked_reversed))


def build_system_prompt(context_text: Optional[str]) -> str:
    if context_text:
        return (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "以下是从知识库中检索到的相关信息，请参考这些信息来回答用户问题：\n\n"
            "---知识库内容开始---\n"
            f"{context_text}\n"
            "---知识库内容结束---\n\n"
            "请基于上述知识库内容回答用户问题。如果知识库内容不足以回答问题，可以适当补充，但要保持专业和准确。"
        )
    return BASE_SYSTEM_PROMPT


def build_messages(system_prompt: str, user_message: str, history: Optional[list] = None) -> list:
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": user_message})
    return messages


def format_prompt_preview(messages: list) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"【System Message】\n{content}")
        elif role == "user":
            parts.append(f"【User Message】\n{content}")
        elif role == "assistant":
            parts.append(f"【Assistant Message】\n{content}")
    return "\n\n".join(parts)


@dataclass
class KnowledgeItem:
    """知识条目"""
    id: str
    question: str
    answer: str
    keywords: List[str] = field(default_factory=list)
    category: str = "通用"
    score: float = 1.0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'KnowledgeItem':
        return cls(
            id=data.get("id", ""),
            question=data.get("question", ""),
            answer=data.get("answer", ""),
            keywords=data.get("keywords", []),
            category=data.get("category", "通用"),
            score=data.get("score", 1.0)
        )


@dataclass
class ProductItem:
    """商品信息"""
    id: str                                          # 商品ID，如 P001
    name: str                                        # 商品名称
    price: float                                     # 价格
    category: str                                    # 商品分类
    description: str                                 # 商品描述
    specifications: Dict[str, str] = field(default_factory=dict)  # 规格参数
    stock: int = 0                                   # 库存数量
    keywords: List[str] = field(default_factory=list)  # 关键词
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ProductItem':
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            price=data.get("price", 0.0),
            category=data.get("category", ""),
            description=data.get("description", ""),
            specifications=data.get("specifications", {}),
            stock=data.get("stock", 0),
            keywords=data.get("keywords", [])
        )
    
    def generate_knowledge_items(self) -> List[dict]:
        """生成对应的知识条目数据"""
        items = []
        
        # 构建规格文本
        spec_text = ""
        if self.specifications:
            spec_lines = [f"  - {k}: {v}" for k, v in self.specifications.items()]
            spec_text = "\n".join(spec_lines)
        
        # 1. 商品基本信息问答
        answer = f"【{self.name}】\n"
        answer += f"💰 价格：¥{self.price:.2f}\n"
        answer += f"📦 库存：{'有货' if self.stock > 0 else '暂时缺货'}（{self.stock}件）\n"
        answer += f"📁 分类：{self.category}\n"
        if spec_text:
            answer += f"📋 规格：\n{spec_text}\n"
        answer += f"\n📝 商品描述：\n{self.description}"
        
        items.append({
            "question": f"{self.name}怎么样？",
            "answer": answer,
            "keywords": self.keywords + [self.name, self.category],
            "category": "商品信息"
        })
        
        # 2. 价格查询
        items.append({
            "question": f"{self.name}多少钱？",
            "answer": f"{self.name}的价格是 ¥{self.price:.2f}。{'目前有货' if self.stock > 0 else '目前暂时缺货'}。",
            "keywords": [self.name, "价格", "多少钱"],
            "category": "商品信息"
        })
        
        # 3. 规格查询（如果有规格）
        if self.specifications:
            spec_answer = f"{self.name}的规格参数如下：\n{spec_text}"
            items.append({
                "question": f"{self.name}有什么规格/配置？",
                "answer": spec_answer,
                "keywords": [self.name, "规格", "配置", "参数"],
                "category": "商品信息"
            })
        
        # 4. 库存查询
        stock_status = "有货" if self.stock > 0 else "暂时缺货"
        stock_answer = f"{self.name}目前{stock_status}，库存数量：{self.stock}件。"
        if self.stock == 0:
            stock_answer += "\n您可以点击'到货通知'，商品补货后我们会第一时间通知您。"
        items.append({
            "question": f"{self.name}有货吗？",
            "answer": stock_answer,
            "keywords": [self.name, "库存", "有货", "缺货"],
            "category": "商品信息"
        })
        
        return items

class RAGSearchResult:
    """RAG搜索结果，用于追溯"""
    def __init__(self):
        self.query = ""
        self.rewritten_query = ""
        self.retrieved_items: List[Tuple[KnowledgeItem, float]] = []
        self.context_text = ""
        self.confidence = 0.0
        self.search_method = "vector"  # "vector" or "keyword"
        self.final_prompt = ""  # 最终发送给LLM的完整提示词
    
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "rewritten_query": self.rewritten_query,
            "retrieved_items": [
                {"id": item.id, "question": item.question, "score": score}
                for item, score in self.retrieved_items
            ],
            "context_text": self.context_text,
            "confidence": self.confidence,
            "search_method": self.search_method,
            "final_prompt": self.final_prompt
        }


class KnowledgeStore:
    """知识库存储 - JSON文件持久化 + 向量检索 + 倒排索引"""
    _cache_mtime: float | None = None
    _cache_raw_items: list[dict] | None = None

    def __init__(self):
        self.items: List[KnowledgeItem] = []
        self.config = Config()
        self._data_file = self._get_data_file()
        self._last_search_result: Optional[RAGSearchResult] = None
        self._last_vector_index_error: Optional[dict] = None
        self._last_chunk_map: Dict[str, List[str]] = {}
        self._embedding_client = None
        self._vector_store = None
        
        # 倒排索引（关键词 -> 知识条目ID列表）
        self._inverted_index: Dict[str, List[str]] = {}
        self._index_built = False
        
        # 性能监控
        self._perf_monitor = None
        
        self._load_from_file()
    
    def _get_perf_monitor(self):
        """延迟加载性能监控器"""
        if self._perf_monitor is None:
            try:
                from core.performance import PerformanceMonitor
                self._perf_monitor = PerformanceMonitor()
            except Exception:
                pass
        return self._perf_monitor

    @property
    def last_vector_index_error(self) -> Optional[dict]:
        return self._last_vector_index_error
    
    def _get_embedding_client(self):
        """延迟加载Embedding客户端"""
        if self._embedding_client is None:
            try:
                from core.embedding import EmbeddingClient
                self._embedding_client = EmbeddingClient()
            except Exception as e:
                logger.exception("加载Embedding客户端失败")
        return self._embedding_client
    
    def _get_vector_store(self):
        """延迟加载向量存储"""
        if self._vector_store is None:
            try:
                from core.vector_store import VectorStore
                self._vector_store = VectorStore()
            except Exception as e:
                logger.exception("加载向量存储失败")
        return self._vector_store
    
    def _get_data_file(self) -> str:
        """获取数据文件路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "knowledge_base.json")
    
    def _load_from_file(self):
        """从JSON文件加载知识库"""
        if os.path.exists(self._data_file):
            try:
                mtime = os.path.getmtime(self._data_file)
                if (
                    self.__class__._cache_mtime == mtime
                    and isinstance(self.__class__._cache_raw_items, list)
                ):
                    self.items = [KnowledgeItem.from_dict(item) for item in self.__class__._cache_raw_items]
                    return
                with open(self._data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    raw_items = data.get("items", []) if isinstance(data, dict) else []
                    raw_items = raw_items if isinstance(raw_items, list) else []
                    self.items = [KnowledgeItem.from_dict(item) for item in raw_items]
                    self.__class__._cache_mtime = mtime
                    self.__class__._cache_raw_items = raw_items
                    logger.info("已加载 %s 条知识", len(self.items))
                    
                # 构建倒排索引
                self._build_inverted_index()
            except Exception as e:
                logger.exception("加载知识库失败")
                self._load_default_knowledge()
        else:
            self._load_default_knowledge()
            self._save_to_file()
    
    def _save_to_file(self):
        """保存知识库到JSON文件（带文件锁）"""
        try:
            from core.file_lock import FileLock
            
            data = {
                "items": [item.to_dict() for item in self.items],
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 使用文件锁保护写入
            lock = FileLock(self._data_file, timeout=5.0)
            with lock:
                with open(self._data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            try:
                self.__class__._cache_mtime = os.path.getmtime(self._data_file)
                self.__class__._cache_raw_items = data.get("items", [])
            except Exception:
                self.__class__._cache_mtime = None
                self.__class__._cache_raw_items = None
            logger.info("知识库已保存，共 %s 条", len(self.items))
        except TimeoutError:
            logger.error("保存知识库失败：无法获取文件锁")
        except Exception as e:
            logger.exception("保存知识库失败")
    
    def _load_default_knowledge(self):
        """加载默认知识库"""
        default_items = [
            KnowledgeItem(
                id="K001",
                question="如何申请退货退款？",
                answer='您可以在收到商品后7天内申请无理由退货。请进入"我的订单"，找到对应订单点击"申请退货"按钮。确保商品完好、不影响二次销售。退款将在1-3个工作日内原路返回。',
                keywords=["退货", "退款", "退换货"],
                category="售后政策"
            ),
            KnowledgeItem(
                id="K002",
                question="我的订单什么时候发货？",
                answer="我们会在下单后24小时内发货（节假日顺延）。发货后您会收到短信通知，也可以在订单详情中查看物流单号。",
                keywords=["发货", "订单", "物流"],
                category="物流配送"
            ),
            KnowledgeItem(
                id="K003",
                question="物流信息在哪里查看？",
                answer="您可以在订单详情页查看物流信息。一般情况下，普通快递3-5天到达，加急快递1-2天到达。如果物流信息长时间未更新，可能是快递公司暂未扫描。",
                keywords=["物流", "快递", "配送"],
                category="物流配送"
            ),
            KnowledgeItem(
                id="K004",
                question="有什么优惠活动吗？",
                answer="目前我们有以下优惠活动：\n1. 新用户首单立减10元\n2. 满200减30\n3. 部分商品限时折扣\n\n您可以在首页查看更多优惠信息。",
                keywords=["优惠", "折扣", "活动", "促销"],
                category="促销活动"
            ),
            KnowledgeItem(
                id="K005",
                question="商品尺码怎么选择？",
                answer="关于尺码选择，建议您参考商品详情页的尺码表。如果您平时穿M码，可以参考表中M码对应的具体尺寸，与您的实际测量尺寸对比选择。",
                keywords=["尺码", "尺寸", "大小"],
                category="商品咨询"
            ),
            KnowledgeItem(
                id="K006",
                question="支持哪些支付方式？",
                answer="我们支持多种支付方式：支付宝、微信支付、银联支付、信用卡等。支付过程采用加密传输，请放心使用。",
                keywords=["支付", "付款", "支付宝", "微信"],
                category="支付问题"
            ),
            KnowledgeItem(
                id="K007",
                question="如何联系人工客服？",
                answer='您可以通过以下方式联系人工客服：\n1. 点击页面右下角"转人工"按钮\n2. 拨打客服热线：400-XXX-XXXX\n3. 在APP内选择"在线客服"\n\n服务时间：9:00-21:00',
                keywords=["人工", "客服", "联系"],
                category="服务咨询"
            ),
            KnowledgeItem(
                id="K008",
                question="商品质量有保障吗？",
                answer="我们所有商品都经过严格质量检测。如果您收到的商品存在质量问题，请在收货后48小时内拍照反馈，我们将为您安排换货或退款。",
                keywords=["质量", "保障", "正品"],
                category="商品咨询"
            ),
        ]
        self.items = default_items
        # 构建倒排索引
        self._build_inverted_index()
    
    def _build_inverted_index(self):
        """构建倒排索引以加速关键词检索"""
        self._inverted_index.clear()
        
        for item in self.items:
            # 索引关键词
            for keyword in (item.keywords or []):
                keyword = (keyword or "").strip().lower()
                if keyword:
                    if keyword not in self._inverted_index:
                        self._inverted_index[keyword] = []
                    if item.id not in self._inverted_index[keyword]:
                        self._inverted_index[keyword].append(item.id)
            
            # 索引分类
            category = (item.category or "").strip().lower()
            if category:
                if category not in self._inverted_index:
                    self._inverted_index[category] = []
                if item.id not in self._inverted_index[category]:
                    self._inverted_index[category].append(item.id)
            
            # 提取问题中的关键词（简单分词）
            tokens = self._extract_tokens(item.question)
            for token in tokens[:10]:  # 限制每个问题最多10个token
                token = token.lower()
                if token not in self._inverted_index:
                    self._inverted_index[token] = []
                if item.id not in self._inverted_index[token]:
                    self._inverted_index[token].append(item.id)
        
        self._index_built = True
        logger.debug("倒排索引已构建，共 %s 个词条", len(self._inverted_index))
    
    def _update_inverted_index(self, item: KnowledgeItem, remove: bool = False):
        """增量更新倒排索引"""
        if not self._index_built:
            self._build_inverted_index()
            return
        
        # 收集该条目的所有索引词
        index_terms = set()
        for keyword in (item.keywords or []):
            keyword = (keyword or "").strip().lower()
            if keyword:
                index_terms.add(keyword)
        
        category = (item.category or "").strip().lower()
        if category:
            index_terms.add(category)
        
        tokens = self._extract_tokens(item.question)
        for token in tokens[:10]:
            index_terms.add(token.lower())
        
        # 更新索引
        for term in index_terms:
            if remove:
                # 删除
                if term in self._inverted_index and item.id in self._inverted_index[term]:
                    self._inverted_index[term].remove(item.id)
                    if not self._inverted_index[term]:
                        del self._inverted_index[term]
            else:
                # 添加
                if term not in self._inverted_index:
                    self._inverted_index[term] = []
                if item.id not in self._inverted_index[term]:
                    self._inverted_index[term].append(item.id)
    
    def _chunk_text(self, text: str) -> List[str]:
        """将文本切片"""
        chunk_size = self.config.get("chunk_size", 500)
        chunk_overlap = self.config.get("chunk_overlap", 50)
        
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - chunk_overlap
        
        return chunks
    
    def _rewrite_query(self, query: str) -> str:
        """查询改写 - 短语停用词过滤 + 同义词扩展"""
        
        # 电商客服场景停用词（只保留完整短语，不使用单字符）
        # 按长度从长到短排序，避免短词误删长词的一部分
        stop_phrases = [
            # 长短语优先
            "请问一下", "想问一下", "问一下", "想知道", "我想问", "我想知道",
            "可不可以", "能不能", "怎么样", "好不好",
            "帮我看看", "帮我查查", "帮我问问",
            "麻烦问一下", "麻烦帮我",
            # 常见开头语
            "你好", "您好", "请问", "我想", "帮我", "麻烦",
            # 常见结尾语
            "谢谢", "感谢", "好的", "可以吗", "行吗", "好吗",
            # 语气词（放最后，只处理句首句尾的）
        ]
        
        # 电商领域同义词映射（用户常用词 → 检索关键词）
        synonym_map = {
            # 促销活动相关
            "促销活动": "优惠活动", "促销": "优惠活动", "活动": "优惠活动",
            "有什么活动": "优惠活动", "什么活动": "优惠活动",
            "参加活动": "优惠活动", "参加": "参与",
            # 价格相关
            "多少钱": "价格", "什么价": "价格", "价位": "价格", 
            "贵不贵": "价格", "便宜": "优惠", "打折": "折扣优惠",
            "优惠券": "优惠券", "满减": "满减活动", "红包": "优惠红包",
            # 物流相关
            "发货": "物流配送", "快递": "物流", "送货": "配送",
            "到货": "送达", "几天到": "配送时间", "多久到": "配送时间",
            "包邮": "免运费", "邮费": "运费", "运费多少": "运费",
            # 售后相关
            "退货": "退换货", "换货": "退换货", "退款": "退款",
            "保修": "质保", "售后": "售后服务", "维修": "维修",
            "坏了": "故障", "不能用": "故障", "质量问题": "质量",
            # 商品相关
            "有货吗": "库存", "有没有货": "库存", "缺货": "库存",
            "尺码": "尺寸", "大小": "尺寸", "颜色": "颜色",
            "款式": "款式", "型号": "型号", "规格": "规格",
            # 支付相关
            "付款": "支付", "怎么付": "支付方式", 
            "分期": "分期付款", "花呗": "支付", "信用卡": "支付",
            # 订单相关
            "订单": "订单", "查单": "订单查询", "取消订单": "取消订单",
            "修改订单": "修改订单", "订单状态": "订单查询",
            # 账户相关
            "密码": "密码", "登录": "登录", "注册": "注册", "账号": "账户"
        }
        
        # 1. 移除停用短语（按长度从长到短，避免误删）
        cleaned_query = query
        for phrase in stop_phrases:
            cleaned_query = cleaned_query.replace(phrase, " ")
        
        # 清理多余空格
        cleaned_query = " ".join(cleaned_query.split()).strip()
        
        # 如果清理后为空或太短，保留原始查询的核心部分
        if len(cleaned_query) < 2:
            cleaned_query = query
        
        # 2. 同义词扩展 - 在原始查询中查找，添加检索关键词
        expanded_terms = []
        for user_term, search_term in synonym_map.items():
            if user_term in query:
                # 避免重复添加
                if search_term not in cleaned_query and search_term not in expanded_terms:
                    expanded_terms.append(search_term)
        
        # 3. 构建改写后的查询
        if expanded_terms:
            rewritten = f"{cleaned_query} {' '.join(expanded_terms)}"
        else:
            rewritten = cleaned_query
        
        return rewritten

    def _merge_results(self, result_sets: List[List[Tuple[KnowledgeItem, float]]], limit: int) -> List[Tuple[KnowledgeItem, float]]:
        best: Dict[str, Tuple[KnowledgeItem, float]] = {}
        for results in result_sets:
            for item, score in results:
                prev = best.get(item.id)
                if prev is None or score > prev[1]:
                    best[item.id] = (item, score)

        merged = list(best.values())
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:limit]

    def _compute_confidence(self, query: str, results: List[Tuple[KnowledgeItem, float]]) -> float:
        if not results:
            return 0.0

        top1 = results[0][1]
        top2 = results[1][1] if len(results) >= 2 else None
        gap = (top1 - top2) if top2 is not None else 0.0

        item = results[0][0]
        keywords = [k for k in (item.keywords or []) if k]
        if keywords:
            denom = min(len(keywords), 6)
            hit = sum(1 for kw in keywords[:denom] if kw in query)
            keyword_cover = hit / max(1, denom)
        else:
            keyword_cover = 0.0

        top_k_bonus = (min(len(results), 5) - 1) / 4 if len(results) >= 2 else 0.0

        confidence = top1
        confidence += 0.15 * max(0.0, min(gap, 1.0))
        confidence += 0.08 * max(0.0, min(keyword_cover, 1.0))
        confidence += 0.04 * max(0.0, min(top_k_bonus, 1.0))

        if confidence < 0.0:
            confidence = 0.0
        if confidence > 1.0:
            confidence = 1.0
        return confidence

    def _average_vectors(self, vectors: List[List[float]]) -> Optional[List[float]]:
        if not vectors:
            return None
        dim = len(vectors[0])
        acc = [0.0] * dim
        for vec in vectors:
            if not vec or len(vec) != dim:
                return None
            for i, v in enumerate(vec):
                acc[i] += v
        n = float(len(vectors))
        return [v / n for v in acc]

    def _item_base_text(self, item: "KnowledgeItem") -> str:
        return f"{item.question} {item.answer}".strip()

    def _make_chunk_id(self, item_id: str, chunk_idx: int) -> str:
        return f"{item_id}#chunk_{int(chunk_idx)}"

    def _split_chunk_id(self, stored_id: str) -> Tuple[Optional[str], Optional[int]]:
        if not stored_id:
            return None, None
        if "#" not in stored_id:
            return stored_id, None
        base, rest = stored_id.split("#", 1)
        base = (base or "").strip()
        if not base:
            return None, None
        m = re.search(r"(\d+)", rest or "")
        if not m:
            return base, None
        try:
            return base, int(m.group(1))
        except Exception:
            return base, None

    def _extract_tokens(self, text: str) -> List[str]:
        s = (text or "").strip()
        if not s:
            return []

        tokens: List[str] = []
        s_lower = s.lower()
        tokens.extend(re.findall(r"[a-z0-9]{2,}", s_lower))
        for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s):
            seg = seg.strip()
            if not seg:
                continue
            tokens.append(seg)
            remain = 12
            for i in range(len(seg) - 1):
                if remain <= 0:
                    break
                tokens.append(seg[i : i + 2])
                remain -= 1

        seen = set()
        uniq: List[str] = []
        for t in tokens:
            if t and t not in seen:
                seen.add(t)
                uniq.append(t)
            if len(uniq) >= 40:
                break
        return uniq

    def _keyword_coverage_score(self, query: str, item: "KnowledgeItem", chunk_texts: Optional[List[str]] = None) -> float:
        tokens = self._extract_tokens(query)
        if not tokens:
            return 0.0

        q = (query or "").strip()
        base_text = self._item_base_text(item)
        pool = (chunk_texts or []) + [item.question or "", item.answer or "", base_text]

        hits = 0
        for t in tokens:
            if any(t in p for p in pool if p):
                hits += 1

        cover = hits / max(1, len(tokens))

        kw_hits = 0
        for kw in (item.keywords or []):
            if kw and kw in q:
                kw_hits += 1
        kw_bonus = min(1.0, 0.4 * kw_hits)

        return min(1.0, 0.75 * cover + 0.25 * kw_bonus)

    def _vector_search_multi(self, queries: List[str], threshold: float) -> List[Tuple[KnowledgeItem, float]]:
        embedding_client = self._get_embedding_client()
        vector_store = self._get_vector_store()
        if not embedding_client or not vector_store:
            return []
        if not embedding_client.is_available():
            logger.warning("Embedding服务不可用，降级到关键词匹配")
            return []

        uniq = []
        for q in queries:
            q = (q or "").strip()
            if q and q not in uniq:
                uniq.append(q)
        if not uniq:
            return []

        vecs = embedding_client.embed_texts(uniq)
        if not vecs:
            return []

        top_k = self.config.get("retrieval_top_k", 5)
        best: Dict[str, Tuple[KnowledgeItem, float]] = {}
        best_chunks: Dict[str, List[str]] = {}

        for q, vec in zip(uniq, vecs):
            results, chunk_map = self._vector_search_vec_detailed(q, vec, threshold)
            for item, score in results:
                prev = best.get(item.id)
                if prev is None or score > prev[1]:
                    best[item.id] = (item, score)
                    parts = chunk_map.get(item.id)
                    if parts:
                        best_chunks[item.id] = parts

        merged = list(best.values())
        merged.sort(key=lambda x: x[1], reverse=True)
        merged = merged[:top_k]
        self._last_chunk_map = best_chunks
        return merged

    def _keyword_search_multi(self, queries: List[str], threshold: float) -> List[Tuple[KnowledgeItem, float]]:
        uniq = []
        for q in queries:
            q = (q or "").strip()
            if q and q not in uniq:
                uniq.append(q)
        if not uniq:
            return []

        top_k = self.config.get("retrieval_top_k", 5)
        result_sets = [self._keyword_search(q, threshold) for q in uniq]
        return self._merge_results(result_sets, top_k)
    
    def search(self, query: str, threshold: float = None) -> List[Tuple[KnowledgeItem, float]]:
        """搜索知识库，优先使用向量检索，失败时降级到关键词匹配"""
        import time as time_module
        start_time = time_module.perf_counter()
        search_method = "keyword"
        
        if threshold is None:
            threshold = self.config.get("similarity_threshold", 0.4)
        
        # 初始化搜索结果
        self._last_search_result = RAGSearchResult()
        self._last_chunk_map = {}
        self._last_search_result.query = query
        rewritten_query = self._rewrite_query(query)
        self._last_search_result.rewritten_query = rewritten_query

        queries = [rewritten_query, query]
        
        results = self._vector_search_multi(queries, threshold)
        
        if results:
            self._last_search_result.search_method = "vector"
            search_method = "vector"
        else:
            results = self._keyword_search_multi(queries, threshold)
            self._last_search_result.search_method = "keyword"
            search_method = "keyword"
        
        self._last_search_result.retrieved_items = results
        
        # 构建上下文
        if results:
            context_parts: List[str] = []
            max_context_chars = int(self.config.get("context_max_chars", 4000) or 4000)
            context_top_n = int(self.config.get("context_top_n", 3) or 3)

            total = 0
            chunk_map = self._last_chunk_map or {}

            for item, _ in results[:max(1, context_top_n)]:
                parts = chunk_map.get(item.id)
                if not parts:
                    parts = [f"问题：{item.question}\n答案：{item.answer}"]
                for p in parts:
                    p = (p or "").strip()
                    if not p:
                        continue
                    next_total = total + len(p)
                    if max_context_chars > 0 and next_total > max_context_chars:
                        if not context_parts:
                            context_parts.append(truncate_text(p, max_context_chars))
                        total = max_context_chars
                        break
                    context_parts.append(p)
                    total = next_total
                if max_context_chars > 0 and total >= max_context_chars:
                    break

            self._last_search_result.context_text = "\n\n---\n\n".join(context_parts)
            self._last_search_result.confidence = self._compute_confidence(query, results)
        else:
            self._last_search_result.confidence = 0.0

        max_context_chars = self.config.get("context_max_chars", 4000)
        system_prompt = build_system_prompt(
            truncate_text(self._last_search_result.context_text, max_context_chars) if self._last_search_result.context_text else None
        )
        messages = build_messages(system_prompt, query)
        self._last_search_result.final_prompt = format_prompt_preview(messages)
        
        # 记录性能指标
        duration = time_module.perf_counter() - start_time
        perf_monitor = self._get_perf_monitor()
        if perf_monitor:
            metric_name = "vector_search" if search_method == "vector" else "keyword_search"
            perf_monitor.record(metric_name, duration, True, {
                "query_length": len(query),
                "results_count": len(results)
            })
        
        return results

    def _vector_search_vec_detailed(
        self,
        query: str,
        query_vec: List[float],
        threshold: float,
    ) -> Tuple[List[Tuple[KnowledgeItem, float]], Dict[str, List[str]]]:
        vector_store = self._get_vector_store()
        if not vector_store or not query_vec:
            return [], {}

        top_k = int(self.config.get("retrieval_top_k", 5) or 5)
        candidate_k = max(top_k * 3, top_k)
        raw = vector_store.search(query_vec, candidate_k)

        last_error = getattr(vector_store, "last_error", None)
        if last_error and isinstance(last_error, dict) and last_error.get("type") == "dimension_mismatch":
            expected = last_error.get("expected")
            actual = last_error.get("actual")
            logger.warning(
                "向量索引维度不匹配，已自动禁用向量检索: 索引维度%s, 向量维度%s",
                expected,
                actual,
            )
            return [], {}

        chunk_top_n = int(self.config.get("chunk_top_n", 2) or 2)

        hits: Dict[str, dict] = {}
        for stored_id, score in raw:
            if score < threshold:
                continue
            item_id, chunk_idx = self._split_chunk_id(stored_id)
            if not item_id:
                continue
            item = self.get_item_by_id(item_id)
            if not item:
                continue

            h = hits.get(item_id)
            if h is None:
                h = {"item": item, "max": float(score), "chunks": {}}
                hits[item_id] = h
            else:
                if float(score) > float(h.get("max", 0.0)):
                    h["max"] = float(score)

            base_text = self._item_base_text(item)
            if chunk_idx is None:
                chunk_text = base_text
            else:
                parts = self._chunk_text(base_text)
                if 0 <= chunk_idx < len(parts):
                    chunk_text = parts[chunk_idx]
                else:
                    chunk_text = base_text

            chunks: Dict[str, float] = h["chunks"]
            prev = chunks.get(chunk_text)
            if prev is None or float(score) > float(prev):
                chunks[chunk_text] = float(score)

        if not hits:
            return [], {}

        ranked: List[Tuple[KnowledgeItem, float]] = []
        chunk_map: Dict[str, List[str]] = {}
        for item_id, h in hits.items():
            item = h["item"]
            max_score = float(h.get("max", 0.0))
            chunks: Dict[str, float] = h.get("chunks") or {}
            best_chunks = sorted(chunks.items(), key=lambda x: x[1], reverse=True)[: max(1, chunk_top_n)]
            chunk_texts = [t for t, _ in best_chunks if t]

            cover = self._keyword_coverage_score(query, item, chunk_texts)
            bonus = min(0.25, 0.25 * cover)
            final_score = max_score + bonus
            if final_score > 1.0:
                final_score = 1.0

            ranked.append((item, final_score))

            formatted: List[str] = []
            for t in chunk_texts[: max(1, chunk_top_n)]:
                formatted.append(f"问题：{item.question}\n内容：{t}")
            if formatted:
                chunk_map[item_id] = formatted

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k], chunk_map
    
    def _vector_search(self, query: str, threshold: float) -> List[Tuple[KnowledgeItem, float]]:
        """向量检索"""
        embedding_client = self._get_embedding_client()
        vector_store = self._get_vector_store()
        
        if not embedding_client or not vector_store:
            return []
        
        if not embedding_client.is_available():
            logger.warning("Embedding服务不可用，降级到关键词匹配")
            return []
        
        # 向量化查询
        query_vec = embedding_client.embed_text(query)
        if not query_vec:
            return []
        
        # 搜索
        top_k = self.config.get("retrieval_top_k", 5)
        search_results = vector_store.search(query_vec, top_k)

        last_error = getattr(vector_store, "last_error", None)
        if last_error and isinstance(last_error, dict) and last_error.get("type") == "dimension_mismatch":
            expected = last_error.get("expected")
            actual = last_error.get("actual")
            logger.warning(
                "向量索引维度不匹配，已自动禁用向量检索: 索引维度%s, 向量维度%s",
                expected,
                actual,
            )
            return []
        
        results = []
        for item_id, score in search_results:
            if score >= threshold:
                # 找到对应的知识条目
                item = self.get_item_by_id(item_id)
                if item:
                    results.append((item, score))
        
        return results
    
    def _keyword_search(self, query: str, threshold: float) -> List[Tuple[KnowledgeItem, float]]:
        """关键词匹配（使用倒排索引加速）"""
        results: List[Tuple[KnowledgeItem, float]] = []
        q = (query or "").strip()
        if not q:
            return []

        q_lower = q.lower()
        tokens = self._extract_tokens(q)
        if not tokens:
            tokens = [q]

        top_k = int(self.config.get("retrieval_top_k", 5) or 5)
        
        # 使用倒排索引快速获取候选集
        candidate_ids = set()
        if self._index_built and self._inverted_index:
            for token in tokens:
                token_lower = token.lower()
                if token_lower in self._inverted_index:
                    candidate_ids.update(self._inverted_index[token_lower])
            
            # 如果倒排索引没有命中，回退到全量搜索
            if not candidate_ids:
                candidate_ids = {item.id for item in self.items}
        else:
            candidate_ids = {item.id for item in self.items}
        
        # 只对候选集进行详细评分
        for item in self.items:
            if item.id not in candidate_ids:
                continue
                
            score = 0.0

            kw_hits = 0
            for keyword in (item.keywords or []):
                if keyword and keyword in q:
                    kw_hits += 1
            if kw_hits:
                score += min(0.7, 0.35 * kw_hits)

            q_hit = 0
            a_hit = 0
            for t in tokens:
                if t and item.question and t in item.question:
                    q_hit += 1
                if t and item.answer and t in item.answer:
                    a_hit += 1

            denom = max(1, len(tokens))
            score += 0.22 * (q_hit / denom)
            score += 0.14 * (a_hit / denom)

            if item.question and q_lower in item.question.lower():
                score += 0.12
            if item.answer and q_lower in item.answer.lower():
                score += 0.08

            if score >= threshold:
                if score > 1.0:
                    score = 1.0
                results.append((item, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def get_item_by_id(self, item_id: str) -> Optional[KnowledgeItem]:
        """根据ID获取知识条目"""
        for item in self.items:
            if item.id == item_id:
                return item
        return None
    
    def get_last_search_result(self) -> Optional[RAGSearchResult]:
        """获取最近一次搜索的详细结果（用于RAG追溯）"""
        return self._last_search_result
    
    def check_duplicate(self, question: str, threshold: float = 0.85) -> Optional[Tuple[KnowledgeItem, float]]:
        """检查是否存在重复或相似的知识条目
        
        Args:
            question: 要检查的问题
            threshold: 相似度阈值（0-1）
        
        Returns:
            如果存在相似条目，返回 (条目, 相似度)，否则返回 None
        """
        if not question or not question.strip():
            return None
        
        question = question.strip().lower()
        
        # 1. 精确匹配检查
        for item in self.items:
            if item.question.strip().lower() == question:
                return (item, 1.0)
        
        # 2. 简单相似度检查（基于字符重叠）
        def simple_similarity(s1: str, s2: str) -> float:
            """计算简单的字符级相似度"""
            s1, s2 = s1.lower(), s2.lower()
            if not s1 or not s2:
                return 0.0
            
            # 使用字符集合的Jaccard相似度
            set1 = set(s1)
            set2 = set(s2)
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            
            if union == 0:
                return 0.0
            
            return intersection / union
        
        best_match = None
        best_score = 0.0
        
        for item in self.items:
            score = simple_similarity(question, item.question)
            if score > best_score:
                best_score = score
                best_match = item
        
        if best_match and best_score >= threshold:
            return (best_match, best_score)
        
        # 3. 如果向量检索可用，使用向量相似度
        embedding_client = self._get_embedding_client()
        vector_store = self._get_vector_store()
        
        if embedding_client and vector_store and embedding_client.is_available():
            try:
                query_vec = embedding_client.embed_text(question)
                if query_vec:
                    results = vector_store.search(query_vec, top_k=1)
                    if results:
                        item_id, score = results[0]
                        if score >= threshold:
                            item = self.get_item_by_id(item_id.split("#")[0])  # 处理chunk ID
                            if item:
                                return (item, score)
            except Exception as e:
                logger.debug("向量相似度检查失败: %s", e)
        
        return None
    
    def add_item(self, question: str, answer: str, keywords: List[str], category: str = "通用") -> KnowledgeItem:
        """添加知识条目"""
        # 性能监控
        perf = self._get_perf_monitor()
        if perf:
            perf.record("knowledge_add", 0.0, True)
        
        # 生成新ID
        max_id = 0
        for item in self.items:
            try:
                num = int(item.id[1:])
                max_id = max(max_id, num)
            except:
                pass
        item_id = f"K{max_id + 1:03d}"
        
        item = KnowledgeItem(
            id=item_id,
            question=question,
            answer=answer,
            keywords=keywords,
            category=category
        )
        self.items.append(item)
        self._save_to_file()
        
        # 更新倒排索引
        self._update_inverted_index(item, remove=False)
        
        # 同步更新向量索引
        self._add_to_vector_index(item)
        
        return item
    
    def _add_to_vector_index(self, item: KnowledgeItem):
        """将知识条目添加到向量索引"""
        self._last_vector_index_error = None
        embedding_client = self._get_embedding_client()
        vector_store = self._get_vector_store()
        
        if not embedding_client or not vector_store:
            return
        
        if not embedding_client.is_available():
            return
        
        try:
            vector_store.remove_vector(item.id)
            vector_store.remove_vectors_by_prefix(f"{item.id}#")
        except Exception:
            pass

        text = self._item_base_text(item)
        chunks = self._chunk_text(text)
        max_chunks = int(self.config.get("chunk_max_per_item", 6) or 6)
        chunks = [c for c in (chunks[:max(1, max_chunks)] if chunks else [text]) if c]
        if not chunks:
            return

        vecs = embedding_client.embed_texts(chunks)
        if not vecs or len(vecs) != len(chunks):
            return

        for i, vec in enumerate(vecs):
            if not vec:
                continue
            cid = self._make_chunk_id(item.id, i)
            ok = vector_store.add_vector(cid, vec)
            if not ok:
                last_error = getattr(vector_store, "last_error", None)
                if isinstance(last_error, dict):
                    self._last_vector_index_error = last_error
                logger.warning("向量索引未更新: %s", item.id)
                return

        vector_store.save()
        logger.info("已添加向量索引: %s", item.id)
    
    def delete_item(self, item_id: str) -> bool:
        """删除知识条目"""
        for i, item in enumerate(self.items):
            if item.id == item_id:
                # 先更新倒排索引
                self._update_inverted_index(item, remove=True)
                
                del self.items[i]
                self._save_to_file()
                
                # 同步删除向量索引
                vector_store = self._get_vector_store()
                if vector_store:
                    vector_store.remove_vector(item_id)
                    vector_store.remove_vectors_by_prefix(f"{item_id}#")
                    vector_store.save()
                
                return True
        return False
    
    def update_item(self, item_id: str, **kwargs) -> bool:
        """更新知识条目"""
        for item in self.items:
            if item.id == item_id:
                # 先从倒排索引中移除旧数据
                self._update_inverted_index(item, remove=True)
                
                for key, value in kwargs.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
                self._save_to_file()
                
                # 添加新数据到倒排索引
                self._update_inverted_index(item, remove=False)
                
                # 重新索引向量
                self._add_to_vector_index(item)
                
                return True
        return False
    
    def rebuild_vector_index(self, progress_callback: Callable[[str, int, int], None] = None) -> Tuple[bool, str]:
        """重建向量索引"""
        self._last_vector_index_error = None
        embedding_client = self._get_embedding_client()
        vector_store = self._get_vector_store()
        
        if not embedding_client:
            return False, "Embedding客户端不可用"
        
        if not vector_store:
            return False, "向量存储不可用"
        
        if not embedding_client.is_available():
            return False, "请先配置API密钥"
        
        # 清空索引
        if progress_callback:
            progress_callback("清空索引", 0, 1)
        vector_store.clear()
        
        max_chunks = int(self.config.get("chunk_max_per_item", 6) or 6)

        chunk_texts: List[str] = []
        chunk_ids: List[str] = []
        for item in self.items:
            text = self._item_base_text(item)
            chunks = self._chunk_text(text)
            chunks = [c for c in (chunks[:max(1, max_chunks)] if chunks else [text]) if c]
            for i, c in enumerate(chunks):
                chunk_texts.append(c)
                chunk_ids.append(self._make_chunk_id(item.id, i))

        if progress_callback:
            progress_callback("向量化", 0, max(len(chunk_texts), 1))
        vectors = embedding_client.embed_texts(chunk_texts)
        if not vectors or len(vectors) != len(chunk_texts):
            return False, "向量化失败"

        wrote = 0
        if progress_callback:
            progress_callback("写入索引", 0, max(len(chunk_texts), 1))
        for i, (cid, vec) in enumerate(zip(chunk_ids, vectors)):
            if vec:
                ok = vector_store.add_vector(cid, vec)
                if not ok:
                    self._last_vector_index_error = getattr(vector_store, "last_error", None)
                    return False, "写入索引失败，请检查Embedding模型并重建索引"
                wrote += 1
            if progress_callback:
                progress_callback("写入索引", i + 1, max(len(chunk_texts), 1))

        vector_store.save()
        return True, f"成功索引 {len(self.items)} 条知识（{wrote} 个chunk向量）"
    
    def get_all_items(self) -> List[KnowledgeItem]:
        """获取所有条目"""
        return self.items.copy()
    
    def get_categories(self) -> List[str]:
        """获取所有分类"""
        return list(set(item.category for item in self.items))
    
    def reload(self):
        """重新加载知识库"""
        self._load_from_file()
        # 重建倒排索引
        self._build_inverted_index()


class ProductStore:
    """商品存储 - JSON文件持久化 + 知识库同步"""
    
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
        self.products: List[ProductItem] = []
        self._data_file = self._get_data_file()
        self._knowledge_store = None
        self._load_from_file()
    
    def _get_knowledge_store(self):
        """延迟加载知识库"""
        if self._knowledge_store is None:
            self._knowledge_store = KnowledgeStore()
        return self._knowledge_store
    
    def _get_data_file(self) -> str:
        """获取数据文件路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "products.json")
    
    def _load_from_file(self):
        """从JSON文件加载商品"""
        if os.path.exists(self._data_file):
            try:
                with open(self._data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.products = [ProductItem.from_dict(item) for item in data.get("products", [])]
                    logger.info("已加载 %s 个商品", len(self.products))
            except Exception as e:
                logger.exception("加载商品数据失败")
                self.products = []
        else:
            self.products = []
            self._save_to_file()
    
    def _save_to_file(self):
        """保存商品到JSON文件（带文件锁）"""
        try:
            from core.file_lock import FileLock
            
            data = {
                "products": [product.to_dict() for product in self.products],
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 使用文件锁保护写入
            lock = FileLock(self._data_file, timeout=5.0)
            with lock:
                with open(self._data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("商品数据已保存，共 %s 个", len(self.products))
        except TimeoutError:
            logger.error("保存商品数据失败：无法获取文件锁")
        except Exception as e:
            logger.exception("保存商品数据失败")
    
    def _get_product_knowledge_ids(self, product_id: str) -> List[str]:
        """获取商品对应的知识条目ID列表"""
        return [f"{product_id}_K{i}" for i in range(1, 5)]  # 最多4个知识条目
    
    def add_product(self, name: str, price: float, category: str, description: str,
                    specifications: Dict[str, str] = None, stock: int = 0,
                    keywords: List[str] = None) -> ProductItem:
        """添加商品"""
        # 生成新ID
        max_id = 0
        for product in self.products:
            try:
                num = int(product.id[1:])
                max_id = max(max_id, num)
            except:
                pass
        product_id = f"P{max_id + 1:03d}"
        
        product = ProductItem(
            id=product_id,
            name=name,
            price=price,
            category=category,
            description=description,
            specifications=specifications or {},
            stock=stock,
            keywords=keywords or []
        )
        self.products.append(product)
        self._save_to_file()
        
        # 同步添加知识条目
        self._sync_product_to_knowledge(product)
        
        return product
    
    def _sync_product_to_knowledge(self, product: ProductItem):
        """将商品信息同步到知识库"""
        knowledge_store = self._get_knowledge_store()
        knowledge_items = product.generate_knowledge_items()
        
        for i, item_data in enumerate(knowledge_items, 1):
            # 使用特殊ID格式：商品ID_K序号
            item_id = f"{product.id}_K{i}"
            
            # 检查是否已存在，如果存在则更新
            existing = knowledge_store.get_item_by_id(item_id)
            if existing:
                knowledge_store.update_item(
                    item_id,
                    question=item_data["question"],
                    answer=item_data["answer"],
                    keywords=item_data["keywords"],
                    category=item_data["category"]
                )
            else:
                # 手动创建知识条目
                new_item = KnowledgeItem(
                    id=item_id,
                    question=item_data["question"],
                    answer=item_data["answer"],
                    keywords=item_data["keywords"],
                    category=item_data["category"]
                )
                knowledge_store.items.append(new_item)
                knowledge_store._save_to_file()
                knowledge_store._add_to_vector_index(new_item)

        logger.info("已同步商品 %s 的 %s 条知识", product.id, len(knowledge_items))
    
    def delete_product(self, product_id: str) -> bool:
        """删除商品"""
        for i, product in enumerate(self.products):
            if product.id == product_id:
                del self.products[i]
                self._save_to_file()
                
                # 同步删除知识条目
                self._remove_product_knowledge(product_id)
                
                return True
        return False
    
    def _remove_product_knowledge(self, product_id: str):
        """删除商品对应的知识条目"""
        knowledge_store = self._get_knowledge_store()
        knowledge_ids = self._get_product_knowledge_ids(product_id)
        
        for kid in knowledge_ids:
            knowledge_store.delete_item(kid)

        logger.info("已删除商品 %s 的知识条目", product_id)
    
    def update_product(self, product_id: str, **kwargs) -> bool:
        """更新商品"""
        for product in self.products:
            if product.id == product_id:
                for key, value in kwargs.items():
                    if hasattr(product, key):
                        setattr(product, key, value)
                self._save_to_file()
                
                # 重新同步知识条目
                self._remove_product_knowledge(product_id)
                self._sync_product_to_knowledge(product)
                
                return True
        return False
    
    def get_product_by_id(self, product_id: str) -> Optional[ProductItem]:
        """根据ID获取商品"""
        for product in self.products:
            if product.id == product_id:
                return product
        return None
    
    def get_all_products(self) -> List[ProductItem]:
        """获取所有商品"""
        return self.products.copy()
    
    def get_categories(self) -> List[str]:
        """获取所有商品分类"""
        return list(set(product.category for product in self.products))
    
    def search_products(self, query: str) -> List[ProductItem]:
        """搜索商品"""
        query_lower = query.lower()
        results = []
        for product in self.products:
            if (query_lower in product.name.lower() or
                query_lower in product.description.lower() or
                any(query_lower in kw.lower() for kw in product.keywords)):
                results.append(product)
        return results
    
    def reload(self):
        """重新加载商品数据"""
        self._load_from_file()
    
    def sync_all_to_knowledge(self) -> tuple:
        """将所有商品同步到知识库"""
        success_count = 0
        fail_count = 0
        
        for product in self.products:
            try:
                self._sync_product_to_knowledge(product)
                success_count += 1
            except Exception as e:
                logger.exception("同步商品 %s 失败", product.id)
                fail_count += 1
        
        return success_count, fail_count
