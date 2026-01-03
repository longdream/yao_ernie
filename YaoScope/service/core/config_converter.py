"""
配置转换器 - 将HTTP请求配置转换为PlanScope所需格式
"""
from typing import Dict, Any


class ConfigConverter:
    """配置转换器"""
    
    @staticmethod
    def convert_to_planscope_config(
        main_config: Dict[str, str],
        advanced_config: Dict[str, str],
        vl_config: Dict[str, str],
        light_config: Dict[str, str],
        embedding_config: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        将HTTP配置转换为PlanScope配置格式
        
        Args:
            main_config: 主模型配置 {model_name, api_key, api_base}
            advanced_config: 高级模型配置
            vl_config: VL模型配置
            light_config: 轻量模型配置
            embedding_config: Embedding模型配置
            
        Returns:
            PlanScope配置字典
        """
        # PlanScope需要的配置格式
        planscope_config = {
            "llm": {
                "provider": "qwen",  # 假设使用qwen
                "api_key": main_config.get("api_key", ""),
                "base_url": main_config.get("api_base", ""),
                "model_name": main_config.get("model_name", ""),
                "temperature": 0.7,
                "max_tokens": 4096,
                "timeout": 60.0,
                "max_retries": 3
            },
            "embedding": {
                "provider": "qwen",
                "api_key": embedding_config.get("api_key", ""),
                "base_url": embedding_config.get("api_base", ""),
                "model_name": embedding_config.get("model_name", ""),
                "timeout": 60.0,
                "max_retries": 3
            },
            "reranker": {
                "provider": "bge",
                "api_key": main_config.get("api_key", ""),
                "base_url": main_config.get("api_base", ""),
                "model_name": "Bge-Reranker-Large",
                "endpoint": "/rerank",
                "timeout": 60.0,
                "max_retries": 3,
                "top_n": 5
            },
            # Plan专用LLM配置（使用advanced模型）
            "plan_llm": {
                "provider": "qwen",
                "api_key": advanced_config.get("api_key", ""),
                "base_url": advanced_config.get("api_base", ""),
                "model_name": advanced_config.get("model_name", ""),
                "temperature": 0.7,
                "max_tokens": 4096,
                "timeout": 60.0,
                "max_retries": 3
            }
        }
        
        return planscope_config
    
    @staticmethod
    def get_model_configs(
        main_config: Dict[str, str],
        advanced_config: Dict[str, str],
        vl_config: Dict[str, str],
        light_config: Dict[str, str]
    ) -> Dict[str, Dict[str, str]]:
        """
        获取所有模型配置（用于工具初始化）
        
        Returns:
            包含所有模型配置的字典
        """
        return {
            "main": main_config,
            "advanced": advanced_config,
            "vl": vl_config,
            "light": light_config
        }

