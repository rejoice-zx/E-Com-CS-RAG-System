# -*- coding: utf-8 -*-
"""
向量存储模块 - 使用FAISS进行向量存储和检索

优化内容 (v2.2.0):
- 向量维度不匹配时提供自动修复建议
- 添加索引状态检查方法

优化内容 (v2.3.0):
- 支持多种索引类型：Flat、IVF、HNSW
- 大规模数据自动切换压缩索引
- 索引类型可配置，支持精度/空间权衡
"""

import os
import json
import numpy as np
import logging
from typing import List, Tuple, Optional, Dict
from enum import Enum


logger = logging.getLogger(__name__)

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss-cpu未安装，将使用简单的numpy检索")


class IndexType(Enum):
    """索引类型枚举"""
    FLAT = "flat"           # 精确搜索，适合小规模数据（<10000）
    IVF = "ivf"             # 倒排索引，适合中等规模（10000-100000）
    HNSW = "hnsw"           # 层次导航小世界图，适合大规模数据（>100000）
    AUTO = "auto"           # 自动选择


# 索引类型阈值
INDEX_THRESHOLD_IVF = 1000      # 超过此数量使用IVF
INDEX_THRESHOLD_HNSW = 50000    # 超过此数量使用HNSW


class VectorStore:
    """向量存储类 - 基于FAISS，支持多种索引类型"""
    
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
        
        self._dimension = 1024  # 默认维度，会根据实际embedding动态调整
        self._index = None
        self._index_type: IndexType = IndexType.FLAT
        self._id_map: Dict[int, str] = {}  # FAISS内部ID -> 知识ID
        self._reverse_map: Dict[str, int] = {}  # 知识ID -> FAISS内部ID
        self._next_id = 0
        self._built_embedding_model: Optional[str] = None
        self._last_error: Optional[dict] = None
        self._pending_vectors: List[Tuple[int, np.ndarray]] = []  # IVF训练前暂存
        self._is_trained = False
        
        self._data_dir = self._get_data_dir()
        self._index_file = os.path.join(self._data_dir, "vectors.index")
        self._map_file = os.path.join(self._data_dir, "vectors_map.json")
        
        self._load_index()
    
    def _get_data_dir(self) -> str:
        """获取数据目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    def _get_current_embedding_model(self) -> Optional[str]:
        try:
            from core.config import Config
            return Config().get("embedding_model")
        except Exception:
            return None
    
    def _create_index(self, dimension: int, embedding_model: Optional[str] = None, 
                       index_type: IndexType = IndexType.AUTO, expected_count: int = 0):
        """创建FAISS索引
        
        Args:
            dimension: 向量维度
            embedding_model: embedding模型名称
            index_type: 索引类型
            expected_count: 预期数据量（用于自动选择索引类型）
        """
        self._dimension = dimension
        if embedding_model is not None:
            self._built_embedding_model = embedding_model
        elif self._built_embedding_model is None:
            self._built_embedding_model = self._get_current_embedding_model()
        
        # 自动选择索引类型
        if index_type == IndexType.AUTO:
            if expected_count >= INDEX_THRESHOLD_HNSW:
                index_type = IndexType.HNSW
            elif expected_count >= INDEX_THRESHOLD_IVF:
                index_type = IndexType.IVF
            else:
                index_type = IndexType.FLAT
        
        self._index_type = index_type
        self._pending_vectors = []
        self._is_trained = False
        
        if FAISS_AVAILABLE:
            if index_type == IndexType.HNSW:
                # HNSW索引：高召回率，适合大规模数据
                # M=32: 每个节点的连接数，越大精度越高但内存越大
                # efConstruction=200: 构建时的搜索深度
                self._index = faiss.IndexHNSWFlat(dimension, 32)
                self._index.hnsw.efConstruction = 200
                self._index.hnsw.efSearch = 64  # 搜索时的深度
                self._is_trained = True  # HNSW不需要训练
                logger.info(f"创建HNSW索引，维度: {dimension}")
                
            elif index_type == IndexType.IVF:
                # IVF索引：需要训练，适合中等规模数据
                # nlist: 聚类中心数，通常为 sqrt(n) 到 4*sqrt(n)
                nlist = max(16, min(256, int(np.sqrt(max(expected_count, 1000)))))
                quantizer = faiss.IndexFlatIP(dimension)
                self._index = faiss.IndexIVFFlat(quantizer, dimension, nlist, faiss.METRIC_INNER_PRODUCT)
                self._is_trained = False
                logger.info(f"创建IVF索引，维度: {dimension}, nlist: {nlist}")
                
            else:
                # Flat索引：精确搜索
                base_index = faiss.IndexFlatIP(dimension)
                self._index = faiss.IndexIDMap2(base_index)
                self._is_trained = True
                logger.info(f"创建Flat索引，维度: {dimension}")
        else:
            # 降级为简单的numpy存储
            self._vectors = []
            self._is_trained = True
    
    def _load_index(self):
        """加载索引"""
        # 加载ID映射
        if os.path.exists(self._map_file):
            try:
                with open(self._map_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._id_map = {int(k): v for k, v in data.get("id_map", {}).items()}
                    self._reverse_map = data.get("reverse_map", {})
                    self._next_id = data.get("next_id", 0)
                    self._dimension = data.get("dimension", 1024)
                    self._built_embedding_model = data.get("embedding_model")
                    # 加载索引类型
                    index_type_str = data.get("index_type", "flat")
                    try:
                        self._index_type = IndexType(index_type_str)
                    except ValueError:
                        self._index_type = IndexType.FLAT
                    self._is_trained = data.get("is_trained", True)
            except Exception as e:
                logger.exception("加载向量映射失败")
        
        # 加载FAISS索引
        if FAISS_AVAILABLE and os.path.exists(self._index_file):
            try:
                loaded = faiss.read_index(self._index_file)
                self._index = loaded
                
                # 检测索引类型
                if isinstance(loaded, faiss.IndexHNSWFlat):
                    self._index_type = IndexType.HNSW
                    self._is_trained = True
                    if hasattr(loaded, 'd'):
                        self._dimension = loaded.d
                elif isinstance(loaded, faiss.IndexIVFFlat):
                    self._index_type = IndexType.IVF
                    self._is_trained = loaded.is_trained
                    if hasattr(loaded, 'd'):
                        self._dimension = loaded.d
                elif isinstance(loaded, faiss.IndexIDMap) or isinstance(loaded, faiss.IndexIDMap2):
                    self._index_type = IndexType.FLAT
                    self._is_trained = True
                    if hasattr(loaded, 'index') and hasattr(loaded.index, 'd'):
                        self._dimension = loaded.index.d
                else:
                    # 尝试转换为IDMap索引
                    if hasattr(loaded, 'd'):
                        self._dimension = int(loaded.d)
                    
                    vectors = None
                    if hasattr(loaded, 'reconstruct_n') and getattr(loaded, 'ntotal', 0) > 0:
                        vectors = loaded.reconstruct_n(0, loaded.ntotal)
                    
                    base_index = faiss.IndexFlatIP(self._dimension)
                    id_index = faiss.IndexIDMap2(base_index)
                    
                    if vectors is not None and len(vectors) > 0:
                        ids = np.arange(loaded.ntotal, dtype=np.int64)
                        id_index.add_with_ids(vectors, ids)
                        self._next_id = max(self._next_id, int(loaded.ntotal))
                    
                    self._index = id_index
                    self._index_type = IndexType.FLAT
                    self._is_trained = True

                logger.info("已加载向量索引，类型: %s, 维度: %s, 数量: %s", 
                           self._index_type.value, self._dimension, self._index.ntotal)
            except Exception as e:
                logger.exception("加载FAISS索引失败")
                self._create_index(self._dimension)
        else:
            self._create_index(self._dimension)
    
    def _save_index(self):
        """保存索引"""
        # 保存ID映射
        try:
            data = {
                "id_map": {str(k): v for k, v in self._id_map.items()},
                "reverse_map": self._reverse_map,
                "next_id": self._next_id,
                "dimension": self._dimension,
                "embedding_model": self._built_embedding_model,
                "index_type": self._index_type.value,
                "is_trained": self._is_trained
            }
            with open(self._map_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("保存向量映射失败")
        
        # 保存FAISS索引
        if FAISS_AVAILABLE and self._index is not None:
            try:
                faiss.write_index(self._index, self._index_file)
            except Exception as e:
                logger.exception("保存FAISS索引失败")
    
    def add_vector(self, item_id: str, vector: List[float]) -> bool:
        """
        添加向量
        
        Args:
            item_id: 知识条目ID
            vector: 向量
        
        Returns:
            是否成功
        """
        if not vector:
            return False
        
        # 检查维度
        if len(vector) != self._dimension:
            if self._index is None or (FAISS_AVAILABLE and self._index.ntotal == 0):
                # 重新创建索引
                self._create_index(len(vector), embedding_model=self._get_current_embedding_model())
            else:
                self._last_error = {
                    "type": "dimension_mismatch",
                    "expected": self._dimension,
                    "actual": len(vector),
                    "op": "add_vector",
                }
                logger.warning("向量维度不匹配: 期望%s, 实际%s", self._dimension, len(vector))
                return False
        
        # 如果已存在，先删除
        if item_id in self._reverse_map:
            self.remove_vector(item_id)
        
        # 归一化向量
        vec = np.array([vector], dtype=np.float32)
        if FAISS_AVAILABLE:
            faiss.normalize_L2(vec)
        
        internal_id = self._next_id
        self._next_id += 1

        if FAISS_AVAILABLE:
            if self._index_type == IndexType.IVF and not self._is_trained:
                # IVF索引未训练，暂存向量
                self._pending_vectors.append((internal_id, vec[0].copy()))
                logger.debug(f"IVF索引未训练，暂存向量 {item_id}")
            elif self._index_type == IndexType.HNSW:
                # HNSW索引直接添加（不支持ID映射，使用顺序ID）
                self._index.add(vec)
            elif self._index_type == IndexType.FLAT:
                # Flat索引使用IDMap
                ids = np.array([internal_id], dtype=np.int64)
                self._index.add_with_ids(vec, ids)
            else:
                # IVF已训练
                self._index.add(vec)
        else:
            if not hasattr(self, '_vectors'):
                self._vectors = []
            self._vectors.append(vec[0])
        
        # 更新映射
        self._id_map[internal_id] = item_id
        self._reverse_map[item_id] = internal_id
        
        return True
    
    def train_index(self, vectors: Optional[np.ndarray] = None) -> bool:
        """训练IVF索引
        
        Args:
            vectors: 训练用的向量，如果为None则使用暂存的向量
        
        Returns:
            是否成功
        """
        if not FAISS_AVAILABLE:
            return False
        
        if self._index_type != IndexType.IVF:
            logger.debug("非IVF索引，无需训练")
            return True
        
        if self._is_trained:
            logger.debug("索引已训练")
            return True
        
        # 收集训练数据
        if vectors is None:
            if not self._pending_vectors:
                logger.warning("没有可用的训练数据")
                return False
            vectors = np.array([v for _, v in self._pending_vectors], dtype=np.float32)
        
        # 训练需要足够的数据
        min_train_size = max(self._index.nlist, 39)  # FAISS要求至少39个向量
        if len(vectors) < min_train_size:
            logger.warning(f"训练数据不足: {len(vectors)} < {min_train_size}")
            return False
        
        try:
            logger.info(f"开始训练IVF索引，训练数据: {len(vectors)} 条")
            self._index.train(vectors)
            self._is_trained = True
            
            # 添加暂存的向量
            if self._pending_vectors:
                for internal_id, vec in self._pending_vectors:
                    self._index.add(vec.reshape(1, -1))
                logger.info(f"已添加 {len(self._pending_vectors)} 条暂存向量")
                self._pending_vectors = []
            
            return True
        except Exception as e:
            logger.exception("训练IVF索引失败")
            return False
    
    def remove_vector(self, item_id: str) -> bool:
        """
        删除向量（标记删除，实际不从FAISS移除）
        
        Args:
            item_id: 知识条目ID
        
        Returns:
            是否成功
        """
        if item_id not in self._reverse_map:
            return False
        
        internal_id = self._reverse_map[item_id]
        
        # 只有Flat索引支持直接删除
        if FAISS_AVAILABLE and self._index is not None and self._index_type == IndexType.FLAT:
            try:
                remove_ids = np.array([internal_id], dtype=np.int64)
                self._index.remove_ids(remove_ids)
            except Exception as e:
                logger.exception("FAISS删除向量失败")
        
        # 从暂存列表中删除（IVF未训练时）
        if self._pending_vectors:
            self._pending_vectors = [(id, v) for id, v in self._pending_vectors if id != internal_id]

        if internal_id in self._id_map:
            del self._id_map[internal_id]
        del self._reverse_map[item_id]
        
        return True

    def remove_vectors_by_prefix(self, prefix: str) -> int:
        if not prefix:
            return 0
        keys = list(self._reverse_map.keys())
        removed = 0
        for k in keys:
            if k == prefix or k.startswith(prefix):
                if self.remove_vector(k):
                    removed += 1
        return removed
    
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        搜索相似向量
        
        Args:
            query_vector: 查询向量
            top_k: 返回数量
        
        Returns:
            [(知识ID, 相似度分数), ...]
        """
        if not query_vector:
            return []

        if len(query_vector) != self._dimension:
            self._last_error = {
                "type": "dimension_mismatch",
                "expected": self._dimension,
                "actual": len(query_vector),
                "op": "search",
            }
            logger.warning("查询向量维度不匹配: 索引维度%s, 查询维度%s", self._dimension, len(query_vector))
            return []
        
        if self._index is None or (FAISS_AVAILABLE and self._index.ntotal == 0):
            return []
        
        # IVF索引未训练时，搜索暂存向量
        if self._index_type == IndexType.IVF and not self._is_trained:
            return self._search_pending_vectors(query_vector, top_k)
        
        # 归一化查询向量
        vec = np.array([query_vector], dtype=np.float32)
        if FAISS_AVAILABLE:
            faiss.normalize_L2(vec)
        
        results = []
        
        if FAISS_AVAILABLE:
            # 设置IVF搜索参数
            if self._index_type == IndexType.IVF:
                # nprobe: 搜索的聚类数，越大越精确但越慢
                self._index.nprobe = min(16, self._index.nlist)
            
            # FAISS搜索
            k = min(top_k * 2, self._index.ntotal)
            try:
                distances, ids = self._index.search(vec, k)
            except AssertionError:
                logger.exception("FAISS搜索维度断言失败: 索引维度%s, 查询维度%s", self._dimension, len(query_vector))
                return []

            for dist, internal_id in zip(distances[0], ids[0]):
                if internal_id == -1:
                    continue
                
                # HNSW和IVF使用顺序ID，需要通过位置映射
                if self._index_type in (IndexType.HNSW, IndexType.IVF):
                    # 通过ID映射查找
                    kid = self._id_map.get(int(internal_id))
                else:
                    kid = self._id_map.get(int(internal_id))
                
                if not kid:
                    continue
                results.append((kid, float(dist)))
                if len(results) >= top_k:
                    break
        else:
            # numpy降级搜索
            if not hasattr(self, '_vectors') or not self._vectors:
                return []
            
            vectors = np.array(self._vectors)
            # 归一化
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / (norms + 1e-9)
            query = vec[0] / (np.linalg.norm(vec[0]) + 1e-9)
            
            # 计算余弦相似度
            similarities = np.dot(vectors, query)
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            for idx in top_indices:
                if idx in self._id_map:
                    results.append((self._id_map[idx], float(similarities[idx])))
        
        return results
    
    def _search_pending_vectors(self, query_vector: List[float], top_k: int) -> List[Tuple[str, float]]:
        """搜索暂存向量（IVF未训练时使用）"""
        if not self._pending_vectors:
            return []
        
        query = np.array(query_vector, dtype=np.float32)
        query = query / (np.linalg.norm(query) + 1e-9)
        
        scores = []
        for internal_id, vec in self._pending_vectors:
            similarity = np.dot(vec, query)
            kid = self._id_map.get(internal_id)
            if kid:
                scores.append((kid, float(similarity)))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def save(self):
        """保存索引到磁盘"""
        self._save_index()
        logger.info("向量索引已保存，共%s条", len(self._id_map))
    
    def clear(self):
        """清空索引"""
        self._create_index(self._dimension, embedding_model=self._get_current_embedding_model())
        self._id_map.clear()
        self._reverse_map.clear()
        self._next_id = 0
        self._last_error = None
        self._pending_vectors = []
        if hasattr(self, '_vectors'):
            self._vectors = []
    
    @property
    def count(self) -> int:
        """获取向量数量"""
        return len(self._id_map)
    
    def has_item(self, item_id: str) -> bool:
        """检查是否存在某知识的向量"""
        return item_id in self._reverse_map

    @property
    def dimension(self) -> int:
        return int(self._dimension)

    @property
    def embedding_model(self) -> Optional[str]:
        return self._built_embedding_model

    @property
    def last_error(self) -> Optional[dict]:
        return self._last_error

    def check_dimension_compatibility(self, expected_dimension: int) -> Tuple[bool, str]:
        """检查向量维度兼容性
        
        Args:
            expected_dimension: 期望的向量维度
        
        Returns:
            (是否兼容, 提示信息)
        """
        if self._index is None or (FAISS_AVAILABLE and self._index.ntotal == 0):
            return True, "索引为空，可以使用任意维度"
        
        if self._dimension == expected_dimension:
            return True, "维度匹配"
        
        return False, f"维度不匹配：索引维度为 {self._dimension}，当前模型维度为 {expected_dimension}。请重建向量索引。"
    
    def needs_rebuild(self, current_embedding_model: str = None) -> Tuple[bool, str]:
        """检查是否需要重建索引
        
        Args:
            current_embedding_model: 当前使用的embedding模型名称
        
        Returns:
            (是否需要重建, 原因说明)
        """
        # 检查索引是否为空
        if self._index is None or (FAISS_AVAILABLE and self._index.ntotal == 0):
            if len(self._id_map) == 0:
                return False, "索引为空，无需重建"
            return True, "索引数据丢失，需要重建"
        
        # 检查embedding模型是否变更
        if current_embedding_model and self._built_embedding_model:
            if current_embedding_model != self._built_embedding_model:
                return True, f"Embedding模型已变更（{self._built_embedding_model} → {current_embedding_model}），建议重建索引"
        
        # 检查是否有维度不匹配错误
        if self._last_error and self._last_error.get("type") == "dimension_mismatch":
            return True, f"向量维度不匹配（索引: {self._last_error.get('expected')}, 当前: {self._last_error.get('actual')}），需要重建索引"
        
        return False, "索引状态正常"
    
    def get_index_info(self) -> dict:
        """获取索引信息"""
        info = {
            "dimension": self._dimension,
            "count": len(self._id_map),
            "embedding_model": self._built_embedding_model,
            "faiss_available": FAISS_AVAILABLE,
            "has_error": self._last_error is not None,
            "last_error": self._last_error,
            "index_type": self._index_type.value,
            "is_trained": self._is_trained,
            "pending_count": len(self._pending_vectors),
        }
        
        # 添加索引特定信息
        if FAISS_AVAILABLE and self._index is not None:
            info["ntotal"] = self._index.ntotal
            
            if self._index_type == IndexType.IVF:
                info["nlist"] = self._index.nlist
                info["nprobe"] = getattr(self._index, 'nprobe', None)
            elif self._index_type == IndexType.HNSW:
                if hasattr(self._index, 'hnsw'):
                    info["M"] = self._index.hnsw.M if hasattr(self._index.hnsw, 'M') else 32
                    info["efConstruction"] = self._index.hnsw.efConstruction
                    info["efSearch"] = self._index.hnsw.efSearch
        
        return info
    
    def rebuild_index(self, index_type: IndexType = IndexType.AUTO, 
                      vectors_data: Optional[List[Tuple[str, List[float]]]] = None) -> bool:
        """重建索引
        
        Args:
            index_type: 新的索引类型
            vectors_data: 向量数据列表 [(item_id, vector), ...]，如果为None则需要外部重新添加
        
        Returns:
            是否成功
        """
        try:
            expected_count = len(vectors_data) if vectors_data else len(self._id_map)
            
            # 清空并创建新索引
            self._id_map.clear()
            self._reverse_map.clear()
            self._next_id = 0
            self._pending_vectors = []
            self._last_error = None
            
            self._create_index(
                self._dimension, 
                embedding_model=self._get_current_embedding_model(),
                index_type=index_type,
                expected_count=expected_count
            )
            
            # 如果提供了向量数据，重新添加
            if vectors_data:
                # 收集所有向量用于训练
                all_vectors = []
                for item_id, vector in vectors_data:
                    vec = np.array(vector, dtype=np.float32)
                    if FAISS_AVAILABLE:
                        faiss.normalize_L2(vec.reshape(1, -1))
                    all_vectors.append(vec)
                
                # IVF索引需要先训练
                if self._index_type == IndexType.IVF and all_vectors:
                    train_data = np.array(all_vectors, dtype=np.float32)
                    if len(train_data) >= 39:  # FAISS最小训练数据量
                        self._index.train(train_data)
                        self._is_trained = True
                
                # 添加向量
                for (item_id, vector), vec in zip(vectors_data, all_vectors):
                    internal_id = self._next_id
                    self._next_id += 1
                    
                    if FAISS_AVAILABLE:
                        if self._index_type == IndexType.FLAT:
                            ids = np.array([internal_id], dtype=np.int64)
                            self._index.add_with_ids(vec.reshape(1, -1), ids)
                        else:
                            self._index.add(vec.reshape(1, -1))
                    
                    self._id_map[internal_id] = item_id
                    self._reverse_map[item_id] = internal_id
                
                logger.info(f"索引重建完成，类型: {self._index_type.value}, 数量: {len(vectors_data)}")
            
            return True
        except Exception as e:
            logger.exception("重建索引失败")
            return False
    
    def optimize_index(self) -> Tuple[bool, str]:
        """优化索引（根据数据量自动选择最佳索引类型）
        
        Returns:
            (是否需要优化, 说明信息)
        """
        current_count = len(self._id_map)
        
        # 判断是否需要切换索引类型
        recommended_type = IndexType.FLAT
        if current_count >= INDEX_THRESHOLD_HNSW:
            recommended_type = IndexType.HNSW
        elif current_count >= INDEX_THRESHOLD_IVF:
            recommended_type = IndexType.IVF
        
        if recommended_type == self._index_type:
            return False, f"当前索引类型 {self._index_type.value} 已是最优选择"
        
        return True, f"建议将索引类型从 {self._index_type.value} 切换为 {recommended_type.value}（数据量: {current_count}）"
    
    def get_index_size_estimate(self) -> dict:
        """估算索引大小"""
        count = len(self._id_map)
        dim = self._dimension
        
        # 估算各类型索引大小（字节）
        flat_size = count * dim * 4  # float32
        ivf_size = flat_size * 1.1   # IVF略大（包含聚类信息）
        hnsw_size = flat_size * 1.5  # HNSW更大（包含图结构）
        
        return {
            "count": count,
            "dimension": dim,
            "current_type": self._index_type.value,
            "estimated_sizes": {
                "flat": f"{flat_size / 1024 / 1024:.2f} MB",
                "ivf": f"{ivf_size / 1024 / 1024:.2f} MB",
                "hnsw": f"{hnsw_size / 1024 / 1024:.2f} MB",
            },
            "recommendations": {
                "flat": f"适合 < {INDEX_THRESHOLD_IVF} 条数据",
                "ivf": f"适合 {INDEX_THRESHOLD_IVF} - {INDEX_THRESHOLD_HNSW} 条数据",
                "hnsw": f"适合 > {INDEX_THRESHOLD_HNSW} 条数据",
            }
        }
    
    @property
    def index_type(self) -> IndexType:
        """获取当前索引类型"""
        return self._index_type
    
    @property
    def is_trained(self) -> bool:
        """检查索引是否已训练（IVF索引需要）"""
        return self._is_trained
