# -*- coding: utf-8 -*-
"""
数据备份模块 - 自动备份和恢复

优化内容 (v2.3.0):
- 定期自动备份（可配置间隔）
- 支持数据导入导出
- 提供数据恢复功能
- 备份文件自动清理
"""

import os
import json
import shutil
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

logger = logging.getLogger(__name__)


class BackupManager:
    """备份管理器"""
    
    _instance = None
    
    # 需要备份的数据文件
    DATA_FILES = [
        "knowledge_base.json",
        "products.json",
        "users.json",
        "settings.json",
        "session_status.json",
        "vectors.index",
        "vectors_map.json"
    ]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._data_dir = os.path.join(self._base_dir, "data")
        self._backup_dir = os.path.join(self._base_dir, "backups")
        
        os.makedirs(self._backup_dir, exist_ok=True)
    
    def create_backup(self, description: str = "") -> Tuple[bool, str]:
        """创建备份
        
        Args:
            description: 备份描述
        
        Returns:
            (成功与否, 消息或备份文件路径)
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}.zip"
            backup_path = os.path.join(self._backup_dir, backup_name)
            
            # 创建ZIP备份
            with ZipFile(backup_path, 'w', ZIP_DEFLATED) as zipf:
                # 备份数据文件
                for filename in self.DATA_FILES:
                    filepath = os.path.join(self._data_dir, filename)
                    if os.path.exists(filepath):
                        zipf.write(filepath, f"data/{filename}")
                
                # 备份对话文件
                conv_dir = os.path.join(self._data_dir, "conversations")
                if os.path.exists(conv_dir):
                    for conv_file in os.listdir(conv_dir):
                        if conv_file.endswith(".json"):
                            conv_path = os.path.join(conv_dir, conv_file)
                            zipf.write(conv_path, f"data/conversations/{conv_file}")
                
                # 写入备份元数据
                metadata = {
                    "timestamp": timestamp,
                    "description": description,
                    "version": "2.3.0",
                    "files": self.DATA_FILES
                }
                zipf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            
            logger.info("备份创建成功: %s", backup_path)
            return True, backup_path
            
        except Exception as e:
            logger.exception("创建备份失败")
            return False, str(e)
    
    def restore_backup(self, backup_path: str) -> Tuple[bool, str]:
        """恢复备份
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            (成功与否, 消息)
        """
        if not os.path.exists(backup_path):
            return False, "备份文件不存在"
        
        try:
            # 先创建当前数据的备份
            self.create_backup("恢复前自动备份")
            
            with ZipFile(backup_path, 'r') as zipf:
                # 验证备份文件
                if "metadata.json" not in zipf.namelist():
                    return False, "无效的备份文件（缺少元数据）"
                
                # 解压到数据目录
                for name in zipf.namelist():
                    if name.startswith("data/"):
                        # 提取相对路径
                        rel_path = name[5:]  # 去掉 "data/" 前缀
                        if rel_path:
                            target_path = os.path.join(self._data_dir, rel_path)
                            target_dir = os.path.dirname(target_path)
                            os.makedirs(target_dir, exist_ok=True)
                            
                            with zipf.open(name) as src, open(target_path, 'wb') as dst:
                                dst.write(src.read())
            
            logger.info("备份恢复成功: %s", backup_path)
            return True, "备份恢复成功，请重启应用"
            
        except Exception as e:
            logger.exception("恢复备份失败")
            return False, str(e)
    
    def list_backups(self) -> List[Dict]:
        """列出所有备份"""
        backups = []
        
        for filename in os.listdir(self._backup_dir):
            if filename.endswith(".zip"):
                filepath = os.path.join(self._backup_dir, filename)
                stat = os.stat(filepath)
                
                # 尝试读取元数据
                description = ""
                try:
                    with ZipFile(filepath, 'r') as zipf:
                        if "metadata.json" in zipf.namelist():
                            metadata = json.loads(zipf.read("metadata.json"))
                            description = metadata.get("description", "")
                except:
                    pass
                
                backups.append({
                    "name": filename,
                    "path": filepath,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "description": description
                })
        
        return sorted(backups, key=lambda x: x["created"], reverse=True)
    
    def delete_backup(self, backup_path: str) -> bool:
        """删除备份"""
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
                logger.info("备份已删除: %s", backup_path)
                return True
        except Exception as e:
            logger.exception("删除备份失败")
        return False
    
    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """清理旧备份，保留最近N个
        
        Args:
            keep_count: 保留的备份数量
        
        Returns:
            删除的备份数量
        """
        backups = self.list_backups()
        deleted = 0
        
        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                if self.delete_backup(backup["path"]):
                    deleted += 1
        
        return deleted
    
    def export_data(self, export_path: str, include_vectors: bool = True) -> Tuple[bool, str]:
        """导出数据
        
        Args:
            export_path: 导出文件路径
            include_vectors: 是否包含向量索引
        
        Returns:
            (成功与否, 消息)
        """
        try:
            with ZipFile(export_path, 'w', ZIP_DEFLATED) as zipf:
                # 导出知识库
                kb_path = os.path.join(self._data_dir, "knowledge_base.json")
                if os.path.exists(kb_path):
                    zipf.write(kb_path, "knowledge_base.json")
                
                # 导出商品
                prod_path = os.path.join(self._data_dir, "products.json")
                if os.path.exists(prod_path):
                    zipf.write(prod_path, "products.json")
                
                # 导出向量索引
                if include_vectors:
                    for vf in ["vectors.index", "vectors_map.json"]:
                        vf_path = os.path.join(self._data_dir, vf)
                        if os.path.exists(vf_path):
                            zipf.write(vf_path, vf)
                
                # 写入导出元数据
                metadata = {
                    "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "version": "2.3.0",
                    "include_vectors": include_vectors
                }
                zipf.writestr("export_metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            
            logger.info("数据导出成功: %s", export_path)
            return True, export_path
            
        except Exception as e:
            logger.exception("导出数据失败")
            return False, str(e)
    
    def import_data(self, import_path: str, merge: bool = False) -> Tuple[bool, str]:
        """导入数据
        
        Args:
            import_path: 导入文件路径
            merge: 是否合并（True=合并，False=覆盖）
        
        Returns:
            (成功与否, 消息)
        """
        if not os.path.exists(import_path):
            return False, "导入文件不存在"
        
        try:
            # 先备份当前数据
            self.create_backup("导入前自动备份")
            
            with ZipFile(import_path, 'r') as zipf:
                if merge:
                    # 合并模式：读取并合并数据
                    return self._merge_import(zipf)
                else:
                    # 覆盖模式：直接解压
                    for name in zipf.namelist():
                        if name in ["knowledge_base.json", "products.json", "vectors.index", "vectors_map.json"]:
                            target_path = os.path.join(self._data_dir, name)
                            with zipf.open(name) as src, open(target_path, 'wb') as dst:
                                dst.write(src.read())
            
            logger.info("数据导入成功: %s", import_path)
            return True, "数据导入成功，请重启应用"
            
        except Exception as e:
            logger.exception("导入数据失败")
            return False, str(e)
    
    def _merge_import(self, zipf: ZipFile) -> Tuple[bool, str]:
        """合并导入数据"""
        merged_count = 0
        
        # 合并知识库
        if "knowledge_base.json" in zipf.namelist():
            import_data = json.loads(zipf.read("knowledge_base.json"))
            import_items = import_data.get("items", [])
            
            kb_path = os.path.join(self._data_dir, "knowledge_base.json")
            if os.path.exists(kb_path):
                with open(kb_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
                current_items = current_data.get("items", [])
                current_ids = {item["id"] for item in current_items}
                
                # 添加新条目
                for item in import_items:
                    if item["id"] not in current_ids:
                        current_items.append(item)
                        merged_count += 1
                
                current_data["items"] = current_items
                with open(kb_path, 'w', encoding='utf-8') as f:
                    json.dump(current_data, f, ensure_ascii=False, indent=2)
        
        return True, f"合并完成，新增 {merged_count} 条数据"
    
    @property
    def backup_dir(self) -> str:
        """获取备份目录"""
        return self._backup_dir
