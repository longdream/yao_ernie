"""
配置管理器适配器
从readscope提取的核心配置管理功能
"""
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigValidationError(Exception):
    """配置验证异常"""
    pass


class ConfigManager:
    """
    配置管理器
    提供与readscope.core.ConfigManager兼容的接口
    """
    
    def __init__(self, config_dict: Dict[str, Any]):
        """
        初始化配置管理器
        
        Args:
            config_dict: 配置字典
        """
        self.config = config_dict
        self.runtime_mode = "online"
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any], work_dir: str = "./planscope_data") -> "ConfigManager":
        """
        从字典创建ConfigManager实例
        
        Args:
            config: 配置字典，必须包含llm, embedding, reranker等配置
            work_dir: 工作目录路径
            
        Returns:
            ConfigManager实例
        """
        # 构建完整的配置结构
        full_config = {
            "runtime": {
                "mode": "online",
                "debug": False,
                "log_level": "INFO",
                "temp_file_cleanup": True
            },
            "online_models": {
                "llm": config.get("llm", {}),
                "embedding": config.get("embedding", {}),
                "reranker": config.get("reranker", {})
            },
            "local_models": {
                "llm": {},
                "embedding": {}
            },
            "document_processing": config.get("document_processing", {
                "max_file_size": 52428800,
                "supported_formats": [".pdf", ".docx", ".txt"],
                "paragraph_min_length": 50,
                "paragraph_max_length": 2000,
                "summary_max_length": 100,
                "summary_batch_size": 5,
                "cache_enabled": True,
                "cache_dir": f"{work_dir}/cache"
            }),
            "indexing": {
                "bm25": {
                    "k1": 1.5,
                    "b": 0.75,
                    "epsilon": 0.25
                }
            },
            "retrieval": config.get("retrieval", {
                "summary_selection": {
                    "batch_size": 10,
                    "use_agent": False
                },
                "content_retrieval": {
                    "bm25_top_k": 5,
                    "max_sentence_length": 500
                },
                "answer_generation": {
                    "max_context_length": 4000,
                    "include_source": True
                }
            }),
            "logging": {
                "file_path": f"{work_dir}/logs/planscope.log",
                "max_file_size": 10485760,
                "backup_count": 5,
                "log_level": "INFO"
            },
            "monitoring": {
                "enabled": False,
                "metrics_file": f"{work_dir}/metrics.json"
            },
            "storage": {
                "vector_dir": f"{work_dir}/vectors",
                "cache_dir": f"{work_dir}/cache"
            }
        }
        
        return cls(config_dict=full_config)
    
    def get_runtime_mode(self) -> str:
        """获取运行模式"""
        return self.config.get("runtime", {}).get("mode", "online")
    
    def get_llm_config(self) -> Dict[str, Any]:
        """获取LLM配置"""
        mode = self.get_runtime_mode()
        if mode == "online":
            return self.config.get("online_models", {}).get("llm", {})
        else:
            return self.config.get("local_models", {}).get("llm", {})
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """获取Embedding配置"""
        mode = self.get_runtime_mode()
        if mode == "online":
            return self.config.get("online_models", {}).get("embedding", {})
        else:
            return self.config.get("local_models", {}).get("embedding", {})
    
    def get_reranker_config(self) -> Dict[str, Any]:
        """获取Reranker配置"""
        return self.config.get("online_models", {}).get("reranker", {})
    
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get("logging", {
            "file_path": "./logs/planscope.log",
            "max_file_size": 10485760,
            "backup_count": 5,
            "log_level": "INFO"
        })
    
    def get_storage_config(self) -> Dict[str, Any]:
        """获取存储配置"""
        return self.config.get("storage", {
            "vector_dir": "./vectors",
            "cache_dir": "./cache"
        })

