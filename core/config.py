# -*- coding: utf-8 -*-
"""
配置管理模块
支持配置热更新
"""

import os
import json
import logging
import base64
from typing import Any, Optional, Callable, List

logger = logging.getLogger(__name__)

# 尝试导入加密库
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError as e:
    CRYPTO_AVAILABLE = False
    logger.warning(f"cryptography库导入失败: {e}，API密钥将使用环境变量存储")

# Windows DPAPI作为备选方案
if os.name == "nt":
    try:
        import ctypes
        from ctypes import wintypes
        DPAPI_AVAILABLE = True
    except ImportError:
        DPAPI_AVAILABLE = False
else:
    DPAPI_AVAILABLE = False


class Config:
    """配置管理类"""
    
    _instance = None
    _config = {}
    _encryption_key = None
    _watcher = None
    _change_callbacks: List[Callable] = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._change_callbacks = []
            cls._instance._init_encryption()
            cls._instance._load_config()
        return cls._instance
    
    def _init_encryption(self):
        """初始化加密密钥"""
        if not CRYPTO_AVAILABLE:
            self._encryption_key = None
            logger.warning("加密库不可用，API密钥将存储在环境变量中")
            return
        
        # 使用机器特征生成密钥（跨平台）
        try:
            import platform
            
            # 组合多个机器特征
            machine_id = f"{platform.node()}-{platform.machine()}-{platform.system()}"
            
            # 使用PBKDF2派生密钥
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'ragproject_salt_v1',  # 固定salt，确保同一机器生成相同密钥
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode('utf-8')))
            self._encryption_key = Fernet(key)
            logger.info("加密模块初始化成功（Fernet）")
        except Exception as e:
            logger.exception(f"加密模块初始化失败: {e}，将使用环境变量")
            self._encryption_key = None
    
    def _get_config_path(self) -> str:
        """获取配置文件路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "settings.json")
    
    def _load_config(self) -> None:
        """加载配置"""
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._config = self._get_default_config()
        else:
            self._config = self._get_default_config()
            self._save_config()

        # 迁移旧的DPAPI加密密钥到新的Fernet加密
        if isinstance(self._config, dict):
            old_protected = self._config.pop("api_key_protected", None)
            raw_key = self._config.pop("api_key", None)
            
            if old_protected and DPAPI_AVAILABLE:
                # 尝试解密旧的DPAPI密钥
                plain = self._unprotect_secret_dpapi(old_protected)
                if plain:
                    logger.info("检测到旧的DPAPI加密密钥，正在迁移...")
                    self.set("api_key", plain)
                    return
            
            if raw_key:
                # 迁移明文密钥
                logger.info("检测到明文API密钥，正在加密...")
                self.set("api_key", str(raw_key))
    
    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "font_size": 10,
            "theme": "light",
            "api_base_url": "",
            "api_key_encrypted": "",  # 新的加密字段
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 2048,
            "temperature": 0.7,
            # RAG配置
            "embedding_model": "bge-large-zh",
            "chunk_size": 500,
            "chunk_overlap": 50,
            "retrieval_top_k": 5,
            "similarity_threshold": 0.4,
            # 历史消息配置
            "history_max_messages": 12,
            "history_max_chars": 6000,
            "context_max_chars": 4000
        }
    
    def _save_config(self) -> None:
        """保存配置（带文件锁）"""
        config_path = self._get_config_path()
        try:
            from core.file_lock import FileLock
            
            # 使用文件锁保护写入
            lock = FileLock(config_path, timeout=5.0)
            with lock:
                with open(config_path, 'w', encoding='utf-8') as f:
                    cfg = self._config if isinstance(self._config, dict) else {}
                    # 排除敏感字段
                    to_save = {k: v for k, v in cfg.items() if k not in ["api_key", "api_key_protected"]}
                    json.dump(to_save, f, ensure_ascii=False, indent=2)
        except TimeoutError:
            logger.error("保存配置失败：无法获取文件锁")
        except IOError as e:
            logger.exception("保存配置失败")
    
    def _encrypt_secret(self, secret: str) -> Optional[str]:
        """加密密钥（跨平台）"""
        if not secret or not secret.strip():
            return ""
        
        secret = secret.strip()
        
        # 优先使用Fernet加密
        if CRYPTO_AVAILABLE and self._encryption_key:
            try:
                encrypted = self._encryption_key.encrypt(secret.encode('utf-8'))
                return base64.b64encode(encrypted).decode('ascii')
            except Exception as e:
                logger.exception("Fernet加密失败")
        
        # 降级到DPAPI（仅Windows）
        if DPAPI_AVAILABLE:
            result = self._protect_secret_dpapi(secret)
            if result:
                return result
        
        # 最后降级：使用环境变量（不保存到文件）
        logger.warning("无可用加密方法，API密钥将仅存储在环境变量中")
        return None
    
    def _decrypt_secret(self, encrypted: str) -> Optional[str]:
        """解密密钥（跨平台）"""
        if not encrypted or not encrypted.strip():
            return ""
        
        encrypted = encrypted.strip()
        
        # 尝试Fernet解密
        if CRYPTO_AVAILABLE and self._encryption_key:
            try:
                decoded = base64.b64decode(encrypted.encode('ascii'))
                decrypted = self._encryption_key.decrypt(decoded)
                return decrypted.decode('utf-8')
            except Exception:
                pass  # 可能是DPAPI加密的，继续尝试
        
        # 尝试DPAPI解密（仅Windows）
        if DPAPI_AVAILABLE:
            result = self._unprotect_secret_dpapi(encrypted)
            if result:
                return result
        
        return None
    
    def _protect_secret_dpapi(self, secret: str) -> Optional[str]:
        """使用Windows DPAPI加密（备选方案）"""
        if not DPAPI_AVAILABLE or not secret:
            return None
        
        secret = secret.strip()
        if not secret:
            return ""
        
        try:
            in_bytes = secret.encode("utf-8")

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

            in_buffer = ctypes.create_string_buffer(in_bytes, len(in_bytes))
            in_blob = DATA_BLOB(len(in_bytes), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte)))
            out_blob = DATA_BLOB()

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            ok = crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                "RAGPROJECT_API_KEY",
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob),
            )
            if not ok:
                return None

            try:
                out_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            finally:
                kernel32.LocalFree(out_blob.pbData)

            return base64.b64encode(out_bytes).decode("ascii")
        except Exception:
            return None

    def _unprotect_secret_dpapi(self, protected: str) -> Optional[str]:
        """使用Windows DPAPI解密（备选方案）"""
        if not DPAPI_AVAILABLE or not protected:
            return None
        
        protected = protected.strip()
        if not protected:
            return ""
        
        try:
            in_bytes = base64.b64decode(protected.encode("ascii"), validate=True)

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

            in_buffer = ctypes.create_string_buffer(in_bytes, len(in_bytes))
            in_blob = DATA_BLOB(len(in_bytes), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte)))
            out_blob = DATA_BLOB()

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            ok = crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None,
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob),
            )
            if not ok:
                return None

            try:
                out_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            finally:
                kernel32.LocalFree(out_blob.pbData)

            return out_bytes.decode("utf-8")
        except Exception:
            return None

    
    def _get_env_override(self, key: str) -> Optional[str]:
        env_map = {
            "api_key": ["RAGPROJECT_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY"],
            "api_base_url": ["RAGPROJECT_API_BASE_URL", "SILICONFLOW_API_BASE_URL", "OPENAI_BASE_URL"],
        }

        for env_key in env_map.get(key, []):
            val = os.environ.get(env_key)
            if val is None:
                continue
            val = str(val).strip()
            if val:
                return val
        return None

    def get(self, key: str, default: Any = None, include_env: bool = True) -> Any:
        """获取配置项"""
        if include_env:
            env_val = self._get_env_override(key)
            if env_val is not None:
                return env_val
        
        if key == "api_key":
            encrypted = ""
            if isinstance(self._config, dict):
                encrypted = str(self._config.get("api_key_encrypted", "") or "")
            plain = self._decrypt_secret(encrypted)
            return plain if plain is not None else default
        
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        if key == "api_key":
            val = "" if value is None else str(value).strip()
            if isinstance(self._config, dict):
                encrypted = self._encrypt_secret(val)
                if encrypted is None:
                    # 加密失败，使用环境变量
                    if val:
                        os.environ["RAGPROJECT_API_KEY"] = val
                        logger.info("API密钥已保存到环境变量")
                    else:
                        os.environ.pop("RAGPROJECT_API_KEY", None)
                    self._config["api_key_encrypted"] = ""
                else:
                    self._config["api_key_encrypted"] = encrypted
                    if val:
                        os.environ["RAGPROJECT_API_KEY"] = val
                    else:
                        os.environ.pop("RAGPROJECT_API_KEY", None)
                self._save_config()
            return
        
        self._config[key] = value
        self._save_config()
    
    def get_all(self) -> dict:
        """获取所有配置"""
        return self._config.copy()
    
    def update(self, settings: dict) -> None:
        """批量更新配置"""
        if isinstance(settings, dict) and "api_key" in settings:
            val = settings.get("api_key")
            val = "" if val is None else str(val).strip()
            self.set("api_key", val)
            settings = {k: v for k, v in settings.items() if k != "api_key"}
        if isinstance(self._config, dict):
            self._config.update(settings)
        self._save_config()
    
    def enable_hot_reload(self, parent=None) -> bool:
        """启用配置热更新
        
        Args:
            parent: Qt父对象（可选）
        
        Returns:
            是否成功启用
        """
        try:
            from core.config_watcher import get_config_watcher
            
            self._watcher = get_config_watcher(parent)
            config_path = self._get_config_path()
            
            if self._watcher.watch(config_path):
                # 注册内部回调处理配置重载
                self._watcher.register_callback(self._on_config_changed)
                logger.info("配置热更新已启用")
                return True
            else:
                logger.warning("配置热更新启用失败")
                return False
        except ImportError as e:
            logger.warning(f"配置热更新模块不可用: {e}")
            return False
    
    def disable_hot_reload(self) -> None:
        """禁用配置热更新"""
        if self._watcher:
            config_path = self._get_config_path()
            self._watcher.unwatch(config_path)
            self._watcher = None
            logger.info("配置热更新已禁用")
    
    def _on_config_changed(self, event) -> None:
        """配置文件变更回调"""
        logger.info(f"检测到配置文件变更，重新加载配置...")
        
        # 保存当前的加密密钥（不需要重新加载）
        old_encrypted = self._config.get("api_key_encrypted", "")
        
        # 重新加载配置
        self._load_config()
        
        # 如果加密密钥没变，恢复它（避免触发不必要的迁移）
        if old_encrypted and not self._config.get("api_key_encrypted"):
            self._config["api_key_encrypted"] = old_encrypted
        
        # 通知所有注册的回调
        for callback in self._change_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.exception(f"配置变更回调执行失败: {e}")
    
    def on_change(self, callback: Callable) -> None:
        """注册配置变更回调
        
        Args:
            callback: 回调函数，接收 ConfigChangeEvent 参数
        """
        if callback not in self._change_callbacks:
            self._change_callbacks.append(callback)
    
    def off_change(self, callback: Callable) -> None:
        """取消注册配置变更回调"""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
    
    def on_key_change(self, key: str, callback: Callable) -> None:
        """注册特定配置键的变更回调
        
        Args:
            key: 配置键名
            callback: 回调函数，接收 (old_value, new_value) 参数
        """
        if self._watcher:
            self._watcher.register_callback(callback, key)
    
    def off_key_change(self, key: str, callback: Callable) -> None:
        """取消注册特定配置键的变更回调"""
        if self._watcher:
            self._watcher.unregister_callback(callback, key)
    
    def is_hot_reload_enabled(self) -> bool:
        """检查热更新是否已启用"""
        return self._watcher is not None
